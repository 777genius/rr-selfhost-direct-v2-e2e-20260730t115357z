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

	coderws "github.com/coder/websocket"
	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
	"github.com/tidwall/gjson"
	"github.com/tidwall/sjson"
)

const repairOpaqueItem = `{"type":"reasoning","id":"rs_repair","status":"completed","prompt_cache_breakpoint":true,"encrypted_content":"synthetic-cipher","content":[{"type":"reasoning_text","text":"synthetic history"}],"extension":{"reference":{"type":"item_reference","id":"rs_prior"},"integer":9007199254740993,"decimal":1.234567890123456789,"nested":[null,true,{"id":"provider.private"}]}}`

func repairRequest(t *testing.T, nullContent bool) []byte {
	t.Helper()
	item := repairOpaqueItem
	if nullContent {
		var err error
		item, err = sjson.SetRaw(item, "content", "null")
		require.NoError(t, err)
	}
	return []byte(`{"model":"mimo-v2.6-pro","stream":false,"store":true,"truncation":"auto","input":[` + item + `,` + repairOpaqueItem + `,{"type":"item_reference","id":"rs_repair","status":"completed","extension":9007199254740993},{"role":"user","status":"completed","content":null}]}`)
}

// Inspect the whole opaque item with UseNumber: JSONEq alone rounds numbers.
func assertRepairOpaqueItems(t *testing.T, expected, actual []byte) {
	t.Helper()
	for _, index := range []int{0, 1, 2} {
		var before, after any
		path := fmt.Sprintf("input.%d", index)
		require.NoError(t, decodeOpenAIJSONUseNumber([]byte(gjson.GetBytes(expected, path).Raw), &before))
		require.NoError(t, decodeOpenAIJSONUseNumber([]byte(gjson.GetBytes(actual, path).Raw), &after))
		require.Equal(t, before, after, "entire opaque item at %s", path)
	}
}

func assertRepairNoRetry(t *testing.T, err error) {
	t.Helper()
	require.Error(t, err)
	var failover *UpstreamFailoverError
	require.False(t, errors.As(err, &failover))
	require.False(t, isOpenAIWSIngressTurnRetryable(err))
	_, retry := OpenAIWSCurrentTurnRetryPayload(err)
	require.False(t, retry)
}

