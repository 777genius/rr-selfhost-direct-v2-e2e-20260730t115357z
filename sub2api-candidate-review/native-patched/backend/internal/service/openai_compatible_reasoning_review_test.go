//go:build unit

package service

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/config"
	coderws "github.com/coder/websocket"
	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
	"github.com/tidwall/gjson"
	"github.com/tidwall/sjson"
)

const compatibleCipherRejection = `{"error":{"code":"invalid_encrypted_content","type":"invalid_request_error","message":"Provider rejected opaque cipher"}}`
const compatibleCipherFailed = `{"type":"response.failed","response":{"id":"resp_rejected","error":{"code":"invalid_encrypted_content","message":"Provider rejected opaque cipher"}}}`
const compatibleCompleted = `{"type":"response.completed","response":{"id":"resp_review","model":"mimo-v2.6-pro","output":[],"usage":{"input_tokens":1,"output_tokens":1}}}`

func compatibleReviewResponse(status int, body string) *http.Response {
	return &http.Response{StatusCode: status, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(body))}
}

func compatibleReviewCipherSSEResponse() *http.Response {
	stream := "data: {\"type\":\"error\"," + compatibleCipherRejection[1:] + "\n\ndata: " + compatibleCipherFailed + "\n\ndata: [DONE]\n\n"
	return &http.Response{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader(stream))}
}

func TestCompatibleReasoningReviewF1HTTP(t *testing.T) {
	for _, optIn := range []bool{false, true} {
		for _, seeded := range []bool{false, true} {
			for _, passthrough := range []bool{false, true} {
				if passthrough && !optIn {
					continue // Legacy recovery belongs to the non-passthrough route.
				}
				t.Run(fmt.Sprintf("opt_%t/seed_%t/pass_%t", optIn, seeded, passthrough), func(t *testing.T) {
					body := compatibleReasoningRequest(`"store":false,`)
					upstream := &httpUpstreamSequenceRecorder{responses: []*http.Response{
						compatibleReviewResponse(http.StatusBadRequest, compatibleCipherRejection),
						compatibleReviewResponse(http.StatusOK, `{"id":"resp_review","output":[],"usage":{"input_tokens":1,"output_tokens":1}}`),
					}}
					if seeded {
						upstream.responses = upstream.responses[1:]
					}
					svc := newOpenAIImageGenerationControlTestService(nil)
					svc.httpUpstream = upstream
					c, rec := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
					c.Request.Header.Set("session_id", "review-session")
					account := newOpenAIImageGenerationControlTestAccount()
					account.Extra = map[string]any{"openai_preserve_compatible_reasoning": optIn, "openai_passthrough": passthrough}
					store := svc.getOpenAIWSStateStore()
					hash := svc.GenerateSessionHash(c, body)
					require.NotEmpty(t, hash)
					if seeded {
						store.MarkSessionInvalidEncryptedContent(getOpenAIGroupIDFromContext(c), hash, collectOpenAIEncryptedContentDigestsRaw(body), time.Minute)
					}
					before := store.GetSessionInvalidEncryptedContentDigests(getOpenAIGroupIDFromContext(c), hash)
					_, err := svc.Forward(context.Background(), c, account, body)
					if optIn && !seeded {
						require.Equal(t, 1, upstream.callCount, "F1: original rejection must not cause recovery retry")
						require.Error(t, err)
						require.Equal(t, http.StatusBadRequest, rec.Code)
						require.JSONEq(t, compatibleCipherRejection, rec.Body.String())
					} else {
						require.NoError(t, err)
					}
					require.Equal(t, optIn || !seeded, gjson.GetBytes(upstream.bodies[0], "input.#(id==\"rs_cipher\").encrypted_content").Exists() ||
						gjson.GetBytes(upstream.bodies[0], "input.#(encrypted_content==\"opaque-provider-cipher\")").Exists(), "F1: first outbound seeded ciphertext")
					if optIn {
						require.Equal(t, 1, upstream.callCount)
						require.Equal(t, before, store.GetSessionInvalidEncryptedContentDigests(getOpenAIGroupIDFromContext(c), hash), "F1: no lineage recording")
						require.Equal(t, seeded, store.HasAnySessionInvalidEncryptedContent())
						assertCompatibleReplay(t, upstream.bodies[0], true, true)
					} else if !seeded {
						require.Equal(t, 2, upstream.callCount, "default ciphertext recovery retained")
						require.False(t, gjson.GetBytes(upstream.bodies[1], "input.#(encrypted_content==\"opaque-provider-cipher\")").Exists())
						require.True(t, store.HasAnySessionInvalidEncryptedContent())
					} else {
						require.Equal(t, 1, upstream.callCount)
					}
				})
			}
		}
	}
}

