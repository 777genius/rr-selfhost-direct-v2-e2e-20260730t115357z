# Server wiring w2: SR1 correction

Delivered bounded constructor correction; no operator gates remain to wait for in this lane. Only `sub2api-spike/broker.mjs`, `sub2api-spike/broker.test.mjs` and new/updated artifacts under `sub2api-server/` were written. No dependencies or platform changes.

The successful exclusive `wx` lock acquisition remains outside exception cleanup. Lock PID write/sync, ledger read/JSON parse/schema validation, initial persistence and handle close now share exception cleanup. Cleanup attempts handle close and releases the owned lock in `finally`, including a close failure. Acquisition `EEXIST` never reaches cleanup. Normal server close and listen-failure cleanup are unchanged. A process crash still leaves its lock for coordinator-controlled recovery. Grant, OIDC, normalization and durable replay-denial logic are unchanged.

## Observed verification

Node v24.21.0; actual disposable filesystem operations, no listeners or provider calls:

- `w2-before.tap`: five selected regressions, **2 pass / 3 fail / 0 skip** before the broker fix. Malformed JSON, invalid schema and ledger-directory `EISDIR` each rejected as expected but retained the lock, failing the required `ENOENT` assertion. Node also reported garbage-collected unclosed FileHandles. Persistence failure and existing foreign/crash lock protection already passed.
- `w2-after.tap`: the same five regressions, **5 pass / 0 fail / 0 skip**. Each failure case permits a repaired ledger to construct successfully, preserves its existing issued-run record, retains the lock while the server exists and removes it after actual server close. The foreign/crash lock test checks unchanged content and inode and unchanged ledger bytes on `EEXIST`.
- `w2-serve-offline.tap`: existing socket-free wiring selection, **3 pass / 0 fail / 0 skip**. Import and pre-broker installation/template/customer initialization rejection behavior still pass.
- `node --check` passed for both edited broker files. Write/sync/handle-close failures are covered structurally by the cleanup boundary; they were not separately injected or claimed as executed cases.

Commands:

```sh
node --test --test-reporter=tap --test-name-pattern='SR1 constructor' sub2api-spike/broker.test.mjs
node --test --test-reporter=tap --test-name-pattern='server import|invalid installation|malformed templates' sub2api-spike/serve.test.mjs
node --check sub2api-spike/broker.mjs
node --check sub2api-spike/broker.test.mjs
```

## Preservation and limitations

`w2-before-sha256.json` and `w2-preservation.json` cover 126 observed files in the spike, gateway and independent review directories: only the two broker files changed; 124 others are byte-identical. Existing broker test bytes were independently reconstructed and matched their captured pre-edit hash before generating `w2.patch`. Existing tests were not replaced. The captured valid wiring is unchanged:

- `serve.mjs`: `fb2ec7e3aa5eadb60cde72d25f2004d77e8ece52de318d5c53abca14a190275c`
- `serve.test.mjs`: `a5f1908d5bab1579deb7ed80273868d87ec3c14bf1c818a0cd0e966eb765047c`

The requested `.spike-inputs/server-review-w1/verification/` is empty here; its REPORT/review/independent test are unavailable. The available `sub2api-server-review/REPORT.md`, `review.json` and `independent.test.mjs` were read for SR1 and preserved byte-for-byte. The independent diagnosis remains historical: its passing assertion demonstrates the old defect, not passing corrected behavior. Its referenced frozen consumer tree is absent here, so that historical test was not executed or rewritten.

The supplied inherited **96 actual root Node HTTP/socket cases** are preserved, not independently rerun or attested here. Available `.spike-inputs/coordinator/server-wiring-w1-execution.json` reports exit 0 and provider_calls 0, but contains no test count or raw log. No attempt was made to access its external full-log path.

**NOT RUN:** HTTP/socket suite, external stock Go, Docker/patched-image integration, live provider, production or installation-custody gates. The coordinator executes external gates; none were waited for or polled. No network, credentials/auth homes, root, Git mutation or provider operations occurred. Remaining risk: these external behaviors are not newly verified by this bounded filesystem fix.

Git preflight ran once: `git status --short` rejected the unavailable linked gitdir, and inspection of its `index.lock` reported no such path. Lock absence is unverified; no bypass or mixed-index normalization was attempted. Git add/commit/push were not run. Coordinator integration must preserve all other lane bytes and normalize any mixed index only after this worker stops.

## Exact w2 artifacts

- `sub2api-server/W2-REPORT.md`
- `sub2api-server/w2.patch` (only the two broker source/test paths)
- `sub2api-server/w2-before.tap`
- `sub2api-server/w2-after.tap`
- `sub2api-server/w2-serve-offline.tap`
- `sub2api-server/w2-before-sha256.json`
- `sub2api-server/w2-preservation.json`
- `sub2api-server/README.md` (w2 handoff appended; inherited evidence retained)

The inherited w1 artifacts and historical `source-sha256.txt` remain unchanged; the w2 manifest records current hashes.
