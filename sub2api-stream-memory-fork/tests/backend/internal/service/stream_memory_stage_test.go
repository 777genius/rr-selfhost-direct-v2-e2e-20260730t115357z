package service

import (
	"bytes"
	"errors"
	"io"
	"os"
	"runtime"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

type memoryRejectWriter struct{}

func (memoryRejectWriter) Write([]byte) (int, error) {
	return 0, errors.New("downstream rejected prefix")
}

// Direct ownership assertions cover a separate resource invariant. They make no
// promise about the runtime heap, GC cadence, scavenging, or RSS return timing.
func TestStreamMemoryStrictStageOwnership(t *testing.T) {
	for _, mode := range []string{"commit", "rollback", "writer_error"} {
		t.Run(mode, func(t *testing.T) {
			if runtime.GOOS == "windows" {
				t.Skip("unlinked spool requires Unix")
			}
			s := newOpenAINativePrefixStage()
			defer s.Close()
			// Variable write sizes would otherwise allow a growing Buffer to overshoot
			// 64KiB capacity even though its logical length stays below that limit.
			for _, size := range []int{40000, 20000, 5536} {
				_, err := s.WriteString(strings.Repeat("a", size))
				require.NoError(t, err)
				require.LessOrEqual(t, s.memory.Cap(), 64*1024)
			}
			require.EqualValues(t, 65536, s.Buffered())
			_, err := s.WriteString("\n")
			require.NoError(t, err)
			fd, path := s.tempFile, s.tempPath
			require.NotNil(t, fd)
			require.Zero(t, s.memory.Cap(), "spill must release backing memory")
			stat, err := fd.Stat()
			require.NoError(t, err)
			require.Equal(t, os.FileMode(0600), stat.Mode().Perm())
			_, err = os.Stat(path)
			require.ErrorIs(t, err, os.ErrNotExist, "spool must already be unlinked")
			switch mode {
			case "commit":
				var out bytes.Buffer
				require.NoError(t, s.CommitTo(&out))
				require.Equal(t, strings.Repeat("a", 65536)+"\n", out.String())
			case "writer_error":
				require.Error(t, s.CommitTo(memoryRejectWriter{}))
				require.NoError(t, s.Close())
			case "rollback":
				require.NoError(t, s.Close())
			}
			require.True(t, s.closed)
			require.Zero(t, s.memory.Cap())
			require.Zero(t, s.Buffered())
			require.Nil(t, s.tempFile)
			require.Empty(t, s.tempPath)
			_, err = fd.Stat()
			require.ErrorIs(t, err, os.ErrClosed)
			require.NoError(t, s.Close())
			_, err = s.WriteString("later")
			require.ErrorIs(t, err, os.ErrClosed)
		})
	}
}

func TestStreamMemoryStrictStageExactLimitAndAtomicOverflow(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("unlinked spool requires Unix")
	}
	s := newOpenAINativePrefixStage()
	defer s.Close()
	chunk := strings.Repeat("x", 65536)
	for i := 0; i < 128; i++ {
		_, err := s.WriteString(chunk)
		require.NoError(t, err)
	}
	require.EqualValues(t, 8*1024*1024, s.Buffered())
	require.Zero(t, s.memory.Cap())
	n, err := s.WriteString("x")
	require.Zero(t, n)
	require.ErrorIs(t, err, errOpenAIFirstOutputStageLimit)
	require.EqualValues(t, 8*1024*1024, s.Buffered())
	require.NoError(t, s.CommitTo(io.Discard))
	require.Zero(t, s.memory.Cap())
}

func TestStreamMemoryStrictStageMemoryCommitReleasesBacking(t *testing.T) {
	s := newOpenAINativePrefixStage()
	defer s.Close()
	_, err := s.WriteString(": waiting\n")
	require.NoError(t, err)
	require.LessOrEqual(t, s.memory.Cap(), 65536)
	require.NoError(t, s.CommitTo(io.Discard))
	require.Zero(t, s.memory.Cap())
	require.Nil(t, s.memory.Bytes())
}

// Exercise existing stage dependencies directly; no hooks added to production.
// Unlike the legacy stage, a strict stage must not silently switch to 8MiB RAM.
func TestStreamMemoryStrictStageSpoolFailures(t *testing.T) {
	t.Run("create", func(t *testing.T) {
		s := newOpenAINativePrefixStage()
		s.memoryOnly = false
		defer s.Close()
		s.createTemp = func() (*os.File, error) { return nil, os.ErrPermission }
		_, err := s.WriteString(strings.Repeat("x", 65537))
		require.ErrorIs(t, err, os.ErrPermission)
		require.Zero(t, s.Buffered())
		require.Zero(t, s.memory.Cap())
	})
	t.Run("unlink", func(t *testing.T) {
		s := newOpenAINativePrefixStage()
		s.memoryOnly = false
		dir := t.TempDir()
		s.createTemp = func() (*os.File, error) { return os.CreateTemp(dir, "prefix-*") }
		s.removeFile = func(string) error { return os.ErrPermission }
		defer func() { s.removeFile = os.Remove; _ = s.Close() }()
		_, err := s.WriteString(strings.Repeat("x", 65537))
		require.Error(t, err)
		require.Zero(t, s.Buffered())
		require.Zero(t, s.memory.Cap())
		require.Nil(t, s.tempFile)
		st, err := os.Stat(s.tempPath)
		require.NoError(t, err)
		require.Zero(t, st.Size(), "never put plaintext in named spool")
		path := s.tempPath
		s.removeFile = os.Remove
		require.Error(t, s.Close(), "original cleanup error remains observable")
		_, err = os.Stat(path)
		require.ErrorIs(t, err, os.ErrNotExist)
		require.NoError(t, s.Close())
	})
	t.Run("memory_only_platform", func(t *testing.T) {
		s := newOpenAINativePrefixStage()
		s.memoryOnly = true
		defer s.Close()
		_, err := s.WriteString(strings.Repeat("x", 65536))
		require.NoError(t, err)
		_, err = s.WriteString("x")
		require.Error(t, err)
		require.EqualValues(t, 65536, s.Buffered())
		require.LessOrEqual(t, s.memory.Cap(), 65536)
	})
}
