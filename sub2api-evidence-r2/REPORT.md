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
