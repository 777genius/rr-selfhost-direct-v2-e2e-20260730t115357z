# Bounded independent SR1 and server integration review — w2 final

Decision: **APPROVE the exact frozen server-wiring-w2 final candidate and workflow proposal for coordinator integration. SR1 is closed; no new actionable findings.** This is a server review, not production or native-fork approval. Review is complete; external gates are limitations, with no waiting work. Only `sub2api-server-review-v2/` was written.

## Exact candidate and evidence

The authoritative sources are under `.spike-inputs/consumer/`, not the older canonical server/broker implementation. Independently checked all **137** current input-manifest entries: zero missing files or hash mismatches. All six source hashes in `.spike-inputs/actual/execution.json` match the actual frozen bytes. `verification/source-check.json` records these comparisons and exact receipt hashes; source files are referenced rather than copied.

| Frozen source | SHA-256 |
| --- | --- |
| sub2api-spike/serve.mjs | fb2ec7e3aa5eadb60cde72d25f2004d77e8ece52de318d5c53abca14a190275c |
| sub2api-spike/serve.test.mjs | a5f1908d5bab1579deb7ed80273868d87ec3c14bf1c818a0cd0e966eb765047c |
| sub2api-spike/broker.mjs | 742b1d166670a18eae27475c5cd5ab5fb3e770bbbb92706e885ee11d33aa900a |
| sub2api-spike/broker.test.mjs | d9320ab9e2e08c5381328723dfc03f79a73c34da0d64c84b0e84cb6512a75051 |
| sub2api-server/broker-initialization.test.mjs | 3038e500b4a8c6d72d74459a5cd0f049bbc9da6cb131100ab8c7b490a24dd0ee |
| sub2api-server/workflow-final.yml | a88e53308513288af722ea08520285752fc189fad18e1d99d7e0c30a3f0280a9 |

## SR1 closure and meaningful regressions

`broker.mjs:18` acquires the exclusive `wx` lock before entering exception cleanup. Acquisition failure therefore cannot unlink another owner or a crash lock. Lines 25–33 cover PID write/sync, ledger read/JSON parsing/schema validation, initial durable persistence and handle close. Rejection attempts handle close and releases the acquired lock in `finally`, even if close rejects. Successful construction retains the lock until the existing server close handler; process crash still leaves it for coordinator-controlled recovery. The diff changes only this constructor initialization boundary; grant admission, issued-run persistence, poisoning, replay denial, revocation and stream handling remain unchanged. Under the existing ownership contract, no coordinator removes a live broker's lock.

Independently executed the exact frozen new module with Node **v24.21.0**, using `TMPDIR` inside the owned report directory: **5 pass, 0 fail, 0 skip**, exit 0. No listener opened. Command:

```sh
TMPDIR="$PWD/sub2api-server-review-v2/tmp" /opt/nodejs/node-v24.21.0-linux-x64/bin/node --test --test-reporter=tap .spike-inputs/consumer/sub2api-server/broker-initialization.test.mjs
```

The four recovery cases use actual filesystem failures and require specific rejection classes: malformed JSON, invalid schema, directory read `EISDIR`, and blocked `.new` persistence returning `ledger_unavailable`. Each asserts the failed constructor's lock is absent, repairs disk state, constructs again, verifies the complete existing issued-run ledger is retained, verifies the live server's lock, closes the server and verifies removal. The fifth asserts `EEXIST` preserves foreign/crash lock content and inode and leaves the malformed ledger untouched. These assertions discriminate the old SR1 failure and avoid a false green from fixtures failing before broker execution. New fixtures use `os.tmpdir()`; they do not write into immutable source mounts. Write, sync and close faults are covered by source inspection of the boundary, not separately injected here.

## Integration and preservation

All 12 frozen consumer source entries other than the changed broker recorded by the prior independent review retain their exact hashes, including serve/tests, customer adapter, OIDC, grant/client/isolation modules, native filtering, utility and operator wiring. Reinspection confirms installation and present template validation precede key/state/ledger/listener effects; actual AdminAPI receives installation and the adapter receives trusted templates. Interrupted adapter recovery fences workspace authority before broker construction and queues revocations until the broker exists. Synthetic customer validation precedes broker construction. Shutdown closes both listeners, and a partial listen failure reaches the existing broker close handler. The source change leaves these invariants intact.

Original frozen `broker.test.mjs` is byte-identical to canonical, including the historical synthetic Bearer assertions. No old tests were replaced or edited. Existing B10/G03 actually asserts stale capability denial, durable issued-run replay denial after restart and fail-closed ledger poisoning. The root full gate covers this alongside broad HTTP/socket, native transport, authority/recovery, receipt and financial-validation contracts, including rejection of fabricated financial success. The new filesystem module augments these contracts.

The workflow proposal is exactly one changed line: append `sub2api-server/*.test.mjs` to the existing contract command. Every other workflow byte matches `.github/workflows/sub2api-gateway-spike.yml`; `verification/workflow.diff` records the change. The coordinator must apply the exact reviewed proposal bytes separately after integration. No workflow was modified or executed here.

The frozen root gate is authoritative for full runtime coverage: its pinned Node 24.21.0 image receipt records exit 0, zero provider calls and **102 pass / 0 fail / 0 skip**. The included, hash-verified `contracts.log` independently contains 102 successful top-level cases and matching totals, including all five SR1 tests, actual startup/AdminAPI transport and customer-listen rollback. This worker checked the log and source binding; it did not rerun the socket gate. Full financial validation here refers to the synthetic contract suite, not a live financial canary.

## Historical evidence and limitations

`W2-REPORT.md`, `w2.patch` and `w2-preservation.json` describe the historical producer change to the original broker test. `actual/fixture-repair.json` records the earlier immutable-mount EROFS failures before broker calls and the subsequent fixture-path repair. Those artifacts remain historical and do not describe final test placement or a current failing gate. `COORDINATOR-FINAL.md` and `actual/test-isolation.json`, together with direct final-byte comparison, establish restored original tests and the separate final five-test module. Scanner retention/enforcement is documented by the coordinator's frozen receipt and user instruction; this review did not execute or independently audit the external handoff scanner. No scanner was disabled or bypassed.

No blocking findings remain in this bounded scope. Actual Node gates and local filesystem checks do not establish production membership/SSO, installed image custody, live OAuth/provider behavior, genuine Actions execution or native deployment readiness. These remain external limitations, not new implementation demands or waiting work. No Docker, Go, Git operations, network/provider/credential access, agents or socket retries were performed. Sources and earlier review artifacts were left intact. This completes the requested review and handoff.
