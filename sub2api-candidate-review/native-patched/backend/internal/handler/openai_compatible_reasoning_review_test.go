//go:build unit

package handler

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCompatibleReasoningReviewCrossMode(t *testing.T) {
	for _, optIn := range []bool{false, true} {
		t.Run(fmt.Sprint(optIn), func(t *testing.T) {
			h := &OpenAIGatewayHandler{}
			canonical := []byte(kiroReasoningCanonicalBody)
			state := &openAIPassthroughFailoverState{passthroughSeen: true}
			account := newOpenAIPassthroughAccount(5151, false)
			account.Extra["openai_preserve_compatible_reasoning"] = optIn
			body := h.deriveOpenAIForwardAttemptBody(nil, canonical, account, state)
			if optIn {
				require.Equal(t, canonical, body, "F1: real handler attempt must preserve opted-in ciphertext")
			} else {
				require.Zero(t, reasoningItemCount(t, body))
			}
			require.True(t, state.passthroughSeen)
			require.Equal(t, kiroReasoningCanonicalBody, string(canonical))
		})
	}
}