func TestCompatibleReasoningReviewF2ImageMigration(t *testing.T) {
	for _, boundary := range []string{"ws", "http", "http_passthrough"} {
		t.Run(boundary, func(t *testing.T) {
			account := newOpenAIImageGenerationControlTestAccount()
			account.Extra = map[string]any{"openai_preserve_compatible_reasoning": true, "openai_passthrough": boundary == "http_passthrough"}
			body, err := sjson.SetRawBytes(compatibleReasoningRequest(`"store":false,`), "tools", []byte(`[{"type":"image_generation","format":"jpeg","compression":87}]`))
			require.NoError(t, err)
			var outbound []byte
			if boundary == "ws" {
				outbound, _, err = normalizeOpenAIResponsesWebSocketCompatibilityBody(body, account, false)
			} else {
				upstream := &httpUpstreamRecorder{resp: compatibleReviewResponse(http.StatusOK, `{"id":"resp_review","output":[],"usage":{"input_tokens":1,"output_tokens":1}}`)}
				svc := newOpenAIImageGenerationControlTestService(upstream)
				c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
				_, err = svc.Forward(context.Background(), c, account, body)
				outbound = upstream.lastBody
			}
			require.NoError(t, err)
			require.Equal(t, "jpeg", gjson.GetBytes(outbound, "tools.0.output_format").String())
			require.Equal(t, "87", gjson.GetBytes(outbound, "tools.0.output_compression").Raw)
			require.False(t, gjson.GetBytes(outbound, "tools.0.format").Exists())
			require.False(t, gjson.GetBytes(outbound, "tools.0.compression").Exists())
			require.Equal(t, "9007199254740993", gjson.GetBytes(outbound, "input.0.opaque").Raw, "F2: whole-body image migration rounded opaque integer")
			assertCompatibleReplay(t, outbound, true, true)
		})
	}
}

func TestCompatibleReasoningReviewNamespaceHTTP(t *testing.T) {
	for _, optIn := range []bool{false, true} {
		upstream := &httpUpstreamRecorder{resp: compatibleReviewResponse(http.StatusOK, `{"id":"resp_review","output":[],"usage":{"input_tokens":1,"output_tokens":1}}`)}
		svc := newOpenAIImageGenerationControlTestService(upstream)
		account := newOpenAIImageGenerationControlTestAccount()
		account.Extra = map[string]any{"openai_preserve_compatible_reasoning": optIn}
		body, err := sjson.SetBytes(compatibleReasoningRequest(`"store":true,`), "input.8.namespace", "remove.nonreasoning")
		require.NoError(t, err)
		c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
		_, err = svc.Forward(context.Background(), c, account, body)
		require.NoError(t, err)
		require.Equal(t, optIn, gjson.GetBytes(upstream.lastBody, "input.0.namespace").Exists(), "reasoning namespace extension")
		require.False(t, gjson.GetBytes(upstream.lastBody, "input.8.namespace").Exists())
		assertCompatibleReplay(t, upstream.lastBody, optIn, false)
	}
}

func compatibleReviewWSConfig() *config.Config {
	cfg := &config.Config{}
	cfg.Security.URLAllowlist.AllowInsecureHTTP = true
	cfg.Gateway.OpenAIWS.Enabled = true
	cfg.Gateway.OpenAIWS.APIKeyEnabled = true
	cfg.Gateway.OpenAIWS.OAuthEnabled = true
	cfg.Gateway.OpenAIWS.ResponsesWebsocketsV2 = true
	cfg.Gateway.OpenAIWS.MaxConnsPerAccount = 1
	cfg.Gateway.OpenAIWS.MaxIdlePerAccount = 1
	cfg.Gateway.OpenAIWS.ReadTimeoutSeconds = 3
	cfg.Gateway.OpenAIWS.WriteTimeoutSeconds = 3
	return cfg
}

