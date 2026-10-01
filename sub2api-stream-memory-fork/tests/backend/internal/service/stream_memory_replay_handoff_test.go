// Controller-only proposed regression: copy into a disposable service test tree.
// NOT EXECUTED by this reviewer. Uses the old service API and no production hooks.
package service

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/config"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

type subreviewCancelErrorWriter struct {
	gin.ResponseWriter
	cancel         context.CancelFunc
	failOnSemantic bool
	failed         bool
}

func (w *subreviewCancelErrorWriter) Write(p []byte) (int, error) {
	if !w.failed && (!w.failOnSemantic || bytes.Contains(p, []byte("response.output_text.delta"))) {
		w.failed = true
		w.cancel()
		return 0, errors.New("downstream closed after prefix ownership handoff")
	}
	return w.ResponseWriter.Write(p)
}
func (w *subreviewCancelErrorWriter) WriteString(p string) (int, error) {
	return w.Write([]byte(p))
}

func TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain(t *testing.T) {
	for _, semantic := range []bool{false, true} {
		t.Run(map[bool]string{false: "prefix_writer_error", true: "first_semantic_writer_error"}[semantic], func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			rec := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(rec)
			c.Request = httptest.NewRequest(http.MethodPost, "/v1/responses", nil)
			w := &subreviewCancelErrorWriter{ResponseWriter: c.Writer, cancel: cancel, failOnSemantic: semantic}
			c.Writer = w
			prefix := ":" + strings.Repeat("p", 80000) + "\n"
			first := `data: {"type":"response.output_text.delta","delta":"ready"}` + "\n\n"
			terminal := `data: {"type":"response.completed","response":{"usage":{"input_tokens":7,"output_tokens":5}}}` + "\n\n"
			resp := &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(prefix + first + terminal))}
			defer resp.Body.Close()
			s := &OpenAIGatewayService{cfg: &config.Config{Gateway: config.GatewayConfig{MaxLineSize: defaultMaxLineSize}}}
			r, err := s.handleStreamingResponsePassthrough(ctx, resp, c, &Account{ID: 1, Platform: PlatformOpenAI}, time.Now(), "", "")
			require.True(t, w.failed)
			require.ErrorIs(t, ctx.Err(), context.Canceled)
			// The existing downstream-disconnect policy drains upstream terminal usage.
			// Source predicts old PASS, frozen new FAIL at the added ctx.Err guards.
			require.NoError(t, err)
			require.NotNil(t, r)
			require.Equal(t, 7, r.usage.InputTokens)
			require.Equal(t, 5, r.usage.OutputTokens)
		})
	}
}
