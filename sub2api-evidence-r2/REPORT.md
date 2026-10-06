Implemented fixed safe diagnostics in the actual caller and clarified its local Node numeric output contract. This revision does not establish a successful live canary. Actual third run **36876496665**, exact workflow **625946b532534acd0329d41bb096d54f6f16b351**, remains **FAILED at the generic evidence phase**. The coordinator removed the raw runner transcript before diagnosis. The actual output format and rejection cause for that run are unknown; no recovery, successful final answer, or new historical narrative is asserted.

Current `.spike-inputs/trusted-setup.json` identifies that run/workflow. Usage rows increased from 9 before the runner to 13 afterward: **4 provider requests**. The user reports a known terminal; current terminal filesystem custody and own-run teardown projections both say PASS. Custody covers the terminal filesystem snapshot and scanned configuration/log surfaces, with zero raw/encoded provider key hits and zero host binds; it does not prove continuous process-memory custody. No raw transcript or provider keys were accessed or saved.

The actual caller now assigns these fixed phases before each operation: `evidence_parse`, `evidence_numeric_example`, `evidence_independent_reproduction`, `evidence_tool_numeric`, `evidence_agent_contract`, `evidence_write`. Its catch still emits only `Spike failed at <fixed phase>; inspect effects privately before retry.` No agent output, error object/message, reasoning, or keys enter stderr. Parsed null/non-object documents fail at parse; the selected negative example must have three finite numeric fields before Node execution. No alternative example or invented semantic fallback is substituted.

The prompt instructs Codex to have its local Node wallet reproduction emit **ONE standalone complete JSON object** with numeric initial_balance, amount, final_balance for the negative withdrawal finding, no prose or extra output, matching the final numeric example. The final answer still follows the findings contract. Complete object/array/strict JSONL acceptance is unchanged in `sub2api-spike/evidence.mjs` (SHA-256 **44f17424b5057ab94693809d05bc33db6305f065ead928f95aa0b066137f2160**). The successful completed command/status, numeric-zero exit, own exact numeric match, real independent wallet execution, separate exact wallet/rules reads, genuine terminal/final-file and finding contract, sealing/import paths, OIDC/grant binding, custody, MiMo HIGH reasoning and granted model are preserved. Controller integration must rebuild/reseal the changed caller bytes.

All eight new tests execute the actual top-level caller with substituted agent/network/privilege/seal I/O and real local Node wallet execution; they are not source-only assertions or live provider evidence. They check exact safe stderr for parse, missing/nonfinite numeric example, independent failure, own numeric mismatch/tool admission, final/reads/terminal contract and write failure, plus a green standalone-object path and selected-source imports. Failures publish no receipt. The independent mismatch observes real Node process exit 1; green paths observe independent process exit 0. The prompt/HIGH/model test inspects arguments and configuration actually handed to the agent launcher.

The nonblocking independent-review observation is fixed minimally in the existing caller harness: `RUN_CLIENT_SOURCE` is resolved to a file URL, and relative imports plus `import.meta.url` are bound to that selected source. Normal ESM resolution then binds the selected evidence module's transitive gateway validator. A behavioral test copies the selected caller/evidence/binder into a temporary owned directory and supplies a distinct transitive validator that rejects; the default imports would incorrectly pass. That temporary tree is removed in finally. This is a harness integrity change, not a production admission change.

Exact offline validation on **Node v24.21.0**:

```sh
node --test --test-reporter=tap sub2api-spike/evidence.test.mjs sub2api-spike/run-client.test.mjs sub2api-evidence-r2/client-contract.test.mjs
```

- Entry baseline before adding tests: **29 passed / 0 failed**, exit **0**, `phase-baseline-29.tap`.
- Final tests against the entry caller, with the selector fix already in the harness: **29 passed / 8 failed**, exit **1**, `phase-red.tap`.
- Fixed caller, identical tests: **37 passed / 0 failed**, exit **0**, `phase-green.tap`.

```sh
node --test --test-reporter=tap --test-name-pattern='RUN_CLIENT_SOURCE binds' sub2api-evidence-r2/client-contract.test.mjs
```

Selector-only RED restores the two original default-base import/meta URL expressions in the harness temporarily and restores fixed bytes in finally: **0 passed / 1 failed**, exit **1**, `selector-red.tap`. Fixed harness with the identical test: **1 passed / 0 failed**, exit **0**, `selector-green.tap`. This independently demonstrates transitive selection, rather than relying on source inspection.