// Real upstream socket; raw frames are captured before any test-side decode.
func compatibleReviewWSServer(t *testing.T, reject bool) (*httptest.Server, <-chan []byte) {
	t.Helper()
	frames := make(chan []byte, 8)
	upgrader := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()
		for {
			_, raw, err := conn.ReadMessage()
			if err != nil {
				return
			}
			frames <- raw
			if reject {
				_ = conn.WriteMessage(websocket.TextMessage, []byte(`{"type":"error",`+compatibleCipherRejection[1:]))
				_ = conn.WriteMessage(websocket.TextMessage, []byte(compatibleCipherFailed))
			} else {
				_ = conn.WriteMessage(websocket.TextMessage, []byte(compatibleCompleted))
			}
		}
	}))
	t.Cleanup(server.Close)
	return server, frames
}

func TestCompatibleReasoningReviewF1WSForward(t *testing.T) {
	for _, seeded := range []bool{false, true} {
		t.Run(fmt.Sprintf("seed_%t", seeded), func(t *testing.T) {
			server, frames := compatibleReviewWSServer(t, !seeded)
			cfg := compatibleReviewWSConfig()
			svc := &OpenAIGatewayService{cfg: cfg, httpUpstream: &httpUpstreamRecorder{}, openaiWSResolver: NewOpenAIWSProtocolResolver(cfg), toolCorrector: NewCodexToolCorrector()}
			t.Cleanup(func() { svc.getOpenAIWSConnPool().Close() })
			account := newOpenAIImageGenerationControlTestAccount()
			account.Credentials["base_url"] = server.URL
			account.Extra = map[string]any{"openai_preserve_compatible_reasoning": true, "responses_websockets_v2_enabled": true}
			c, rec := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
			c.Request.Header.Set("session_id", "review-session")
			SetOpenAIClientTransport(c, OpenAIClientTransportWS)
			body := compatibleReasoningRequest(`"store":false,`)
			store := svc.getOpenAIWSStateStore()
			hash := svc.GenerateSessionHash(c, body)
			if seeded {
				store.MarkSessionInvalidEncryptedContent(getOpenAIGroupIDFromContext(c), hash, collectOpenAIEncryptedContentDigestsRaw(body), time.Minute)
			}
			before := store.GetSessionInvalidEncryptedContentDigests(getOpenAIGroupIDFromContext(c), hash)
			_, err := svc.Forward(context.Background(), c, account, body)
			require.Len(t, frames, 1, "F1: WS recovery must make one request")
			if seeded {
				require.NoError(t, err)
			} else {
				require.Error(t, err)
				require.Contains(t, err.Error(), "invalid_encrypted_content")
				require.Equal(t, http.StatusBadRequest, rec.Code)
				require.JSONEq(t, gjson.Get(compatibleCipherRejection, "error").Raw, gjson.Get(rec.Body.String(), "error").Raw)
			}
			assertCompatibleReplay(t, <-frames, true, true)
			require.Equal(t, before, store.GetSessionInvalidEncryptedContentDigests(getOpenAIGroupIDFromContext(c), hash))
		})
	}
}

