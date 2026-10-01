APPROVE — frozen evidence-r3 numeric object/array repair, within the offline review scope. No blocking issue found. This approval does not attest a live E2E, a rebuilt runner image, or installed module seals.

Reviewed the supplied frozen `.spike-inputs/candidate` against current canonical workspace files and actual canary 36862418094 diagnostic projections. Trusted setup names canonical workflow SHA `3004a4b16e03588ee62c0ed7fe2751e0e53300e0`. No Git or external service was accessed to independently authenticate that association; exact reviewed bytes are recorded in `input-hashes.json`. All 130 supplied manifest entries were independently SHA-256 recomputed and matched. The candidate snapshot contains no `.github` workflow; the inherited behavioral workflow-validator test was explicitly pointed at the canonical workspace workflow, whose hash is recorded below.

Exact key input SHA-256 values:

| Input | SHA-256 |
| --- | --- |
| Candidate run-client.mjs | `0cafcb8b3adf01f607b62786f7d95021deefddaba7b71a0c62b86ba0419f2565` |
| Candidate evidence.mjs | `4a13f43b05ed54d9e6d267525b89179bc9e6eff246213d6eb63abd8258e1af1f` |
| Candidate evidence.test.mjs | `3cd0e9fe1b99e0cbd3ef7ed6aae03cbe517d3ebf1395ec9eb4eb97c79788d087` |
| Candidate client-contract.test.mjs | `7b1cebb0eeef65363b8d5b90a9153cde4930079d70a8bb3d4276769884359d07` |
| Canonical run-client.mjs | `484d454a3aacf25c3ea2e21e9400bbaa1fbd5b1615b485c24e6088bc881d2599` |
| Canonical evidence.mjs | `2f8b6d1d2adda68a97a28d3672617508da09bf3845d9d60e6df608505eb28856` |
| Canonical workflow | `a88e53308513288af722ea08520285752fc189fad18e1d99d7e0c30a3f0280a9` |
| Fixed wallet.mjs | `c47fcdfb32c95bf1ede68c01a3705084a658ecbd2882ab21ca4e8cc5fc658f71` |
| Fixed BUSINESS_RULES.md | `1a9837e5e95ee86f22eb171c7bc9ee1226c55ff859973ad573417feb6aae43a5` |
| Actual agent projection | `520634e6fe58cb30833bdc2596fef56879305454c5afcde026aee4079cac64fa` |
| Actual tool projection | `fab2a0eb3fd84957ebcdfb09b4d3326e20440f3286d5e4dcf509bd2349fc604e` |
| Actual runner exit | `39d06d86c4405c347353106c9ab25487b1fee7fadd266ce4c2b4650f03d9880e` |
| Actual trusted setup | `fd512de55cb53cf609420357d0578ce6d12d4f2c95962e58e3983753c7d74730` |
| Actual provider custody | `0b855272679569eb042a1dc3bb162048831f3d166ffa09837fe4bc6e3d118e5c` |
| Actual network boundary | `6209bf16d8a8a1fb3d818d994a78b77b86b7fe67c019d944117c79e86e654baf` |

Acceptance and retained gates:

- The actual caller imports and invokes `codexNumericEvidence` on collected command events, using the negative example selected from the final-message document. The helper parses the whole output once; accepts a root object or an immediate object member of a root array; and requires all three fields in that same object to be finite numbers exactly equal under `===`. It never recursively searches, scans prose/fragments, coerces numeric strings, or accepts reasoning/agent-message items as command evidence.
- Numeric proof still requires `item.completed`, command_execution, completed status, numeric zero exit, and the inherited direct Node or exact `/bin/bash|sh|zsh -c|-lc` wrapper classifier with wallet/withdraw tokens. The original classifier is a lexical classifier, not a shell parser or semantic execution attestation; its admission rules are preserved. Tests use synthetic event fixtures explicitly, and a separate real local Node test generates the two-example output from the fixed wallet.
- Separate successful wallet/rules reads, successful agent process exit, turn.completed, rejection of turn.failed/error, and the original final finding contract remain enforced. A real final-message file remains the Codex final source. Financial validation still requires a nonempty summary and a valid negative-withdrawal finding.
- The independent reproduction expression is unchanged and runs before receipt creation against the fixed fixture, checking both return balance and mutated account balance. It is initiated by the trusted control parent. The actual spawn helper uses UID/GID 1002 for Node as well as the agent; this is not a root-UID Node execution. This review executes local Node without privilege changes and does not validate the deployed container boundary.
- OIDC/runtime/grant identity binding, HIGH reasoning configuration, fixture hashes, seal calls covering binder and transitive evidence imports, fixed positive receipt projection, and in-memory transcript custody remain unchanged. The launcher verifies harness.sha256 before Node imports. New helper code resides in an already sealed module. Installed hash-manifest bytes/image rebuilding and actual seal enforcement are not proven by these offline tests.

