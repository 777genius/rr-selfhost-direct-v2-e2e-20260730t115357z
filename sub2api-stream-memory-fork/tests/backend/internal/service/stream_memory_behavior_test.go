package service

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/config"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

// Every Read delivers at most one physical line. At the nominated line boundary
// the reader reports entry and waits for permission; no production hooks needed.
type memoryGatedBody struct {
	lines                    []string
	index, offset            int
	gateAt                   int
	reached, release, closed chan struct{}
	once                     sync.Once
	readLines                chan int
	closeOnce                sync.Once
}

func newMemoryGatedBody(lines []string, gateAt int) *memoryGatedBody {
	return &memoryGatedBody{lines: lines, gateAt: gateAt, reached: make(chan struct{}), release: make(chan struct{}), closed: make(chan struct{}), readLines: make(chan int, len(lines)+1)}
}
func (b *memoryGatedBody) Read(p []byte) (int, error) {
	if b.index == b.gateAt && b.offset == 0 {
		b.once.Do(func() { close(b.reached) })
		select {
		case <-b.release:
		case <-b.closed:
			return 0, context.Canceled
		}
	}
	select {
	case <-b.closed:
		return 0, context.Canceled
	default:
	}
	if b.index == len(b.lines) {
		return 0, io.EOF
	}
	n := copy(p, b.lines[b.index][b.offset:])
	b.offset += n
	if b.offset == len(b.lines[b.index]) {
		b.index++
		b.offset = 0
		b.readLines <- b.index
	}
	return n, nil
}
func (b *memoryGatedBody) Close() error {
	b.closeOnce.Do(func() { close(b.closed) })
	return nil
}

type memoryGatedWriter struct {
	gin.ResponseWriter
	entered, release chan struct{}
	once             sync.Once
	flushSizes       []int
	rec              *httptest.ResponseRecorder
}

func (w *memoryGatedWriter) Write(p []byte) (int, error) {
	w.once.Do(func() { close(w.entered); <-w.release })
	return w.ResponseWriter.Write(p)
}
func (w *memoryGatedWriter) WriteString(s string) (int, error) { return w.Write([]byte(s)) }
func (w *memoryGatedWriter) Flush() {
	w.ResponseWriter.Flush()
	w.flushSizes = append(w.flushSizes, w.rec.Body.Len())
}

func memoryAwait(t *testing.T, ch <-chan struct{}) {
	t.Helper()
	select {
	case <-ch:
	case <-time.After(5 * time.Second):
		t.Fatal("channel barrier timed out")
	}
}
func memoryContext() (*gin.Context, *httptest.ResponseRecorder) {
	rec := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(rec)
	c.Request = httptest.NewRequest(http.MethodPost, "/v1/messages", nil)
	return c, rec
}

// This behavioral test compiles against the frozen source and must be RED there:
// the 16-slot scanner requests physical line four while the writer is gated.
func TestStreamMemoryMessagesReadAhead(t *testing.T) {
	for _, native := range []bool{false, true} {
		name := "passthrough"
		if native {
			name = "native"
		}
		t.Run(name, func(t *testing.T) {
			// Near-2MiB physical lines retain their accepted size. No line cutoff.
			comment := ":" + strings.Repeat("x", 1998900) + "\n"
			lines := []string{`data: {"type":"message_start","message":{"usage":{"input_tokens":9}}}` + "\n", comment, comment, comment, "\n", `data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"toolu_memory_9007199254740993","name":"lookup","input":{}}}` + "\n", "\n", `data: {"type":"message_delta","usage":{"output_tokens":7}}` + "\n", "\n", `data: {"type":"message_stop"}` + "\n", "\n"}
			body := newMemoryGatedBody(lines, 3)
			defer body.Close()
			c, rec := memoryContext()
			w := &memoryGatedWriter{ResponseWriter: c.Writer, entered: make(chan struct{}), release: make(chan struct{}), rec: rec}
			c.Writer = w
			// Cleanup unblocks both sides even when the expected old RED fires.
			defer func() {
				select {
				case <-w.release:
				default:
					close(w.release)
				}
				select {
				case <-body.release:
				default:
					close(body.release)
				}
			}()
			cfg := &config.Config{Gateway: config.GatewayConfig{MaxLineSize: defaultMaxLineSize, StreamDataIntervalTimeout: 1}}
			var gotIn, gotOut int
			var gotErr error
			done := make(chan struct{})
			go func() {
				defer close(done)
				resp := &http.Response{StatusCode: 200, Header: http.Header{}, Body: body}
				account := &Account{ID: 1, Platform: PlatformAnthropic}
				if native {
					r, e := (&OpenAIGatewayService{cfg: cfg}).handleNativeAnthropicStreamingResponse(context.Background(), resp, c, account, "m", "m", "m", nil, time.Now())
					gotErr = e
					if r != nil {
						gotIn = r.Usage.InputTokens
						gotOut = r.Usage.OutputTokens
					}
				} else {
					r, e := (&GatewayService{cfg: cfg}).handleStreamingResponseAnthropicAPIKeyPassthrough(context.Background(), resp, c, account, time.Now(), "m")
					gotErr = e
					if r != nil {
						gotIn = r.usage.InputTokens
						gotOut = r.usage.OutputTokens
					}
				}
			}()
			memoryAwait(t, w.entered)
			for i := 1; i <= 3; i++ {
				select {
				case n := <-body.readLines:
					require.Equal(t, i, n)
				case <-time.After(5 * time.Second):
					t.Fatal("producer did not scan expected three lines")
				}
			}
			// Hold downstream longer than the upstream interval. Read-ahead must remain
			// bounded, and delivery backpressure must not be charged as upstream idle.
			select {
			case <-body.reached:
				t.Error("read-ahead exceeded one queued line plus one in-flight line")
			case <-time.After(1200 * time.Millisecond):
			}
			close(w.release)
			close(body.release)
			memoryAwait(t, done)
			require.NoError(t, gotErr)
			require.Equal(t, 9, gotIn)
			require.Equal(t, 7, gotOut)
			require.Equal(t, strings.Join(lines, ""), rec.Body.String())
			require.Contains(t, rec.Body.String(), "toolu_memory_9007199254740993")
			require.NotEmpty(t, w.flushSizes)
		})
	}
}