func TestCompatibleReasoningReviewF1WSIngress(t *testing.T) {
	for _, mode := range []string{"native", "http", "sse"} {
		bridge, sse := mode != "native", mode == "sse"
		for _, optIn := range []bool{false, true} {
			for _, seeded := range []bool{false, true} {
				if sse && !optIn {
					continue // Legacy SSE return is covered by the direct bridge control.
				}
				name := fmt.Sprintf("bridge_%t/opt_%t/seed_%t", bridge, optIn, seeded)
				if sse {
					name += "/sse"
				}
				t.Run(name, func(t *testing.T) {
					cfg := compatibleReviewWSConfig()
					cfg.Gateway.OpenAIWS.ModeRouterV2Enabled = bridge
					cfg.Gateway.OpenAIWS.IngressModeDefault = OpenAIWSIngressModeCtxPool
					wsServer, frames := compatibleReviewWSServer(t, !seeded)
					upstream := &httpUpstreamSequenceRecorder{responses: []*http.Response{compatibleReviewResponse(http.StatusBadRequest, compatibleCipherRejection)}}
					if seeded && !sse {
						upstream.responses = []*http.Response{{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader("data: " + compatibleCompleted + "\n\ndata: [DONE]\n\n"))}}
					}
					if sse {
						upstream.responses = []*http.Response{compatibleReviewCipherSSEResponse()}
					}
					svc := &OpenAIGatewayService{cfg: cfg, httpUpstream: upstream, cache: &stubGatewayCache{}, openaiWSResolver: NewOpenAIWSProtocolResolver(cfg), toolCorrector: NewCodexToolCorrector()}
					t.Cleanup(func() { svc.getOpenAIWSConnPool().Close() })
					account := newOpenAIImageGenerationControlTestAccount()
					account.Credentials["base_url"] = wsServer.URL
					account.Extra = map[string]any{"openai_preserve_compatible_reasoning": optIn, "responses_websockets_v2_enabled": true}
					if bridge {
						account.Extra["openai_apikey_responses_websockets_v2_mode"] = OpenAIWSIngressModeHTTPBridge
					}
					body := append([]byte(`{"type":"response.create",`), compatibleReasoningRequest(`"store":false,`)[1:]...)
					store := svc.getOpenAIWSStateStore()
					var callbackCount, callbackTurn int
					var callbackResult *OpenAIForwardResult
					var callbackErr error
					hooks := &OpenAIWSIngressHooks{AfterTurn: func(turn int, result *OpenAIForwardResult, err error) {
						callbackCount++
						callbackTurn, callbackResult, callbackErr = turn, result, err
					}}
					done := make(chan error, 1)
					server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
						conn, err := coderws.Accept(w, r, nil)
						if err != nil {
							done <- err
							return
						}
						defer conn.CloseNow()
						c, _ := gin.CreateTestContext(httptest.NewRecorder())
						c.Request = r
						ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
						defer cancel()
						_, first, err := conn.Read(ctx)
						if err == nil {
							hash := svc.GenerateSessionHash(c, first)
							if scope, _ := resolveOpenAIWSExecutionScope(c, first, 0); scope != "" {
								hash = scope
							}
							if seeded {
								store.MarkSessionInvalidEncryptedContent(0, hash, collectOpenAIEncryptedContentDigestsRaw(first), time.Minute)
							}
							err = svc.ProxyResponsesWebSocketFromClient(ctx, c, conn, account, "sk-test", first, hooks)
						}
						done <- err
					}))
					defer server.Close()
					ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
					defer cancel()
					client, _, err := coderws.Dial(ctx, "ws"+strings.TrimPrefix(server.URL, "http"), &coderws.DialOptions{HTTPHeader: http.Header{"session_id": []string{"review-session"}, "User-Agent": []string{"unit-test-agent/1.0"}}})
					require.NoError(t, err)
					defer client.CloseNow()
					require.NoError(t, client.Write(ctx, coderws.MessageText, body))
					_, event, err := client.Read(ctx)
					require.NoError(t, err)
					if !seeded && optIn && !sse {
						require.Equal(t, "invalid_encrypted_content", gjson.GetBytes(event, "error.code").String())
						require.Equal(t, "Provider rejected opaque cipher", gjson.GetBytes(event, "error.message").String())
					}
					if sse {
						require.JSONEq(t, compatibleCipherFailed, string(event), "F1: original SSE client terminal")
					}
					if !bridge && !seeded {
						_, _, err = client.Read(ctx) // Authoritative response.failed terminal.
						require.NoError(t, err)
					}
					if !sse {
						_ = client.Close(coderws.StatusNormalClosure, "done")
					}
					select {
					case err = <-done:
						if bridge && (!seeded || sse) {
							require.Error(t, err)
						} else {
							require.NoError(t, err)
						}
					case <-ctx.Done():
						t.Fatal("ingress did not terminate")
					}
					if sse {
						var failover *UpstreamFailoverError
						require.False(t, errors.As(err, &failover), "F1: ingress must not offer account retry/fallback")
						require.False(t, isOpenAIWSIngressTurnRetryable(err))
						_, retry := OpenAIWSCurrentTurnRetryPayload(err)
						require.False(t, retry)
						require.EqualError(t, err, "invalid_encrypted_content: Provider rejected opaque cipher")
						require.Equal(t, 1, callbackCount)
						require.Equal(t, 1, callbackTurn)
						require.Same(t, err, callbackErr)
						require.NotNil(t, callbackResult)
						require.Equal(t, "response.failed", callbackResult.UpstreamTerminalEvent)
						require.Empty(t, frames, "F1: bridge rejection must not fall back to native WS")
					}
					var outbound []byte
					if bridge {
						require.Equal(t, 1, upstream.callCount)
						outbound = upstream.bodies[0]
					} else {
						require.Len(t, frames, 1)
						outbound = <-frames
					}
					require.Equal(t, optIn || !seeded, gjson.GetBytes(outbound, "input.#(encrypted_content==\"opaque-provider-cipher\")").Exists(), "F1: actual ingress prestrip")
					if optIn {
						assertCompatibleReplay(t, outbound, true, true)
					}
					require.Equal(t, seeded || !optIn, store.HasAnySessionInvalidEncryptedContent(), "F1: ingress lineage policy")
				})
			}
		}
	}
}

