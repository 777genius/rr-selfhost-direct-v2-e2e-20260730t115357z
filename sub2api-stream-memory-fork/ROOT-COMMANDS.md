These commands are for the project controller, using its existing offline Go 1.27.1 toolchain and populated dependency cache. They require no elevated privileges, Docker, Git writes, network, or providers. No Go command below was run by this worker. Missing tooling/cache is NOT RUN, never a behavioral RED.

Set `MEMORY_FORK_GO` to the absolute path of that existing Go executable and `MEMORY_FORK_MODCACHE` to the existing populated module cache. Run from the shared workspace root. Use fresh disposable destinations; preparation refuses to overwrite an existing tree and does not edit shared sources.

```sh
python3 sub2api-stream-memory-fork/prepare-go.py --mode red --dest /tmp/sub2api-memory-old-w2
python3 sub2api-stream-memory-fork/prepare-go.py --mode green --native-controls --dest /tmp/sub2api-memory-new-w2
python3 sub2api-stream-memory-fork/run-go.py --suite red --tree /tmp/sub2api-memory-old-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2
python3 sub2api-stream-memory-fork/run-go.py --suite controls --tree /tmp/sub2api-memory-old-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2/old-controls
python3 sub2api-stream-memory-fork/run-go.py --suite controls --tree /tmp/sub2api-memory-new-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2/new-controls
python3 sub2api-stream-memory-fork/run-go.py --suite handoff --tree /tmp/sub2api-memory-old-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2/old-handoff
python3 sub2api-stream-memory-fork/run-go.py --suite handoff --tree /tmp/sub2api-memory-new-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2/new-handoff
python3 sub2api-stream-memory-fork/run-go.py --suite green --race --tree /tmp/sub2api-memory-new-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2
python3 sub2api-stream-memory-fork/run-go.py --suite native --tree /tmp/sub2api-memory-new-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2
python3 sub2api-stream-memory-fork/run-go.py --suite probe --tree /tmp/sub2api-memory-new-w2 --go "$MEMORY_FORK_GO" --gomodcache "$MEMORY_FORK_MODCACHE" --out /tmp/sub2api-memory-go-w2
```

The RED wrapper expects four named behavioral failures: Messages read-ahead in both routes, Responses prefix overflow, and Responses prefix cancellation. Parent subtest failure is allowed; compile failure and unexpected test failures reject the gate. Both controls commands must PASS with the same fixed byte, SHA-256, flush, tool-ID, and usage oracles. The GREEN command must PASS the original 32 entries plus the prescribed handoff parent and two subtests (35 entries), with race detection and zero skips. The handoff suites require three PASS entries on both old and repaired source, using the exact independent reproducer and unchanged 7/5 usage assertions with the native policy flag absent. Native requires the historical 292 selected passes; investigate coverage changes without relabeling fewer passes as the same gate. Probe requires all 63 original capability-disable controls with zero skips. Native requires zero skips too. The root must also run existing passthrough flush, failure, concatenated JSON, first-output, and Messages preservation tests on the integrated source:

```sh
cd /tmp/sub2api-memory-new-w2/backend
env GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOMODCACHE="$MEMORY_FORK_MODCACHE" \
  "$MEMORY_FORK_GO" test -mod=readonly -tags=unit ./internal/service ./internal/handler \
  -run '^(TestOpenAIStreamingPassthrough|TestOpenAIFirstOutput|TestOpenAINativeFirstOutput|TestOpenAISSE|TestStartOpenAISSEKeepalive|TestPassthroughKeepalive|TestGatewayService_AnthropicAPIKeyPassthrough|Test.*NativeAnthropic)' \
  -count=1 -timeout=240s
```

Root commands bind JSONL results to this production patch's hash, preparation manifest, exact command and build status. Run the same commands after conflict-aware integration using newly recorded integrated hashes, rather than treating this independent overlay as proof of the merged result. Keep receipts outside the package so the frozen artifact inventory remains intact.

Offline packaging checks, runnable by this worker, were executed:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-stream-memory-fork/package.py
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-stream-memory-fork/verify.py
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-stream-memory-fork/verify-w2.py
.spike-inputs/gofmt -l sub2api-stream-memory-fork/production/backend/internal/service/*.go sub2api-stream-memory-fork/tests/backend/internal/service/*.go
```

The supplied W1 old/new handoff receipts already establish old PASS / W1 RED. They are historical input summaries, not repaired-source or merged-source receipts. `W2-DELTA.json` and the two `w2-prefix-ownership.*.patch` files also support exact W1-to-W2 application; the full patches remain against frozen combined source. The controller must conflict-merge the four production files against cancellation work and regenerate integrated hashes.
