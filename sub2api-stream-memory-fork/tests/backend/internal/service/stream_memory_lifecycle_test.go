package service

import (
	"context"
	"io"
	"net/http"
	"os"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/config"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func memorySpoolFDCount(t *testing.T, dir string) int {
	t.Helper()
	entries, err := os.ReadDir("/proc/self/fd")
	require.NoError(t, err)
	n := 0
	for _, entry := range entries {
		target, err := os.Readlink("/proc/self/fd/" + entry.Name())
		if err == nil && strings.HasPrefix(target, dir+"/sub2api-openai-first-output-") {
			n++
		}
	}
	return n
}

func TestStreamMemoryResponsesSpoolCancelAndDeadline(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("actual descriptor ownership regression uses procfs")
	}
	for _, deadline := range []bool{false, true} {
		t.Run(map[bool]string{false: "cancel", true: "deadline"}[deadline], func(t *testing.T) {
			dir := t.TempDir()
			t.Setenv("TMPDIR", dir)
			// Reaching the next read proves the previous >64KiB prefix was staged.
			body := newMemoryGatedBody([]string{":" + strings.Repeat("p", 80000) + "\n", ": unread\n"}, 1)
			defer body.Close()
			ctx, cancel := context.WithCancel(context.Background())
			if deadline {
				cancel()
				ctx, cancel = context.WithTimeout(context.Background(), time.Second)
			}
			defer cancel()
			c, rec := memoryContext()
			done := make(chan struct{})
			var gotErr error
			go func() {
				defer close(done)
				_, gotErr = (&OpenAIGatewayService{cfg: &config.Config{Gateway: config.GatewayConfig{MaxLineSize: defaultMaxLineSize}}}).handleStreamingResponsePassthrough(ctx, &http.Response{StatusCode: 200, Header: http.Header{}, Body: body}, c, &Account{ID: 1, Platform: PlatformOpenAI}, time.Now(), "", "")
			}()
			memoryAwait(t, body.reached)
			require.Equal(t, 1, memorySpoolFDCount(t, dir), "actual handler must own one anonymous spool while prefix is pending")
			if !deadline {
				cancel()
			}
			select {
			case <-done:
			case <-time.After(3 * time.Second):
				t.Error("prefix request deadline/cancel did not stop blocked read")
				body.Close()
			}
			memoryAwait(t, done)
			if deadline {
				require.ErrorIs(t, gotErr, context.DeadlineExceeded)
			} else {
				require.ErrorIs(t, gotErr, context.Canceled)
			}
			require.Empty(t, rec.Body.String())
			require.Zero(t, memorySpoolFDCount(t, dir), "handler exit must close the prefix descriptor")
		})
	}
}

type memoryJoinedBody struct {
	io.Reader
	parts []*memoryGatedBody
}

func (b *memoryJoinedBody) Close() error {
	for _, part := range b.parts {
		_ = part.Close()
	}
	return nil
}

func TestStreamMemoryResponsesSpoolReleasedBeforeTerminal(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("actual descriptor ownership regression uses procfs")
	}
	dir := t.TempDir()
	t.Setenv("TMPDIR", dir)
	prefix := ":" + strings.Repeat("p", 80000) + "\n"
	first := `data: {"type":"response.output_text.delta","delta":"ready"}` + "\n\n"
	terminal := `data: {"type":"response.completed","response":{"usage":{"input_tokens":7,"output_tokens":5}}}` + "\n\n"
	before := newMemoryGatedBody([]string{prefix, first}, 1)
	after := newMemoryGatedBody([]string{terminal}, 0)
	body := &memoryJoinedBody{Reader: io.MultiReader(before, after), parts: []*memoryGatedBody{before, after}}
	defer body.Close()
	defer func() {
		select {
		case <-before.release:
		default:
			close(before.release)
		}
		select {
		case <-after.release:
		default:
			close(after.release)
		}
	}()
	c, rec := memoryContext()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	var result *openaiStreamingResultPassthrough
	var gotErr error
	go func() {
		defer close(done)
		result, gotErr = (&OpenAIGatewayService{cfg: &config.Config{Gateway: config.GatewayConfig{MaxLineSize: defaultMaxLineSize}}}).handleStreamingResponsePassthrough(ctx, &http.Response{StatusCode: 200, Header: http.Header{}, Body: body}, c, &Account{ID: 1, Platform: PlatformOpenAI}, time.Now(), "", "")
	}()
	memoryAwait(t, before.reached)
	require.Equal(t, 1, memorySpoolFDCount(t, dir))
	close(before.release)
	memoryAwait(t, after.reached)
	require.Zero(t, memorySpoolFDCount(t, dir), "flushed prefix must not retain descriptor through the rest of request")
	// Once semantic output is committed the previous usage-drain policy remains.
	cancel()
	close(after.release)
	memoryAwait(t, done)
	require.NoError(t, gotErr)
	require.Equal(t, prefix+first+terminal, rec.Body.String())
	require.Equal(t, 7, result.usage.InputTokens)
	require.Equal(t, 5, result.usage.OutputTokens)
}