func TestCompatibleReasoningRepairRejectedFields(t *testing.T) {
	cases := []struct {
		name, code, param, message, repairedPath string
		nullContent, protected                   bool
	}{
		{"content", "array_above_max_length", "input[0].content", "Invalid 'input[0].content': array too long. Expected an array with maximum length 0, but got an array with length 1 instead.", "input.0.content", false, true},
		{"null", "invalid_type", "input[0].content", "Invalid type for 'input[0].content': expected a string or a list, but got null instead.", "input.0.content", true, true},
		{"status", "unknown_parameter", "input[0].status", "Unknown parameter: 'input[0].status'.", "input.0.status", false, true},
		{"cache", "invalid_parameter", "input[0].prompt_cache_breakpoint", "'input[0].prompt_cache_breakpoint' is not supported on this model.", "input.0.prompt_cache_breakpoint", false, true},
		{"reference_status", "unknown_parameter", "input[2].status", "Unknown parameter: 'input[2].status'.", "input.2.status", false, true},
		{"user_status", "unknown_parameter", "input[3].status", "Unknown parameter: 'input[3].status'.", "input.3.status", false, false},
		{"user_null", "invalid_type", "input[3].content", "Invalid type for 'input[3].content': expected a string or a list, but got null instead.", "input.3.content", false, false},
		{"truncation", "unsupported_parameter", "truncation", "Unsupported parameter: truncation", "truncation", false, false},
	}
	for _, mode := range []string{"http", "passthrough", "bridge", "native"} {
		for _, tc := range cases {
			for _, optIn := range []bool{true, false} {
				if !optIn && tc.name == "content" {
					continue // Legacy proactive content stripping precedes this rejection.
				}
				t.Run(fmt.Sprintf("%s/%s/opt_%t", mode, tc.name, optIn), func(t *testing.T) {
					body := repairRequest(t, tc.nullContent)
					rejection, err := sjson.Set(`{"status":400,"error":{"type":"invalid_request_error"}}`, "error.code", tc.code)
					require.NoError(t, err)
					rejection, err = sjson.Set(rejection, "error.param", tc.param)
					require.NoError(t, err)
					rejection, err = sjson.Set(rejection, "error.message", tc.message)
					require.NoError(t, err)
					stop := optIn && tc.protected
					account := newOpenAIImageGenerationControlTestAccount()
					account.Extra = map[string]any{"openai_preserve_compatible_reasoning": optIn, "openai_passthrough": mode == "passthrough", "responses_websockets_v2_enabled": true}
					upstream := &httpUpstreamSequenceRecorder{responses: []*http.Response{
						compatibleReviewResponse(http.StatusBadRequest, rejection),
						compatibleReviewResponse(http.StatusOK, `{"id":"resp_repair","output":[],"usage":{"input_tokens":1,"output_tokens":1}}`),
					}}
					svc := newOpenAIImageGenerationControlTestService(nil)
					svc.httpUpstream = upstream
					var outbound [][]byte
					if mode == "http" || mode == "passthrough" {
						c, rec := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
						_, err = svc.Forward(context.Background(), c, account, body)
						if stop {
							require.Equal(t, http.StatusBadRequest, rec.Code)
							require.JSONEq(t, rejection, rec.Body.String())
						}
						outbound = upstream.bodies
					} else {
						cfg := compatibleReviewWSConfig()
						cfg.Gateway.OpenAIWS.ModeRouterV2Enabled = mode == "bridge"
						cfg.Gateway.OpenAIWS.IngressModeDefault = OpenAIWSIngressModeCtxPool
						svc.cfg, svc.cache, svc.openaiWSResolver = cfg, &stubGatewayCache{}, NewOpenAIWSProtocolResolver(cfg)
						if mode == "bridge" {
							account.Extra["openai_apikey_responses_websockets_v2_mode"] = OpenAIWSIngressModeHTTPBridge
							upstream.responses[1] = &http.Response{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader("data: " + compatibleCompleted + "\n\ndata: [DONE]\n\n"))}
						}
						frames := make(chan []byte, 8)
						upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
						wsServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
							conn, upgradeErr := upgrader.Upgrade(w, r, nil)
							if upgradeErr != nil {
								return
							}
							defer conn.Close()
							for {
								_, raw, readErr := conn.ReadMessage()
								if readErr != nil {
									return
								}
								frames <- raw
								event := compatibleCompleted
								if len(frames) == 1 {
									event = `{"type":"error",` + rejection[1:]
								}
								if conn.WriteMessage(websocket.TextMessage, []byte(event)) != nil {
									return
								}
							}
						}))
						defer wsServer.Close()
						account.Credentials["base_url"] = wsServer.URL
						t.Cleanup(func() { svc.getOpenAIWSConnPool().Close() })
						done := make(chan error, 1)
						server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
							conn, acceptErr := coderws.Accept(w, r, nil)
							if acceptErr != nil {
								done <- acceptErr
								return
							}
							defer conn.CloseNow()
							c, _ := gin.CreateTestContext(httptest.NewRecorder())
							c.Request = r
							ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
							defer cancel()
							_, first, proxyErr := conn.Read(ctx)
							if proxyErr == nil {
								proxyErr = svc.ProxyResponsesWebSocketFromClient(ctx, c, conn, account, "sk-test", first, nil)
							}
							done <- proxyErr
						}))
						defer server.Close()
						ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
						defer cancel()
						client, _, dialErr := coderws.Dial(ctx, "ws"+strings.TrimPrefix(server.URL, "http"), nil)
						require.NoError(t, dialErr)
						defer client.CloseNow()
						require.NoError(t, client.Write(ctx, coderws.MessageText, append([]byte(`{"type":"response.create",`), body[1:]...)))
						_, event, readErr := client.Read(ctx)
						require.NoError(t, readErr)
						if stop {
							require.JSONEq(t, gjson.Get(rejection, "error").Raw, gjson.GetBytes(event, "error").Raw)
						} else {
							require.Equal(t, "response.completed", gjson.GetBytes(event, "type").String())
							_ = client.Close(coderws.StatusNormalClosure, "done")
						}
						select {
						case err = <-done:
						case <-ctx.Done():
							t.Fatal("service did not terminate after semantic rejection/control")
						}
						if mode == "native" {
							for len(frames) > 0 {
								outbound = append(outbound, <-frames)
							}
							require.Zero(t, upstream.callCount, "no HTTP fallback")
						} else {
							outbound = upstream.bodies
							require.Empty(t, frames, "no native fallback")
						}
					}
					if stop {
						assertRepairNoRetry(t, err)
						require.Len(t, outbound, 1, "no mutated replay")
					} else {
						require.NoError(t, err)
						require.Len(t, outbound, 2, "ordinary/default field recovery retained")
						if tc.name == "user_null" {
							require.Equal(t, `""`, gjson.GetBytes(outbound[1], tc.repairedPath).Raw)
						} else {
							require.False(t, gjson.GetBytes(outbound[1], tc.repairedPath).Exists())
						}
					}
					if optIn {
						for _, raw := range outbound {
							assertRepairOpaqueItems(t, body, raw)
						}
					}
					require.False(t, svc.getOpenAIWSStateStore().HasAnySessionInvalidEncryptedContent())
				})
			}
		}
	}
}