Syntax checks for run-client.mjs, evidence.test.mjs and client-contract.test.mjs all exited **0**. Existing **29** tests remain in place and pass. The existing **full 121** tests are retained; the full suite was **NOT RUN in this turn** because its broker/customer/server tests open loopback sockets and network is prohibited. There are no new dependencies. **Paid new run: NOT RUN.** No real agent/provider, network, credentials/auth, Docker, root workflow, Git write or sub-agent operation occurred. The attempted initial read-only Git status failed to resolve the linked gitdir; source diffs were computed directly from saved entry bytes. No commit or push was attempted.

Exact incremental LOC and final SHA-256 relative to this evidence-r5 entry (artifact/report LOC excluded):

| File | Added / removed | Final SHA-256 |
| --- | --- | --- |
| sub2api-spike/run-client.mjs | +9 / -5 | 3308b5cbaaf2b5be10d616ace4a1e47a24e013fa944514ae61054fd37d7fb490 |
| sub2api-spike/evidence.test.mjs | +0 / -0 | 0b2a8eae3f3000598ddc868b0ee449c4c3ca12791343e6fb163fc6d74570bbb0 |
| sub2api-evidence-r2/client-contract.test.mjs | +97 / -9 | 49bf6f90369b551e598fd79535dee389bc789b69d7f624b7b0f29ec04b802efa |

Production: **+9 / -5**. Behavioral tests/harness: **+97 / -9**. `evidence.test.mjs` is byte-identical to entry. `phase-implementation.patch` contains the two actual source/harness diffs; `phase-change-metrics.json` records baseline/final hashes and artifact hashes. No other production source was changed. Historical report bytes are copied unchanged below; historical red/green logs, patches, metrics and numeric fixture remain intact. Their descriptions and hashes refer to their own earlier revisions, not this revision. The two earlier failed canaries and this third failed canary all remain failures.

Remaining limits: the third run's specific rejection cannot be diagnosed without its removed transcript; new paid E2E is explicitly NOT RUN. Local behavioral checks prove the requested diagnostics, contract and preserved acceptance/proof gates, not live success. Controller integration/rebuild/reseal and any future paid run are outside this edit/test handoff. Delivered and stopped within the requested ten-minute bound.

Historical report follows verbatim:

Fixed the actual strict JSONL numeric evidence rejection from MiMo + Codex HIGH run **36869316283**, whose reviewed workflow was **e3358801023d81211440c13af09ce205700ebe25**. Whole-output JSON object/array parsing remains first. Only a JSON syntax failure enables JSONL: at least two nonblank lines, every line a complete object containing all three finite numeric fields, with one row matching the reported initial_balance, amount, and final_balance exactly. No line is skipped except blank whitespace. Prose, malformed or partial JSON, arrays, nested candidates, missing fields, string numbers, overflow/nonfinite values, and mismatched examples fail. Existing object/array behavior, including pretty-printed complete documents, remains green.

The root-supplied actual-numeric-jsonl-projection.json was read with actual-agent-projection.json and trusted-setup.json. Its two rows are 1000 / -50 / 1050 and 1000 / 25.5 / 974.5; the later 10.5 / 1 / 9.5 single-object observation still uses the whole-object path. The two-row output is reproduced with real local Node importing the actual sub2api-spike fixture wallet, printing one complete object per line, and comparing the entire stdout against the supplied rows. The top-level caller then performs its separate real Node reproduction of the selected negative example. A wrong reported final balance produces an observed independent process exit 1 and no receipt. The sanitized numeric-only projection is retained as numeric-jsonl-fixture.json (byte-identical to the supplied projection) so tests work without the temporary root inputs. No raw transcript is saved.

run-client.mjs is byte-identical to the entry baseline. Command admission, completed item/status, numeric-zero exit, separate wallet/rules reads, genuine successful terminal and final-message file, inherited final finding validation, HIGH reasoning/model, grant binding, sealing of all imported modules, fixed receipt projection, and transcript custody remain intact. Caller tests verify the successful JSONL path and denial of failed tools, wrong commands, missing separate reads, missing/failed terminal, invalid/absent final, independent proof mismatch, and seal denial. No phase constants were needed; error output remains the existing fixed vocabulary without raw text.