Actual canary evidence and fidelity limits:

The provided agent projection says review_found/json_valid, separate tool reads, task_complete, and the two final examples `(100,-10,110)` and `(100,0.5,99.5)`. The tool projection says exact separate wallet/rules reads with matching output and zero exits, and a Node-starting reproduction with zero exit and no multiple commands. Runner exit is zero. Network and complete-filesystem provider-key custody projections are PASS. These support the reported successful agent return; they do not themselves constitute a validated positive financial receipt.

The tool projection has `numeric_outputs: []`; it does not preserve the raw complete array stdout or raw terminal event sequence. The complete array shape therefore derives from the user-provided account and an independently reproduced local wallet execution, rather than recovery of raw historical output. No historical output, successful receipt, or live E2E is fabricated or inferred from a synthetic fixture. Projections were inspected in place, not rewritten.

Actual commands and results (Node v24.21.0; paths relative to workspace):

1. `CONSUMER_WORKFLOW_SOURCE="$PWD/.github/workflows/sub2api-gateway-spike.yml" node --test .spike-inputs/candidate/sub2api-spike/evidence.test.mjs .spike-inputs/candidate/sub2api-spike/run-client.test.mjs .spike-inputs/candidate/sub2api-evidence-r2/client-contract.test.mjs`
   Exit 0; 22 passed / 0 failed. Captured in `candidate-tests.tap`. This independently confirms the claimed candidate count.
2. `RUN_CLIENT_SOURCE="$PWD/sub2api-spike/run-client.mjs" node --test --test-name-pattern='caller accepts' .spike-inputs/candidate/sub2api-evidence-r2/client-contract.test.mjs`
   Exit 1 as expected; object passed, synthetic array and actual locally generated array both failed: 1 passed / 2 failed. Captured in `canonical-red.tap`. This independently reproduces the regression against the untouched original caller. Candidate historical red log had only two selected tests; the frozen final harness adds the third real-output test, explaining the count difference.
3. `node --test sub2api-evidence-review/independent.test.mjs`
   Exit 0; 6 passed / 0 failed. Captured in `independent-tests.tap`. Independently authored behavioral tests cover actual local Node array generation, either member/single-object acceptance, disjoint-field rejection, exact numeric matching, nonfinite and missing fields, no recursive/prose extraction, failed/reasoning/agent items, fixed fixture bytes, separate reads, final contract and terminals.
4. `node --test .spike-inputs/candidate/sub2api-spike/granted-run.test.mjs`
   Exit 0; 2 passed / 0 failed. Captured in `grant-tests.tap`. Real local signed-token verifier and binder tests; no external OIDC request.

Test integrity and ownership:

The candidate caller harness loads the actual caller, substitutes only filesystem/runner/process/network I/O, relocates real binder/evidence imports, and runs the actual independent reproduction expression in a local Node subprocess. It neither replaces the numeric predicate nor asserts production source text. Synthetic agent events are explicitly test data. The inherited workflow test executes the canonical validator slice in a VM; it is a behavioral check, not a source-string presence assertion. Inherited caller tests stub independent numeric execution, but the new caller harness and independently authored test perform real Node execution. The fixtures produce both reported balances; their bytes match canonical copies and pinned constants.

Byte comparison of all supplied candidate paths against canonical workspace found exactly three changed existing files: run-client.mjs, evidence.mjs, evidence.test.mjs; new files are exclusively the seven supplied sub2api-evidence-r2 artifacts. Measured production delta is +18/-7 (+2/-7 caller, +16/-0 helper); test delta is +50/-1 for evidence tests plus the 90-line caller harness. See `delta.json` and `ownership-audit.json`.

Review writes are exclusively under new `sub2api-evidence-review/`: this report, hash/delta/ownership audits, independently authored tests and actual command logs. Existing source, frozen inputs and candidate tests were untouched. No credentials, auth homes, root workflows, Docker, Go, network, Git mutation, live providers, subagents, or external gate waits were used. No blocker remains for this bounded review. Deployment seal/custody and exact live coordinator E2E remain verification limits; the project controller owns integration and rebuilding/resealing. STOP.