func TestCompatibleReasoningRepairEmptyImages(t *testing.T) {
	for _, passthrough := range []bool{false, true} {
		for _, optIn := range []bool{false, true} {
			t.Run(fmt.Sprintf("pass_%t/opt_%t", passthrough, optIn), func(t *testing.T) {
				body := repairRequest(t, false)
				var err error
				// Same cleanup trigger inside opaque reasoning and an ordinary user message.
				body, err = sjson.SetRawBytes(body, "input.0.content", []byte(`[{"type":"input_image","image_url":"data:image/png;base64,"},{"type":"reasoning_text","text":"keep"}]`))
				require.NoError(t, err)
				body, err = sjson.SetRawBytes(body, "input.3.content", []byte(`[{"type":"input_image","image_url":"data:image/png;base64,"},{"type":"input_text","text":"continue"}]`))
				require.NoError(t, err)
				upstream := &httpUpstreamSequenceRecorder{responses: []*http.Response{compatibleReviewResponse(http.StatusOK, `{"id":"resp_repair","output":[],"usage":{"input_tokens":1,"output_tokens":1}}`)}}
				svc := newOpenAIImageGenerationControlTestService(nil)
				svc.httpUpstream = upstream
				account := newOpenAIImageGenerationControlTestAccount()
				account.Extra = map[string]any{"openai_passthrough": passthrough, "openai_preserve_compatible_reasoning": optIn}
				c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
				_, err = svc.Forward(context.Background(), c, account, body)
				require.NoError(t, err)
				require.Equal(t, 1, upstream.callCount)
				require.Equal(t, int64(1), gjson.GetBytes(upstream.bodies[0], "input.3.content.#").Int())
				require.Equal(t, "continue", gjson.GetBytes(upstream.bodies[0], "input.3.content.0.text").String())
				if optIn {
					assertRepairOpaqueItems(t, body, upstream.bodies[0])
				}
			})
		}
	}
}

func TestCompatibleReasoningRepairEmptyImageRejectsBogusNumbers(t *testing.T) {
	for _, numeric := range []string{"01", "NaN", "1e", "1.2.3"} {
		t.Run(numeric, func(t *testing.T) {
			body := []byte(`{"input":[{"role":"user","content":[{"type":"input_image","image_url":"data:image/png;base64,"}]}],"opaque":` + numeric + `}`)
			_, _, err := sanitizeEmptyBase64InputImagesInOpenAIBody(body)
			require.Error(t, err)
		})
	}
}