func TestCompatibleReasoningReviewOAuthRecoveryDefault(t *testing.T) {
	for _, accountType := range []string{AccountTypeOAuth, AccountTypeSetupToken} {
		t.Run(accountType, func(t *testing.T) {
			upstream := &httpUpstreamSequenceRecorder{responses: []*http.Response{
				compatibleReviewResponse(http.StatusBadRequest, compatibleCipherRejection),
				{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader("data: " + compatibleCompleted + "\n\ndata: [DONE]\n\n"))},
			}}
			svc := newOpenAIImageGenerationControlTestService(nil)
			svc.httpUpstream = upstream
			account := newOpenAIImageGenerationControlTestAccount()
			account.Type = accountType
			account.Credentials = map[string]any{"access_token": "synthetic-token", "chatgpt_account_id": "synthetic-account"}
			account.Extra = map[string]any{"openai_preserve_compatible_reasoning": true}
			c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
			c.Request.Header.Set("session_id", "review-oauth-control")
			_, err := svc.Forward(context.Background(), c, account, compatibleReasoningRequest(`"store":false,`))
			require.NoError(t, err)
			require.Equal(t, 2, upstream.callCount, "OAuth-like accounts retain recovery despite flag")
			require.True(t, gjson.GetBytes(upstream.bodies[0], "input.#(encrypted_content==\"opaque-provider-cipher\")").Exists())
			require.False(t, gjson.GetBytes(upstream.bodies[1], "input.#(encrypted_content==\"opaque-provider-cipher\")").Exists())
			require.True(t, svc.getOpenAIWSStateStore().HasAnySessionInvalidEncryptedContent())
		})
	}
}

func TestCompatibleReasoningReviewF1BridgeSSELineage(t *testing.T) {
	for _, optIn := range []bool{false, true} {
		t.Run(fmt.Sprintf("opt_%t", optIn), func(t *testing.T) {
			upstream := &httpUpstreamSequenceRecorder{responses: []*http.Response{compatibleReviewCipherSSEResponse()}}
			svc := newOpenAIImageGenerationControlTestService(nil)
			svc.httpUpstream = upstream
			account := newOpenAIImageGenerationControlTestAccount()
			account.Extra = map[string]any{"openai_preserve_compatible_reasoning": optIn}
			c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
			c.Request.Header.Set("session_id", "review-sse-control")
			body, _, err := normalizeOpenAIResponsesWebSocketCompatibilityBody(compatibleReasoningRequest(`"store":false,`), account, false)
			require.NoError(t, err)
			var events [][]byte
			result, err := svc.proxyOpenAIWSHTTPBridgeTurn(context.Background(), c, account, "sk-test", body, len(body), "mimo-v2.6-pro", "", "", "", "", 1, func(event []byte) error {
				events = append(events, append([]byte(nil), event...))
				return nil
			})
			var failover *UpstreamFailoverError
			if optIn {
				require.False(t, errors.As(err, &failover), "F1: SSE ciphertext rejection must not fail over")
				require.EqualError(t, err, "invalid_encrypted_content: Provider rejected opaque cipher")
				require.NotNil(t, result)
				require.Equal(t, "response.failed", result.UpstreamTerminalEvent)
				require.Len(t, events, 1)
				require.JSONEq(t, compatibleCipherFailed, string(events[0]))
			} else {
				require.ErrorAs(t, err, &failover, "Default bridge retains legacy failover")
				require.Equal(t, http.StatusBadGateway, failover.StatusCode)
				require.JSONEq(t, `{"error":{"type":"upstream_error","message":"Provider rejected opaque cipher"}}`, string(failover.ResponseBody))
				require.True(t, failover.ShouldRetryNextAccount())
				require.Nil(t, result)
				require.Empty(t, events, "Legacy failover occurs before client output")
			}
			require.Equal(t, 1, upstream.callCount)
			require.Equal(t, !optIn, svc.getOpenAIWSStateStore().HasAnySessionInvalidEncryptedContent(), "F1: bridge SSE lineage recording")
			if optIn {
				assertCompatibleReplay(t, upstream.bodies[0], true, true)
			}
		})
	}
}
