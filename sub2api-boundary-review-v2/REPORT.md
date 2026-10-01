# Independent bounded review v2

**Approve the repaired producer code for integration in the disposable synthetic sandbox, with the gates below. BR02 remains open at the adapter-to-engine boundary. No real E2E, credential installation, canary dispatch or production GO is approved.** Review is complete; coordinator gates are handoff requirements, not a reason to wait.

Frozen upstream: `96f4c115c9749078f90cbf210a01d39baf3f53b6`, officially archived and hash-verified by the coordinator as instructed. Local SHA-256 verification matched all 212 staged manifest entries. Exact source tree: `fd54c05fbf6d70a7afee06da78ac4c45df802505bdbddd7a60820f89a6de26c1` (4,168 files). Full hashes and algorithm are in `frozen-inputs.json`; review decisions and evidence bindings are in `review.json`.

| Frozen artifact | SHA-256 |
| --- | --- |
| INPUT-HASHES.json | 1df83cf05c0d62dd06241f90785b0102c9501a6bdfacabf55c711834509155bc |
| boundary replacement patch | 482855b20d60917ce9081d606592366ad9f77ad865bd6f3840bbb0a4bb0a47d1 |
| boundary customer.mjs | 35f4c44a3a1a02e2c2d6c21f029abbfc4e5d0fb57ed643c9248850b3df3ce99d |
| probe patch | 31ee1ff60fa957566513cbd124cfde6ec97bdf77c1012e7ba583c098d96fdd72 |
| provenance broker.mjs | 976def94620b9a01e9523c640c7134c6d930f06babe0612fc6aa06eb078a91dd |
| provenance granted-run.mjs | fcc538a3c28e97ce0fd2b4724615fd4484fd94f3c1c4fe5cfbc2f91021a0c047 |

Paths below start at `.spike-inputs/` unless specified otherwise.

## Actionable findings

**BR02 / P1 — Adapter preparation removes the engine's trusted probe-disable flag.** `boundary-code/sub2api-spike/customer.mjs:59`, generated extra at `:195`. A template carrying boolean `openai_disable_capability_probe=true` is prepared with a replacement extra map containing neither that flag nor a preservation rule. Actual upstream `backend/internal/service/admin_account.go:662-705` replaces extra and preserves only enumerated managed fields; this flag is absent. Patched handler/service guards therefore see the default enabled behavior after preparation. Independent contract `independent.test.mjs:62` fails with actual undefined versus expected true. This proves the missing outgoing flag; no external request was executed. The source establishes why the real PUT does not preserve it. The handler unit stub leaves extra unchanged, so its green count cannot close this integration gap.

Minimal remedy: explicitly set the trusted boolean true for OpenAI quarantine preparation, verify it in the template/prepared/duplicate responses, and preserve it through the copy lifecycle. Do not copy arbitrary template extra or permit customer control. Reject an engine lacking the patch/flag contract before preparation. Keep the unchanged default behavior outside this trusted path. Acceptance: actual admin PUT and duplicate with an independent counting inert transport, drain delayed work, and require zero requests and zero capability-metadata writes.

**BR04 / P2 — Producer repaired; consumer integration remains mandatory.** `boundary-code/sub2api-spike/run-client.mjs:33,67` still discards grant identity and publishes launcher identity; the replacement workflow hunk in `boundary-code/sub2api-boundary/boundary.patch:972` validates only result and workflow SHA. The older provenance caller (`provenance-code/sub2api-spike/run-client.mjs:52,85`) likewise has no binder. Exact mismatched run/attempt/provider/agent selections are denied by the real binder in independent and producer tests, but these callers never invoke it. This is the known next lane, not a rejection of the underlying producer contract.

Minimal remedy: seal/install/import `granted-run.mjs`; call it after grant parsing and before review execution; derive receipt identity from its frozen result; compare run, attempt, workflow, provider, agent and protocol before upload. For the repaired harness map **runtime.runID, runtime.runAttempt, runtime.workflowSHA** to binder runID/attempt/workflowSHA. The handoff snippet's snake-case runtime fields must be adapted, otherwise valid runs fail closed. Preserve existing financial/native assertions. Require an integrated mismatch test proving zero review execution/publication and a valid normalized receipt.

**BR05 / P2 — Bundled actual-admin gate still cannot exercise the repaired path.** `boundary-code/sub2api-spike/operator/admin-roundtrip.mjs:36` creates adapter configuration without trusted template IDs. It necessarily fails `quarantine_template_required` before account preparation; its receipt initializes upstream_requests to zero rather than measuring asynchronous effects. Minimal remedy: supply exclusively owned inactive/group-free/unschedulable inert templates, wire trusted IDs, and obtain effect counts from a separate instrumented boundary. Run against the exact patched engine; retain the prior genuine stock red receipt.

## Repair assessment