Exact RED and GREEN test command (same command in both states):

```sh
node --test --test-reporter=tap sub2api-spike/evidence.test.mjs sub2api-spike/run-client.test.mjs sub2api-evidence-r2/client-contract.test.mjs
```

RED: original object/array-only evidence.mjs bytes, final regression tests: **27 passed / 2 failed**, process exit **1**. Only the actual JSONL helper acceptance and actual JSONL top-level caller acceptance tests failed. jsonl-red.tap records this. The entry baseline helper was temporarily restored by a Node script and the fixed helper restored in its finally block; baseline hashes are in change-metrics.json. GREEN: fixed helper, identical tests: **29 passed / 0 failed**, process exit **0**, in jsonl-green.tap. Negative tests reject extra malformed/prose/array lines even when an earlier row matches; test all three numeric fields for strings/nonfinite/missing values and exact mismatches; reject a purported example assembled from different rows; retain successful command/item/exit requirements. Node is **v24.21.0**. Local agent/network/seal I/O is substituted; wallet and independent numeric execution are real local processes. These logs are local contract evidence, not a successful live-provider run.

Syntax checks, all exit **0**:

```sh
node --check sub2api-spike/run-client.mjs
node --check sub2api-spike/evidence.mjs
node --check sub2api-spike/evidence.test.mjs
node --check sub2api-evidence-r2/client-contract.test.mjs
```

Incremental LOC relative to this evidence-r4 entry baseline (line insertions/deletions; test fixture and report artifacts excluded):

| File | Added | Removed | Final SHA-256 |
| --- | ---: | ---: | --- |
| sub2api-spike/run-client.mjs | 0 | 0 | 0cafcb8b3adf01f607b62786f7d95021deefddaba7b71a0c62b86ba0419f2565 |
| sub2api-spike/evidence.mjs | 15 | 5 | 44f17424b5057ab94693809d05bc33db6305f065ead928f95aa0b066137f2160 |
| sub2api-spike/evidence.test.mjs | 47 | 1 | 0b2a8eae3f3000598ddc868b0ee449c4c3ca12791343e6fb163fc6d74570bbb0 |
| sub2api-evidence-r2/client-contract.test.mjs | 46 | 4 | 4c9d4eed62708962b86f396f69d00b9f582b34a0a331ea3753f012d95cfda3d8 |

Production: **+15 / -5**. Tests: **+93 / -5**. Numeric fixture SHA-256: **13f41a252197709f3382adca88b3924132aa50fa3cb081e88ce83cc2790b5bbb**. change-metrics.json records baseline/final hashes and log hashes; jsonl-implementation.patch records the incremental source/test/fixture changes. Previous object/array metrics are retained as previous-change-metrics.json. Previous red.tap, caller-red.tap, green.tap, and implementation.patch remain intact. Their original report follows verbatim as historical evidence; its paths, LOC, hashes, and 22-test GREEN describe the previous revision, not this JSONL fix.

**Coordinator paid E2E: NOT RUN.** The two previous actual failures remain failures: run36862418094 on 3004a4b required array support; run36869316283 on e335880 required strict JSONL support. Neither is promoted to live success by these local tests. No provider/network/credential, Docker/root/Go, Git mutation/push, or sub-agent action occurred. Git status could not resolve the linked worktree's unavailable gitdir; no Git writes were attempted. Integration/rebuild/reseal and the exact coordinator paid E2E remain controller responsibilities. No local implementation blocker remains. All writes are within the three owned source paths and sub2api-evidence-r2/, apart from disposable baseline snapshots in the authorized agent temporary directory. run-client.mjs required no change for this revision.

Previous report (retained historical failures and validation):

Implemented the numeric-object-or-array evidence fix for the reported MiMo + Codex HIGH canary 36862418094 on 3004a4b. The exported `codexNumericEvidence(event, example)` helper parses the complete command output once and accepts either a root JSON object or an immediate member of a root JSON array. The candidate's `initial_balance`, `amount`, and `final_balance` must all be finite numbers exactly equal to the reported example. Existing successful object evidence remains accepted.