// Old RED: the unbounded prefix reaches the semantic read barrier; the patched
// reader rejects byte 8MiB+1 without emitting or silently truncating the prefix.
func TestStreamMemoryResponsesPrefixOverflow(t *testing.T) {
	line := ":" + strings.Repeat("p", 65534) + "\n" // exactly 64KiB including delimiter
	lines := make([]string, 0, 132)
	for i := 0; i < 128; i++ {
		lines = append(lines, line)
	}
	lines = append(lines, ": overflow\n", `data: {"type":"response.output_text.delta","delta":"ready"}`+"\n\n", `data: {"type":"response.completed","response":{"usage":{"input_tokens":5,"output_tokens":1}}}`+"\n\n")
	body := newMemoryGatedBody(lines, 129)
	defer body.Close()
	var gotErr error
	var output string
	done := make(chan struct{})
	go func() {
		defer close(done)
		_, rec, _, err := runPassthroughFlushTest(t, body, -1)
		gotErr = err
		output = rec.Body.String()
	}()
	select {
	case <-done:
	case <-body.reached:
		t.Error("unbounded prefix reached semantic read barrier")
		body.Close()
	case <-time.After(5 * time.Second):
		t.Error("prefix limit did not terminate promptly")
		body.Close()
	}
	memoryAwait(t, done)
	require.Error(t, gotErr)
	require.ErrorIs(t, gotErr, errOpenAIFirstOutputStageLimit)
	var replay *UpstreamFailoverError
	require.False(t, errors.As(gotErr, &replay), "accepted upstream uncertainty must not cause replay")
	require.Empty(t, output)
	memoryAwait(t, body.closed)
}

func TestStreamMemoryResponsesSpilledPrefixPreservesBytesAndFlush(t *testing.T) {
	prefix := strings.Repeat(": waiting with exact spacing\n\n", 3000) + "id: opaque-9007199254740993\nevent: response.created\ndata: {\"type\":\"response.created\",\"response\":{\"id\":\"r_memory\"}}\n\n"
	first := `data: {"type":"response.output_text.delta","delta":"ready"}` + "\n\n"
	last := `data: {"type":"response.completed","response":{"id":"r_memory","usage":{"input_tokens":5,"output_tokens":3}}}` + "\n\n"
	result, rec, w, err := runPassthroughFlushTest(t, io.NopCloser(strings.NewReader(prefix+first+last)), -1)
	require.NoError(t, err)
	require.Equal(t, prefix+first+last, rec.Body.String())
	require.Equal(t, []int{len(prefix) + len(first), len(prefix) + len(first) + len(last)}, w.flushBodyLengths)
	require.Equal(t, 5, result.usage.InputTokens)
	require.Equal(t, 3, result.usage.OutputTokens)
}

func TestStreamMemoryMessagesRealUpstreamIdle(t *testing.T) {
	for _, native := range []bool{false, true} {
		t.Run(map[bool]string{false: "passthrough", true: "native"}[native], func(t *testing.T) {
			body := newMemoryGatedBody([]string{": never delivered\n"}, 0)
			defer body.Close()
			c, _ := memoryContext()
			cfg := &config.Config{Gateway: config.GatewayConfig{StreamDataIntervalTimeout: 1, MaxLineSize: defaultMaxLineSize}}
			done := make(chan struct{})
			var gotErr error
			go func() {
				defer close(done)
				resp := &http.Response{StatusCode: 200, Header: http.Header{}, Body: body}
				a := &Account{ID: 1, Platform: PlatformAnthropic}
				if native {
					_, gotErr = (&OpenAIGatewayService{cfg: cfg}).handleNativeAnthropicStreamingResponse(context.Background(), resp, c, a, "m", "m", "m", nil, time.Now())
				} else {
					_, gotErr = (&GatewayService{cfg: cfg}).handleStreamingResponseAnthropicAPIKeyPassthrough(context.Background(), resp, c, a, time.Now(), "m")
				}
			}()
			memoryAwait(t, body.reached)
			memoryAwait(t, done)
			require.ErrorContains(t, gotErr, "stream data interval timeout")
		})
	}
}

func TestStreamMemoryResponsesPrefixCancellationClosesReader(t *testing.T) {
	body := newMemoryGatedBody([]string{": waiting\n", ": not yet\n"}, 1)
	defer body.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	c, rec := memoryContext()
	cfg := &config.Config{Gateway: config.GatewayConfig{MaxLineSize: defaultMaxLineSize}}
	done := make(chan struct{})
	var gotErr error
	go func() {
		defer close(done)
		_, gotErr = (&OpenAIGatewayService{cfg: cfg}).handleStreamingResponsePassthrough(ctx, &http.Response{StatusCode: 200, Header: http.Header{}, Body: body}, c, &Account{ID: 1, Platform: PlatformOpenAI}, time.Now(), "", "")
	}()
	memoryAwait(t, body.reached)
	cancel()
	// Old RED must release its fake reader after reporting missing cancellation.
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Error("prefix cancellation did not close the upstream reader")
		body.Close()
	}
	memoryAwait(t, done)
	require.ErrorIs(t, gotErr, context.Canceled)
	require.Empty(t, rec.Body.String())
}
