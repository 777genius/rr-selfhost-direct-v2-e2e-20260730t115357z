//go:build unit

package service

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Wei-Shaw/sub2api/internal/config"
	"github.com/gin-gonic/gin"
)

// Fail only the first actual spilled-prefix replay write. Later writes succeed:
// a mutant that continues after losing BOTH trusted replay actions must remain
// blocked on the real held upstream. Withhold the SSE blank separator too:
// otherwise a buffered blank line reaches the intact disconnect guard.
type rrNativeMergedReplayFailure struct {
	at      time.Time
	spilled bool
	prefix  bool
}

type rrNativeMergedReplayWriter struct {
	gin.ResponseWriter
	t      *testing.T
	dir    string
	failed chan rrNativeMergedReplayFailure
	once   atomic.Bool
}

func (w *rrNativeMergedReplayWriter) Write(p []byte) (int, error) {
	if w.once.CompareAndSwap(false, true) {
		isPrefix := len(p) > 1 && p[0] == ':' && bytes.Equal(p[1:], bytes.Repeat([]byte("p"), len(p)-1))
		w.failed <- rrNativeMergedReplayFailure{time.Now(), memorySpoolFDCount(w.t, w.dir) == 1, isPrefix}
		return 0, io.ErrClosedPipe
	}
	return w.ResponseWriter.Write(p)
}

func (w *rrNativeMergedReplayWriter) WriteString(s string) (int, error) {
	return w.Write([]byte(s))
}

func TestNativeMergedSpilledPrefixWriterFailure(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("TMPDIR", dir)
	request := rrNativeRequest("responses")
	release, returned, canceled := make(chan struct{}), make(chan struct{}), make(chan struct{})
	var once sync.Once
	unblock := func() { once.Do(func() { close(release) }) }
	var effects atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer close(returned)
		wire, err := io.ReadAll(r.Body)
		if err != nil || !bytes.Contains(wire, []byte("9007199254740993")) || !bytes.Contains(wire, []byte("rs_mimo")) {
			t.Errorf("full protected request missing: %v", err)
		}
		effects.Add(1)
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = io.WriteString(w, ":"+strings.Repeat("p", 80000)+"\n")
		// A complete JSON line triggers replay; hold the next scanner token.
		_, _ = io.WriteString(w, "data: {\"type\":\"response.output_text.delta\",\"delta\":\"ready\"}\n")
		w.(http.Flusher).Flush()
		select {
		case <-r.Context().Done():
			close(canceled)
		case <-release:
			_, terminal := rrNativeFrames("responses")
			_, _ = io.WriteString(w, "\n"+terminal)
		}
	}))
	t.Cleanup(server.Close)
	t.Cleanup(unblock)
	address, _ := url.Parse(server.URL)
	u := &rrNativeTransport{client: server.Client(), target: address, body: make(chan *rrNativeBody, 2)}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	c, _ := gin.CreateTestContext(httptest.NewRecorder())
	c.Request = httptest.NewRequest(http.MethodPost, "/v1/responses", bytes.NewReader(request)).WithContext(ctx)
	writer := &rrNativeMergedReplayWriter{ResponseWriter: c.Writer, t: t, dir: dir, failed: make(chan rrNativeMergedReplayFailure, 1)}
	c.Writer = writer
	s := &OpenAIGatewayService{cfg: &config.Config{}, httpUpstream: u}
	result := make(chan rrNativeResult, 1)
	go func() {
		res, err := s.forwardOpenAIPassthrough(ctx, c, rrNativeAccount("responses", true), request, request, "mimo-v2.6-pro", false, nil, true, time.Now())
		if res == nil {
			result <- rrNativeResult{err: err}
			return
		}
		result <- rrNativeResult{true, res.Usage.InputTokens, res.Usage.OutputTokens, res.ClientDisconnect, err}
	}()
	var body *rrNativeBody
	select {
	case body = <-u.body:
		t.Cleanup(func() { _ = body.Close() })
	case <-time.After(3 * time.Second):
		t.Fatal("real upstream response missing")
	}
	var failure rrNativeMergedReplayFailure
	select {
	case failure = <-writer.failed:
	case <-time.After(3 * time.Second):
		t.Fatal("spilled prefix replay never reached writer")
	}
	if !failure.spilled || !failure.prefix {
		t.Fatalf("failure did not occur during actual anonymous spool replay: %+v", failure)
	}
	deadline := failure.at.Add(rrNativeCancelOracle)
	var got rrNativeResult
	select {
	case got = <-result:
	case <-time.After(time.Until(deadline)):
		// A held-forward timeout is behavioral RED only with an actual live
		// body Read, live caller, held server and exactly one accepted effect.
		if ctx.Err() != nil || body.active.Load() == 0 || effects.Load() != 1 || u.attempts.Load() != 1 {
			t.Fatal("replay fault did not leave the real accepted attempt in held Read")
		}
		select {
		case <-body.closed:
			t.Fatal("replay fault timed out after real body was already closed")
		case <-returned:
			t.Fatal("replay fault timed out after held upstream already returned")
		default:
		}
		t.Fatal("native forward did not finish within the failure/cancellation oracle: actual held Read after replay loss")
	}
	if ctx.Err() != nil {
		t.Fatal("independent caller context was canceled")
	}
	var failover *UpstreamFailoverError
	if got.err == nil || errors.As(got.err, &failover) || got.known || got.input != 0 || got.output != 0 {
		t.Fatalf("accepted incomplete attempt exposed retry or known usage: %+v", got)
	}
	rrNativeGapClosed(t, body, deadline)
	rrNativeWait(t, canceled, time.Until(deadline), "upstream cancellation after replay failure")
	rrNativeWait(t, returned, time.Until(deadline), "real upstream returned")
	if effects.Load() != 1 || u.attempts.Load() != 1 {
		t.Fatalf("unexpected effects/attempts: %d/%d", effects.Load(), u.attempts.Load())
	}
}
