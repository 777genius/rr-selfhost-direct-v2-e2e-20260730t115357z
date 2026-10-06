package service

import (
	"context"
	"crypto/sha256"
	"hash"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/config"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

// Hash all delivered bytes without retaining a transcript. Memory assertions in
// stage tests remain independent of this functional whole-volume oracle.
type memoryHashSink struct {
	header     http.Header
	digest     hash.Hash
	bytes      int64
	flushBytes []int64
}

func (s *memoryHashSink) Header() http.Header { return s.header }
func (s *memoryHashSink) WriteHeader(int)     {}
func (s *memoryHashSink) Write(p []byte) (int, error) {
	n, err := s.digest.Write(p)
	s.bytes += int64(n)
	return n, err
}
func (s *memoryHashSink) Flush() { s.flushBytes = append(s.flushBytes, s.bytes) }

func TestStreamMemoryMessagesFullVolumes(t *testing.T) {
	for _, native := range []bool{false, true} {
		for _, mib := range []int{8, 32, 64} {
			label := "passthrough"
			if native {
				label = "native"
			}
			t.Run(label+"/"+map[int]string{8: "8MiB", 32: "32MiB", 64: "64MiB"}[mib], func(t *testing.T) {
				start := `data: {"type":"message_start","message":{"usage":{"input_tokens":11}}}` + "\n\n"
				// A large valid tool argument is a semantic near-2MiB frame, not just padding.
				tool := `data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"toolu_9007199254740993","name":"lookup","input":{"payload":"` + strings.Repeat("z", 1998000) + `"}}}` + "\n\n"
				terminal := `data: {"type":"message_delta","usage":{"output_tokens":17}}` + "\n\ndata: {\"type\":\"message_stop\"}\n\n"
				total := mib * 1024 * 1024
				remaining := total - len(start) - len(tool) - len(terminal)
				comment := ":" + strings.Repeat("c", 65532) + "\n\n"
				parts := []string{start, tool}
				for remaining >= len(comment) {
					parts = append(parts, comment)
					remaining -= len(comment)
				}
				require.GreaterOrEqual(t, remaining, 3)
				parts = append(parts, ":"+strings.Repeat("r", remaining-3)+"\n\n", terminal)
				readers := make([]io.Reader, 0, len(parts))
				want := sha256.New()
				for _, p := range parts {
					readers = append(readers, strings.NewReader(p))
					_, _ = io.WriteString(want, p)
				}
				sink := &memoryHashSink{header: make(http.Header), digest: sha256.New()}
				c, _ := gin.CreateTestContext(sink)
				cfg := &config.Config{Gateway: config.GatewayConfig{MaxLineSize: defaultMaxLineSize}}
				resp := &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(io.MultiReader(readers...))}
				a := &Account{ID: 1, Platform: PlatformAnthropic}
				if native {
					r, err := (&OpenAIGatewayService{cfg: cfg}).handleNativeAnthropicStreamingResponse(context.Background(), resp, c, a, "m", "m", "m", nil, time.Now())
					require.NoError(t, err)
					require.Equal(t, 11, r.Usage.InputTokens)
					require.Equal(t, 17, r.Usage.OutputTokens)
				} else {
					r, err := (&GatewayService{cfg: cfg}).handleStreamingResponseAnthropicAPIKeyPassthrough(context.Background(), resp, c, a, time.Now(), "m")
					require.NoError(t, err)
					require.Equal(t, 11, r.usage.InputTokens)
					require.Equal(t, 17, r.usage.OutputTokens)
				}
				require.EqualValues(t, total, sink.bytes)
				require.Equal(t, want.Sum(nil), sink.digest.Sum(nil), "every byte, including opaque tool ID and terminal, must match")
				// Same complete-event flush positions, including the existing EOF safety flush.
				var expected []int64
				var offset int64
				for _, p := range parts {
					for _, line := range strings.SplitAfter(p, "\n") {
						offset += int64(len(line))
						if line == "\n" {
							expected = append(expected, offset)
						}
					}
				}
				expected = append(expected, int64(total))
				require.Equal(t, expected, sink.flushBytes)
			})
		}
	}
}
