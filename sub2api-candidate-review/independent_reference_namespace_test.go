//go:build unit

package service

import (
	"context"
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/tidwall/gjson"
)

// Prescription for the coordinator's existing pinned unit gate. Not executed
// by this read-only reviewer: Go, sockets and image execution are out of scope.
func TestIndependentCompatibleReferenceNamespaceHTTP(t *testing.T) {
	const body = `{"model":"mimo-v2.6-pro","stream":false,"store":true,"input":[{"type":"item_reference","id":"rs_provider","namespace":{"provider":"opaque"},"extension":9007199254740993},{"type":"message","role":"user","content":"continue","namespace":"ordinary"}]}`
	for _, passthrough := range []bool{false, true} {
		for _, optIn := range []bool{false, true} {
			t.Run(fmt.Sprintf("pass_%t/opt_%t", passthrough, optIn), func(t *testing.T) {
				upstream := &httpUpstreamRecorder{resp: compatibleReviewResponse(200, `{"id":"resp_independent","output":[],"usage":{"input_tokens":1,"output_tokens":1}}`)}
				svc := newOpenAIImageGenerationControlTestService(upstream)
				account := newOpenAIImageGenerationControlTestAccount()
				account.Extra = map[string]any{"openai_passthrough": passthrough, "openai_preserve_compatible_reasoning": optIn}
				c, _ := newOpenAIImageGenerationControlTestContext(true, "unit-test-agent/1.0")
				_, err := svc.Forward(context.Background(), c, account, []byte(body))
				require.NoError(t, err)
				require.NotNil(t, upstream.lastReq)
				reference := gjson.GetBytes(upstream.lastBody, "input.0")
				require.Equal(t, optIn, reference.Get("namespace").Exists(), "opted-in reference namespace must survive the initial HTTP pass")
				require.Equal(t, "9007199254740993", reference.Get("extension").Raw)
				require.False(t, gjson.GetBytes(upstream.lastBody, "input.1.namespace").Exists(), "ordinary sanitation remains enabled")
				if optIn {
					var before, after any
					require.NoError(t, decodeOpenAIJSONUseNumber([]byte(gjson.Get(body, "input.0").Raw), &before))
					require.NoError(t, decodeOpenAIJSONUseNumber([]byte(reference.Raw), &after))
					require.Equal(t, before, after)
				}
			})
		}
	}
}