BR01 is closed for the inspected **standard-mode full DTO** producer contract. The parser requires full authority fields, accepts omitted empty group slices/null redacted credentials, denies present null/malformed/duplicate/conflicting memberships, and requests `lite=false` during recovery. Actual types/mappers, repository membership loading and successful full responses were inspected, including omission and query-error propagation. Simple-mode filtering remains a deployment gate: full-looking empty fields alone do not establish unfiltered membership. Require verified standard mode.

BR03 is closed within the stated single-controller authority model. Object/reference/value snapshots are checked across credential resolution, template preparation, persistence, promotion, read/export/mutation and recovery awaits. Independent remaps at attachment, activation and scheduling fail without publication and compensate to inactive/group-free/unschedulable. Independent malformed owned acknowledgements retain the ID before quarantine; reused foreign IDs receive no writes and cause durable fencing/revocation. Producer tests additionally cover replaced/deleted authority, unknown acknowledgement, recovery ambiguity, compensation failure and restart. Distributed leases and invisible changes inside resolver closures are outside this contract.

Probe patch: inspected all four applied files; fresh application in the owned disposable project matches every patched file hash. Boolean true in trusted account extra suppresses handler scheduling and the fresh-account service path before effects; malformed/missing/false values preserve defaults. Duplicate deep-copy preserves the boolean. The delayed-work test drains the real handler goroutine and the default positive control is meaningful. Coordinator evidence records actual handler red before repair, patched 63 PASS and original service 43 PASS. No Go toolchain is available locally; no independent actual-admin zero-effects result is supplied. BR02 prevents combining these component passes into a zero-effects adapter claim.

Provenance: actual verifier, broker, binder and final additive test module were read. Validated workflow/run/attempt identity is snapshotted, scope determines provider/protocol, workspace activity is checked before admission and inference, and cached responses return the original grant identity/expiry. Binder supports MiMo/Codex Responses, MiMo/Claude Messages and OpenRouter/Codex Responses; unsupported/mismatched mappings deny. Real deployment must supply trusted workspace resolution/activity and revocation wiring: the broker default activity callback is permissive. Original broker.test is byte-identical to the boundary baseline; additive BR04 cases reside in grant-provenance.test. Normal scanning remains enabled per the supplied handoff. The 49/49 coordinator HTTP result predates final relocation, so the exact final test layout must rerun. Redundant private patch is not authoritative integration input.

Fixed launcher/UID helper and financial/native checks remain intact. Source seals the harness and uses fixed no-argument delegation, restricted child environments and safe output reads. Kernel, effective groups, installed import/package sealing, FD boundaries and escaped-descendant teardown require installed-image evidence; offline helper tests do not prove these properties.

## Evidence and mandatory gates

Local Node v24.21.0: independent contracts **4 PASS / 1 expected defect FAIL** (`independent.tap`); producer boundary offline **17/17 PASS**; producer signed identity/binder/native-financial and UID-input helper **12/12 PASS**. All execution used copied exact source in `disposable/`, filesystem-only fixtures and local in-process behavior. Initial copies lacked two fixture dependencies; these were copied unchanged and final producer runs passed. No socket/Go/root/Docker/live-provider/Git operations occurred.

Supplied coordinator evidence: boundary HTTP **76/76 PASS**, provenance HTTP **49/49 PASS** before relocation, patched Go **63 PASS**, original-service control **43 PASS**. These are attributed results, not this reviewer's execution or actual-engine E2E. The genuine prior stock gate remains red; repaired stock and independent real-admin zero-effects gates remain pending.

Mandatory coordinator gates, without waiting here:

1. Integrate exact reviewed bytes plus BR02 correction; retain failed observations and freeze the combined hashes. Historical producer NOT_VERIFIED labels/tree digests are superseded by the coordinator's authenticated input and this current tree hash; record the current applied engine/image identity.
2. Rerun final exact provenance test layout and combined HTTP contracts with scanning enabled. Wire real trusted workspace resolution/activity, revocation, scope/group/key authority and supported provider/agent selection.
3. Verify standard-mode actual stock full DTO, exact duplicate transaction/default-group exclusion, scheduler publication, ambiguous commit/recovery, ownership/reused-ID denial, authority remaps and durable fence/restart behavior against the engine/DB. Run independently measured actual-admin zero-effects after BR02 correction, including delayed work.
4. Integrate binder/caller/workflow validation and seal the new imports in the fixed harness manifest; prove mismatches abort review and receipt publication. Refresh installed-image delegation/UID/FD/lifecycle containment evidence before reuse.
5. Only the authorized coordinator may subsequently assess genuine Actions/native acceptance and custody/teardown. This report grants no such execution or production approval.

Changed only `sub2api-boundary-review-v2/`: report, JSON/hash evidence, independent regression contract, TAP receipts and minimal disposable copies. All other paths stayed read-only. The bounded review objective is finished.

Coordinator custody note: generated disposable source copies are retained privately with original hashes; publishable report/tests remain. Those copies duplicate baseline synthetic Bearer assertions and are not source deliverables. Normal export scanner remains enabled. Independent tests are rerunnable with fresh frozen source setup; no claim that private fixture copies ship in the report.
