//go:build rrsub2profile && linux

package main

// Disposable sandbox instrumentation. No HTTP handler, GC request, memory
// tuning, request values, stack arguments, or environment output.
import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"runtime/pprof"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

type rrSample struct {
	Schema         uint64  `json:"schema"`
	Sequence       uint64  `json:"sequence"`
	PID            int     `json:"pid"`
	StartMS        float64 `json:"start_ms"`
	EndMS          float64 `json:"end_ms"`
	DurationMS     float64 `json:"duration_ms"`
	HeapAlloc      uint64  `json:"heap_alloc"`
	HeapObjects    uint64  `json:"heap_objects"`
	HeapInuse      uint64  `json:"heap_inuse"`
	HeapIdle       uint64  `json:"heap_idle"`
	HeapReleased   uint64  `json:"heap_released"`
	HeapSys        uint64  `json:"heap_sys"`
	TotalAlloc     uint64  `json:"total_alloc"`
	Mallocs        uint64  `json:"mallocs"`
	Frees          uint64  `json:"frees"`
	Sys            uint64  `json:"sys"`
	StackInuse     uint64  `json:"stack_inuse"`
	StackSys       uint64  `json:"stack_sys"`
	NextGC         uint64  `json:"next_gc"`
	NumGC          uint32  `json:"num_gc"`
	NumForcedGC    uint32  `json:"num_forced_gc"`
	LastGC         uint64  `json:"last_gc_unix_ns"`
	PauseTotal     uint64  `json:"pause_total_ns"`
	Goroutines     int     `json:"goroutines"`
	MemProfileRate int     `json:"mem_profile_rate"`
}

type rrProfiler struct {
	dir      string
	mu       sync.Mutex
	enc      *json.Encoder
	sequence uint64
}

func rrAbort() { os.Exit(97) } // No error text or environment values.
func rrMono() float64 {
	var t syscall.Timespec
	_, _, e := syscall.Syscall(syscall.SYS_CLOCK_GETTIME, 1, uintptr(unsafe.Pointer(&t)), 0)
	if e != 0 {
		rrAbort()
	}
	return float64(t.Sec)*1000 + float64(t.Nsec)/1e6
}
func rrNew(name string) *os.File {
	f, e := os.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		rrAbort()
	}
	return f
}
func (p *rrProfiler) sample() rrSample {
	p.mu.Lock()
	defer p.mu.Unlock()
	start := rrMono()
	var m runtime.MemStats
	runtime.ReadMemStats(&m) // Current allocator counters, NOT current reachability.
	n := runtime.NumGoroutine()
	end := rrMono()
	p.sequence++
	s := rrSample{1, p.sequence, os.Getpid(), start, end, end - start,
		m.HeapAlloc, m.HeapObjects, m.HeapInuse, m.HeapIdle, m.HeapReleased, m.HeapSys,
		m.TotalAlloc, m.Mallocs, m.Frees, m.Sys, m.StackInuse, m.StackSys,
		m.NextGC, m.NumGC, m.NumForcedGC, m.LastGC, m.PauseTotalNs, n, runtime.MemProfileRate}
	if p.enc.Encode(s) != nil {
		rrAbort()
	}
	return s
}

// WriteTo(debug=0) is a sampled binary protobuf profile. The matching runtime
// flushes delayed profiler buckets; it does NOT request a fresh GC. The heap
// data may lag by up to two GC cycles. Each kind gets its own bracketing samples.
type rrLimited struct {
	w    io.Writer
	left int64
}

func (w *rrLimited) Write(b []byte) (int, error) {
	if int64(len(b)) > w.left {
		return 0, io.ErrShortWrite
	}
	n, e := w.w.Write(b)
	w.left -= int64(n)
	return n, e
}
func (p *rrProfiler) checkpoint(id uint64) {
	rows := make([]map[string]any, 0, 3)
	for kind, name := range []string{"heap", "allocs", "goroutine"} {
		before := p.sample()
		f := rrNew(filepath.Join(p.dir, fmt.Sprintf("checkpoint-%03d-%s.pb.gz", id, name)))
		e := pprof.Lookup(name).WriteTo(&rrLimited{f, 8 << 20}, 0)
		closeErr := f.Close()
		if e != nil || closeErr != nil {
			rrAbort()
		}
		after := p.sample()
		rows = append(rows, map[string]any{"schema": 1, "checkpoint": id, "kind": kind + 1,
			"before_sequence": before.Sequence, "after_sequence": after.Sequence,
			"before_num_gc": before.NumGC, "after_num_gc": after.NumGC,
			"start_ms": before.EndMS, "end_ms": after.StartMS, "pid": os.Getpid()})
	}
	// Acknowledgement is atomic and appears only after all files are closed.
	temp := filepath.Join(p.dir, fmt.Sprintf("checkpoint-%03d.tmp", id))
	f := rrNew(temp)
	if json.NewEncoder(f).Encode(rows) != nil || f.Close() != nil {
		rrAbort()
	}
	if os.Rename(temp, filepath.Join(p.dir, fmt.Sprintf("checkpoint-%03d.json", id))) != nil {
		rrAbort()
	}
}
func init() {
	dir := os.Getenv("RR_SUB2_PROFILE_DIR")
	if dir == "" {
		rrAbort()
	} // Tagged binary cannot silently omit instrumentation.
	if runtime.Version() != "go1.27.1" || !filepath.IsAbs(dir) {
		rrAbort()
	}
	st, e := os.Lstat(dir)
	if e != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 || st.Mode().Perm() != 0700 {
		rrAbort()
	}
	f := rrNew(filepath.Join(dir, "runtime.ndjson"))
	p := &rrProfiler{dir: dir, enc: json.NewEncoder(f)}
	p.sample()
	go func() {
		tick := time.NewTicker(100 * time.Millisecond)
		defer tick.Stop()
		// Hard instrumentation bound, independent of the root 600s supervisor.
		limit := time.NewTimer(650 * time.Second)
		defer limit.Stop()
		for {
			select {
			case <-tick.C:
				p.sample()
			case <-limit.C:
				rrAbort()
			}
		}
	}()
	go func() {
		var next uint64
		tick := time.NewTicker(100 * time.Millisecond)
		defer tick.Stop()
		for range tick.C {
			b, e := os.ReadFile(filepath.Join(dir, "request"))
			if os.IsNotExist(e) {
				continue
			}
			if e != nil || len(b) > 16 {
				rrAbort()
			}
			value := strings.TrimSpace(string(b))
			id, e := strconv.ParseUint(value, 10, 64)
			if e != nil || value != strconv.FormatUint(id, 10) || id > 100 {
				rrAbort()
			}
			if next > 0 && id == next-1 {
				continue
			}
			if id != next {
				rrAbort()
			}
			p.checkpoint(id)
			next++
		}
	}()
}
