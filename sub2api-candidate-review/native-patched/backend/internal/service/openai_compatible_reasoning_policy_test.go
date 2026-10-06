//go:build unit

package service

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
	"github.com/tidwall/gjson"
)

// Two completed tool turns with provider-owned reasoning around each call.
// IDs deliberately include both rs_* and a provider namespace; the numeric
// extension catches accidental float64 decoding of opaque replay metadata.
const compatibleReasoningHistory = `[
	{"type":"reasoning","id":"rs_native_one","namespace":"provider.reasoning","summary":[],"content":[{"type":"reasoning_text","text":"first thought"}],"opaque":9007199254740993},
	{"type":"function_call","id":"fc_one","call_id":"call_one","name":"lookup","arguments":"{}"},
	{"type":"function_call_output","call_id":"call_one","output":"first result"},
	{"type":"reasoning","id":"mimo_native_two","namespace":{"provider":"mimo"},"encrypted_content":null,"summary":[],"content":[{"type":"reasoning_text","text":"second thought"}]},
	{"type":"function_call","id":"fc_two","call_id":"call_two","name":"lookup","arguments":"{}"},
	{"type":"function_call_output","call_id":"call_two","output":"second result"},
	{"type":"reasoning","id":"rs_cipher","namespace":"provider.cipher","encrypted_content":"opaque-provider-cipher","summary":null,"content":[{"type":"reasoning_text","text":"cipher companion"}]},
	{"type":"item_reference","id":"rs_native_one"},
	{"type":"message","id":"invalid_message","call_id":"non_pair","role":"user","content":"continue"}
]`

func compatibleReasoningRequest(store string) []byte {
	return []byte(`{"model":"mimo-v2.6-pro","stream":false,` + store +
		`"input":` + compatibleReasoningHistory + `}`)
}

func assertCompatibleReplay(t *testing.T, forwarded []byte, preserved bool, storeFalse bool) {
	t.Helper()
	items := gjson.GetBytes(forwarded, "input").Array()
	var reasoning, tools []gjson.Result
	for _, item := range items {
		switch item.Get("type").String() {
		case "reasoning":
			reasoning = append(reasoning, item)
		case "function_call", "function_call_output":
			tools = append(tools, item)
		}
	}
	original := gjson.Parse(compatibleReasoningHistory).Array()
	require.Len(t, tools, 4)
	for i, index := range []int{1, 2, 4, 5} {
		require.JSONEq(t, original[index].Raw, tools[i].Raw, "paired tool history changed")
	}
	if preserved {
		require.Len(t, items, len(original), "full input interleaving changed")
		for i, expected := range original {
			require.Equal(t, expected.Get("type").String(), items[i].Get("type").String(), "input type/order at %d", i)
			if expected.Get("type").String() != "message" {
				require.JSONEq(t, expected.Raw, items[i].Raw, "full input history at %d", i)
			}
		}
		require.Len(t, reasoning, 3)
		for i, index := range []int{0, 3, 6} {
			require.JSONEq(t, original[index].Raw, reasoning[i].Raw, "provider reasoning changed")
		}
		require.Equal(t, "9007199254740993", reasoning[0].Get("opaque").Raw)
		require.JSONEq(t, original[7].Raw, items[7].Raw, "reasoning reference lost")
	} else {
		if storeFalse {
			require.Len(t, reasoning, 1, "legacy store=false must drop plain reasoning")
			require.False(t, reasoning[0].Get("id").Exists())
			require.True(t, reasoning[0].Get("summary").IsArray())
		} else {
			require.Len(t, reasoning, 3)
		}
		for _, item := range reasoning {
			require.False(t, item.Get("content").Exists(), "legacy content sanitation lost")
		}
	}
	// Opt-in is not a global sanitizer bypass.
	last := items[len(items)-1]
	require.False(t, last.Get("id").Exists())
	require.False(t, last.Get("call_id").Exists())
	require.Equal(t, "continue", last.Get("content").String())
	require.JSONEq(t, `{"type":"message","role":"user","content":"continue"}`, last.Raw, "expected message sanitation")
}

func TestCompatibleReasoningPolicyHTTP(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, passthrough := range []bool{false, true} {
		for _, tc := range []struct {
			name      string
			policy    any
			store     string
			preserved bool
		}{
			{"opt_in_store_false", true, `"store":false,`, true},
			{"opt_in_store_true", true, `"store":true,`, true},
			{"opt_in_store_missing", true, "", true},
			{"missing_default", nil, `"store":false,`, false},
			{"explicit_false", false, `"store":false,`, false},
			{"string_is_not_opt_in", "true", `"store":false,`, false},
		} {
			t.Run(fmt.Sprintf("passthrough_%t/%s", passthrough, tc.name), func(t *testing.T) {
				upstream := &httpUpstreamRecorder{resp: &http.Response{
					StatusCode: http.StatusOK,
					Header:     http.Header{"Content-Type": []string{"application/json"}},
					Body:       io.NopCloser(strings.NewReader(`{"id":"resp_test","model":"mimo-v2.6-pro","output":[],"usage":{"input_tokens":1,"output_tokens":1}}`)),
				}}
				svc := newOpenAIImageGenerationControlTestService(upstream)
				c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
				account := newOpenAIImageGenerationControlTestAccount()
				account.Extra = map[string]any{"openai_passthrough": passthrough}
				if tc.policy != nil {
					account.Extra["openai_preserve_compatible_reasoning"] = tc.policy
				}
				// A caller's body/header cannot override the trusted account.
				body := compatibleReasoningRequest(tc.store)
				body = append([]byte(`{"openai_preserve_compatible_reasoning":true,"extra":{"openai_preserve_compatible_reasoning":true},`), body[1:]...)
				c.Request.Header.Set("Openai-Preserve-Compatible-Reasoning", "true")
				_, err := svc.Forward(context.Background(), c, account, body)
				require.NoError(t, err)
				require.NotNil(t, upstream.lastReq)
				require.Equal(t, "/v1/responses", upstream.lastReq.URL.Path)
				assertCompatibleReplay(t, upstream.lastBody, tc.preserved, tc.store == `"store":false,`)
			})
		}
	}
}