The provided independent diagnostic projections were inspected in place: separate wallet/rules reads succeeded; the reproduction command starts with Node and succeeded; the final projection contains the negative and fractional examples. The tool projection has an empty `numeric_outputs` list. The user-provided complete two-object array is reproduced by the local wallet execution test. No real transcript, credentials, or raw diagnostic data were copied or persisted. This report does not promote the failed canary to a successful Actions run.

The helper retains the existing direct Node and `/bin/bash|sh|zsh -c|-lc` wrapper classifier, wallet/withdraw tokens, completed command item/status, and numeric zero exit requirement. It does not add shell command admission or recursively search output. Complete-output parsing rejects fragments, prose, markdown fences, malformed output, string numbers, mismatched values, nested candidates, reasoning items, and failed tools. The caller still takes its final review from the final-message file, independently executes the selected example against the immutable wallet, and requires successful separate file/rules reads, a successful agent terminal, and the inherited financial finding contract. Grant binding, HIGH reasoning configuration, fixed receipt projection, sealing calls, and transcript custody code are unchanged. The helper lives in the already imported and sealed `evidence.mjs`; no new production module or manifest entry is needed.

RED commands and observed results:

```sh
node --test sub2api-spike/evidence.test.mjs
```

Run after extracting the original root-only predicate, before adding array membership: 8 passed, 1 failed, exit 1. Only the array test failed; the existing object test passed. Captured in `red.tap`.

```sh
RUN_CLIENT_SOURCE=/srv/worker-state/jobs/review-router-gateway-spike/poc-20260930/rr-gateway-spike-20260930-evidence-r3/tmp/agent/evidence-r2-baseline/run-client.mjs node --test --test-name-pattern='caller accepts' sub2api-evidence-r2/client-contract.test.mjs
```

Run against the untouched saved original caller: object accepted, array rejected, 1 passed / 1 failed, exit 1. Both execute the original independent Node reproduction expression locally. Captured in `caller-red.tap`. The saved original is a disposable local baseline; `implementation.patch` records the original-to-final changes.

GREEN command:

```sh
node --test sub2api-spike/evidence.test.mjs sub2api-spike/run-client.test.mjs sub2api-evidence-r2/client-contract.test.mjs
```

Node v24.21.0: **22 passed, 0 failed**, exit 0, captured in `green.tap`. Coverage includes unchanged object behavior, either array example/order, exact finite numeric fields, malformed/fragment/nested output, failed/incomplete items, wrong commands, missing separate reads, failed/missing agent terminal, invalid final JSON, independent reproduction mismatch, seal denial, and inherited grant/receipt binding. A local Node process imports the actual wallet and emits exactly the two-object array; the caller accepts that complete output and then executes its own independent Node reproduction. Agent, network, privilege, and seal I/O are substituted in caller tests; local numeric execution is real. These are local behavioral contract tests, not live-provider proof.

Syntax verification passed (exit 0 for each):

```sh
node --check sub2api-spike/run-client.mjs
node --check sub2api-spike/evidence.mjs
node --check sub2api-spike/evidence.test.mjs
node --check sub2api-evidence-r2/client-contract.test.mjs
```

Changed LOC relative to this sandbox's initial file bytes:

| File | Added | Removed |
| --- | ---: | ---: |
| `sub2api-spike/run-client.mjs` | 2 | 7 |
| `sub2api-spike/evidence.mjs` | 16 | 0 |
| `sub2api-spike/evidence.test.mjs` | 50 | 1 |
| New `sub2api-evidence-r2/client-contract.test.mjs` | 90 | 0 |

Production total: **+18 / -7**. Behavioral tests: **+140 / -1**. Report, TAP logs, patch, and metrics are additional handoff artifacts under the authorized new directory. `change-metrics.json` includes hashes of the final code/test bytes. Only the three authorized existing files and the authorized new directory were written in the project.

Remaining limits: **exact coordinator E2E: NOT RUN**. No Docker, privileged/root workflow, Go, real agent, live provider, or real seal/custody deployment was exercised. The independent root/container execution and installed seal checks remain unchanged and require coordinator validation after integration. Historical source manifests/receipts were not rewritten. No external canary state was changed. Read-only Git status/HEAD inspection failed because the linked worktree's gitdir is unavailable in this sandbox; no Git mutation, staging, commit, or push was attempted. The Project Integration controller must apply/commit the intact workspace diff and rebuild/reseal through its normal lifecycle. No implementation blocker remains; live E2E is an explicit verification limit.