type memoryKeepaliveWriter struct {
	gin.ResponseWriter
	beats chan struct{}
}

func (w *memoryKeepaliveWriter) Flush() {
	w.ResponseWriter.Flush()
	select {
	case w.beats <- struct{}{}:
	default:
	}
}

func TestStreamMemoryResponsesPrefixKeepaliveDoesNotReplayPrefix(t *testing.T) {
	prefix := strings.Repeat(": upstream prefix\n", 5000)
	first := `data: {"type":"response.output_text.delta","delta":"ready"}` + "\n\n"
	terminal := `data: {"type":"response.completed","response":{"usage":{"input_tokens":2,"output_tokens":1}}}` + "\n\n"
	body := newMemoryGatedBody([]string{prefix, first, terminal}, 1)
	defer body.Close()
	defer func() {
		select {
		case <-body.release:
		default:
			close(body.release)
		}
	}()
	c, rec := memoryContext()
	w := &memoryKeepaliveWriter{ResponseWriter: c.Writer, beats: make(chan struct{}, 8)}
	c.Writer = w
	done := make(chan struct{})
	var gotErr error
	go func() {
		defer close(done)
		_, gotErr = (&OpenAIGatewayService{cfg: &config.Config{Gateway: config.GatewayConfig{MaxLineSize: defaultMaxLineSize, StreamKeepaliveInterval: 1}}}).handleStreamingResponsePassthrough(context.Background(), &http.Response{StatusCode: 200, Header: http.Header{}, Body: body}, c, &Account{ID: 1, Platform: PlatformOpenAI}, time.Now(), "", "")
	}()
	memoryAwait(t, body.reached)
	memoryAwait(t, w.beats)
	// The existing keepalive stop synchronizes access to the writer; no raceful
	// reading of ResponseRecorder while the keepalive goroutine writes it.
	require.True(t, StopOpenAICompactSSEKeepaliveCommitted(c))
	beats := rec.Body.String()
	require.NotEmpty(t, beats)
	require.Equal(t, strings.Repeat(": keepalive\n\n", strings.Count(beats, ": keepalive\n\n")), beats)
	require.False(t, openAIStreamClientOutputStarted(c, false))
	close(body.release)
	memoryAwait(t, done)
	require.NoError(t, gotErr)
	require.Equal(t, beats+prefix+first+terminal, rec.Body.String())
}

func TestStreamMemoryResponsesSpoolWriterErrorCleanupAndUsage(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("actual descriptor ownership regression uses procfs")
	}
	dir := t.TempDir()
	t.Setenv("TMPDIR", dir)
	prefix := ":" + strings.Repeat("p", 80000) + "\n"
	first := `data: {"type":"response.output_text.delta","delta":"ready"}` + "\n\n"
	terminal := `data: {"type":"response.completed","response":{"usage":{"input_tokens":7,"output_tokens":5}}}` + "\n\n"
	r, rec, _, err := runPassthroughFlushTest(t, io.NopCloser(strings.NewReader(prefix+first+terminal)), 0)
	require.NoError(t, err)
	require.Empty(t, rec.Body.String())
	require.Equal(t, 7, r.usage.InputTokens)
	require.Equal(t, 5, r.usage.OutputTokens)
	require.Zero(t, memorySpoolFDCount(t, dir), "failed prefix replay must close spool while usage is drained")
}