func TestCompatibleReasoningPolicyWebSocketPreparation(t *testing.T) {
	for _, tc := range []struct {
		name      string
		policy    any
		preserved bool
	}{
		{"opt_in", true, true},
		{"missing_default", nil, false},
		{"explicit_false", false, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			account := newOpenAIImageGenerationControlTestAccount()
			account.Extra = map[string]any{"openai_preserve_compatible_reasoning": tc.policy}
			body := compatibleReasoningRequest(`"store":false,`)
			body = append([]byte(`{"type":"response.create",`), body[1:]...)
			normalized, _, err := normalizeOpenAIResponsesWebSocketCompatibilityBody(body, account, false)
			require.NoError(t, err)
			assertCompatibleReplay(t, normalized, tc.preserved, true)
			// WS-to-HTTP preparation must retain the same history too.
			bridged, err := prepareOpenAIWSHTTPBridgeBody(account, normalized)
			require.NoError(t, err)
			assertCompatibleReplay(t, bridged, tc.preserved, true)
		})
	}
}

func TestCompatibleReasoningPolicyOAuthIgnored(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, accountType := range []string{AccountTypeOAuth, AccountTypeSetupToken} {
		t.Run(accountType, func(t *testing.T) {
			var baselineHTTP, baselineWS string
			for _, optIn := range []bool{false, true} {
				account := newOpenAIImageGenerationControlTestAccount()
				account.Type = accountType
				account.Credentials = map[string]any{"access_token": "synthetic-token", "chatgpt_account_id": "synthetic-account"}
				account.Extra = map[string]any{"openai_passthrough": true, "openai_preserve_compatible_reasoning": optIn}
				body := compatibleReasoningRequest(`"store":false,`)
				wsBody, _, err := normalizeOpenAIResponsesWebSocketCompatibilityBody(body, account, false)
				require.NoError(t, err)
				stream := "data: {\"type\":\"response.completed\",\"response\":{\"id\":\"resp_test\",\"model\":\"mimo-v2.6-pro\",\"output\":[],\"usage\":{\"input_tokens\":1,\"output_tokens\":1}}}\n\ndata: [DONE]\n\n"
				upstream := &httpUpstreamRecorder{resp: &http.Response{StatusCode: http.StatusOK, Header: http.Header{"Content-Type": []string{"text/event-stream"}}, Body: io.NopCloser(strings.NewReader(stream))}}
				svc := newOpenAIImageGenerationControlTestService(upstream)
				c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
				_, err = svc.Forward(context.Background(), c, account, body)
				require.NoError(t, err)
				require.NotNil(t, upstream.lastReq)
				require.Equal(t, "https://chatgpt.com/backend-api/codex/responses", upstream.lastReq.URL.String())
				if !optIn {
					baselineHTTP = gjson.GetBytes(upstream.lastBody, "input").Raw
					baselineWS = gjson.GetBytes(wsBody, "input").Raw
				} else {
					require.JSONEq(t, baselineHTTP, gjson.GetBytes(upstream.lastBody, "input").Raw)
					require.JSONEq(t, baselineWS, gjson.GetBytes(wsBody, "input").Raw)
					require.False(t, gjson.GetBytes(upstream.lastBody, "input.0.content").Exists())
				}
			}
		})
	}
}

func TestCompatibleReasoningPolicyMalformedRejected(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, body := range [][]byte{
		[]byte(`{"model":"mimo-v2.6-pro","input":[{"type":"reasoning","content":[{"text":"broken"}]}]`),
		append(compatibleReasoningRequest(`"store":false,`), []byte(` {"trailing":true}`)...),
	} {
		account := newOpenAIImageGenerationControlTestAccount()
		account.Extra = map[string]any{"openai_passthrough": true, "openai_preserve_compatible_reasoning": true}
		upstream := &httpUpstreamRecorder{}
		svc := newOpenAIImageGenerationControlTestService(upstream)
		c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
		_, err := svc.Forward(context.Background(), c, account, body)
		require.Error(t, err)
		require.Nil(t, upstream.lastReq, "malformed opt-in request reached upstream")
		_, _, err = normalizeOpenAIResponsesWebSocketCompatibilityBody(body, account, false)
		require.Error(t, err)
	}
}

func TestCompatibleReasoningPolicyRouteScope(t *testing.T) {
	for _, tc := range []struct {
		name     string
		platform string
		extra    map[string]any
	}{
		{"other_platform", PlatformAnthropic, map[string]any{}},
		{"probe_denied_responses", PlatformOpenAI, map[string]any{"openai_responses_supported": false}},
		{"forced_chat_completions", PlatformOpenAI, map[string]any{"openai_responses_mode": "force_chat_completions", "openai_responses_supported": true}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			account := newOpenAIImageGenerationControlTestAccount()
			account.Platform = tc.platform
			account.Extra = tc.extra
			body := compatibleReasoningRequest(`"store":false,`)
			baseline, _, err := normalizeOpenAIResponsesWebSocketCompatibilityBody(body, account, false)
			require.NoError(t, err)
			account.Extra["openai_preserve_compatible_reasoning"] = true
			flagged, _, err := normalizeOpenAIResponsesWebSocketCompatibilityBody(body, account, false)
			require.NoError(t, err)
			require.Equal(t, string(baseline), string(flagged), "non-native account accepted opt-in")
		})
	}
}
