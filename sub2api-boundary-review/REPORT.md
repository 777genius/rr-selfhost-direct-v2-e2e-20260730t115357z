# Independent boundary review

**CANARY_NO_GO.** The frozen proposal has a proven stock DTO integration break, additional control-flow and evidence-binding blockers, and an upstream capability-probe path that must be contained before real credentials are installed. This bounded review is complete; it does not wait for the operator or approve genuine Actions execution.

Task: rr-gateway-spike-20260930-boundary-review-w1, attempt 2, 2026-10-01.
Exact reviewed `.spike-inputs/candidate.patch` SHA-256: `a292e147a7630c44d6592f2239a86120ca1d782ce5c8b611d944e095a8866805`.
All eight producer source/workflow hashes match the frozen candidate. Paths below are relative to `.spike-inputs/candidate/`; backend references are relative to `.spike-inputs/upstream/`. Full evidence hashes, machine-readable findings and limits are in `review.json`.

## BR01 — P1: Stock empty-group DTO breaks connect and trusted orphan reconciliation

`sub2api-spike/customer.mjs:24` (R11; SOURCE_AND_OFFLINE_CONTROL_FLOW).

Stock standard-mode empty groups omit both group_ids and groups. GET fails quarantine_template_denied; independently isolated PUT fails quarantine_template_drift; a duplicate acknowledgement with this shape fails quarantine_invalid before upstreamID is recorded; omitted groups on a recovery list item fail recovery_quarantine_denied.

Minimal correction: Normalize group fields only at a validated pinned standard-mode stock AdminAPI DTO boundary. Omission of both is empty under the inspected full-detail and compact-list contracts. Reject present null/non-array/malformed/conflicting fields; retain other ownership/platform/status/scheduling checks. Require standard mode or independently verify unfiltered group membership. Apply consistently to template GET/PUT, duplicate, and recovery list/detail. Add actual DTO serialization and real-admin regressions.

## BR02 — P1: Preparing inactive template triggers an upstream model probe outside routing quarantine

`sub2api-spike/customer.mjs:28` (R11; SOURCE_REACHABILITY_AFTER_BR01_CORRECTION).

Once BR01 is corrected, PUT with real OpenAI API-key credentials schedules the stock Responses capability probe. That path bypasses status/schedulable/group checks and posts a tool-choice-required model request using the key and configured model, before duplicate acknowledgement or canary dispatch. force_responses and billing-probe-disabled flags do not skip this handler probe.

Minimal correction: Use an independently verified no-probe credential preparation path or explicitly contain and suppress capability probes for quarantined templates in the trusted engine/control lane. No adapter-only status/group change disables this stock probe. Prove zero provider effects using a counting synthetic upstream through actual handler execution, including delayed goroutine execution; do not install real credentials until that gate passes.

## BR03 — P2: Promotion can publish an obsolete workspace group across awaits

`sub2api-spike/customer.mjs:98` (R11; OFFLINE_CONTROL_FLOW).

Remapping trusted workspace group from 11 to 22 during group-attachment acknowledgement still returns active and enables account scheduling in group 11. Subsequent read reports group_drift. Membership checks do not revalidate routing mapping. Cross-tenant inference is conditional on old-group reassignment; it was not demonstrated.

Minimal correction: Fence routing configuration changes with a revision/lock coordinated with workspace keys and broker grants, and revalidate expected group/authority after every promotion await and before scheduling/publication. On drift compensate and revoke/fence. Verify a real-engine remap/reassignment race before claiming tenant isolation.

## BR04 — P2: Normalized Actions run metadata is not bound to the signed OIDC run

`sub2api-spike/run-client.mjs:67` (R07; SOURCE_DATA_FLOW).

Broker authorizes signed run_id/run_attempt, but grant returns only capability/model/expires. Trusted harness prints run_id/run_attempt from UID1001-supplied stdin without comparing them to signed claims. A permitted launcher caller can label evidence with a different syntactically valid run/attempt. Workflow checks only workflow_sha. This does not prove unauthorized grant issuance or root execution.

Minimal correction: Return broker-verified runID/attempt/workflow identity in the grant and compare against stdin before agent execution; construct receipt from verified values. Extend workflow receipt validation to run/attempt and provider/agent. Add mismatch denial tests at the grant-to-receipt boundary.

## BR05 — P2: Bundled stock-admin gate omits required trusted quarantine templates

`sub2api-spike/operator/admin-roundtrip.mjs:36` (R11; SOURCE_AND_OFFLINE_CONTROL_FLOW).

This unchanged operator constructs fresh workspace records with no quarantineTemplates, supplies no adapter option, then connects. Current AdminAPI fails quarantine_template_required with zero account requests. The bundled gate cannot validate the new path; coordinator custom setup is separate evidence.

Minimal correction: Provision per-workspace scoped inactive/unschedulable/group-free templates using inert synthetic credentials, persist trusted IDs, and pass them to this gate. Exercise exact adapter GET/PUT/duplicate/recovery against the pinned stock engine, including omitted DTO group fields. Preserve intentional fail-closed behavior; do not restore ordinary-create fallback.

## Why the empty-group correction is safe only at the actual DTO boundary

The operator's stock-admin failure is consistent with inspected source, and independently reproduced in `offline-oracles.json`. Standard-mode `dto/types.go:324-325` marks both `group_ids` and `groups` as `omitempty`; compact list `types.go:422` also omits empty `group_ids` and does not expose `groups`. `dto/mappers.go:282` copies service GroupIDs; `:436-456` only fills Groups when nonempty. `repository/account_repo.go:265-278` GET uses `accountsToService`; `:3388-3423` loads group memberships and propagates query failures. `:3469-3520` builds membership maps only for actual rows. Thus a successful standard-mode full account response with neither field is the documented wire representation of no group memberships, rather than an unloaded successful GET. PUT returns a fresh repository GET (`service/admin_account.go:906-918`); duplicate returns its exact group set (`:344-345`); compact lists copy GroupIDs (`dto/mappers.go:495`). These paths all require the correction.

Normalize inside the stock transport's validated full-detail or list-item decoder, with the deployed source and standard run mode verified. Validate the account envelope and positive ID, every present group field and entry, and consistency if multiple representations are present. If both fields are absent under that exact contract, materialize `group_ids: []`; do not convert present null, strings, objects, malformed entries, conflicting representations or arbitrary injected adapter records into empty groups. An unexpected nonempty `account_groups` must also deny quarantine. Keep all scope/owner/type/platform/status/schedulable checks. Validate nonempty routes using the same decoder.

`AccountWithConcurrency.MarshalJSON` (`account_handler.go:292-325`) changes semantics in simple mode: composite memberships can be filtered from group IDs, groups and account_groups. An empty visible set there does not independently prove an empty DB set. Require verified standard mode, or an explicit unfiltered independently verified membership source. A generic `a.group_ids ?? a.groups?.map(...) ?? []` is insufficient. This reviewer has not changed the frozen implementation.

The existing HTTP fault lab creates and returns `group_ids: []` on synthetic templates and duplicates (`customer.test.mjs:14-34`), and models PUT with Object.assign. Its fixtures conceal the stock omission and the handler's asynchronous probe. They are useful persistence/authorization fault tests, not duplicated real-DB transaction coverage, and their green count cannot validate this stock contract. The independent oracle separately isolates GET, PUT, duplicate acknowledgement and compact recovery omission; it checks one create at most and no acknowledged upstream ID on the invalid duplicate response. It does not emulate a real database.

## R07 assessment and remaining execution boundaries

The fixed no-argument launcher checks root and SUDO_UID1001, checks the installed manifest, clears environment and executes a fixed Node/harness path (`operator/runner-launcher.sh:4-9`). Root harness does not execute a checkout path. The child helper creates an allowlisted environment, drops each CLI/version/numeric process to UID/GID1002, ignores stdin and exposes only output pipes (`runner-isolation.mjs:37-40,61-82`). OIDC and Actions control tokens are not intentionally passed to children; the bounded broker run capability is. Tool and fixture checks seal root-owned ancestor paths and pin fixture bytes. Tool package dependency trees still depend on operator installation sealing, not merely the entrypoint checks.

The output reader rejects final-component symlinks with O_NOFOLLOW, nonregular/foreign-owned/hardlinked/oversized files and caps reads (`runner-isolation.mjs:51-59`). Its concrete review path is directly inside the UID1002 home under a root-owned parent, so the final-component protection is meaningful. Stderr is drained and suppressed. Evidence projection uses fixed vocabulary from `gateway-spike/evidence.mjs`; token-bearing raw transcripts are not published. Existing financial finding, separate source/rules reads and local numeric reproduction assertions remain intact. No arbitrary privileged command or token-output vulnerability was proven in these paths. BR04 is a provenance binding defect, not a root-command defect.

Children are launched as detached process groups and group-killed on timeout/limit/close. This alone is not proof of cleanup of a hostile descendant that starts a new session. The kernel receipt described in operator guidance covers UID/proc/sentinel/tool-IO/symlink checks, not FD or escaped-descendant lifetime. Before another run reuses UID1002, require an independent lifecycle gate (cgroup/container-wide teardown, or single-run disposable runner destruction). This review does not run privileged probes.

The newest operator guidance reports derived-image UID1002/proc/sentinel/normal tool IO/hostile symlink and same-UID negative-control PASS. That advances containment evidence, but no raw normalized receipt/image digest is available here. It also reports initial sudo failure: base `/usr/bin/sudo` mode700 and broad `%sudo` rule with no includedir. Installing just a fragment would not establish the intended policy. Operator must install a complete minimal visudo-validated sudoers, restore sudo setuid4755, remove runner extra groups/broad privileges, and prove fixed no-argument delegation with negative cases. This is an installation gate, not a defect inferred from new filenames. `runner-isolation.mjs`, its test and `operator/runner-launcher.sh` are reasonable bounded names; explicit path approval remains the coordinator's integration responsibility.

## R11 assessment beyond blockers

The stock duplicate service reads the source, preserves non-runtime ownership markers, skips default groups, and sets Schedulable=false before persistence (`service/admin_account.go:244-345`). `repository/account_repo.go:209-264` commits the account, exact memberships and scheduler outbox together. `service/account.go:181-185` rejects unschedulable accounts even when status is active. This is a sound source-level choice over ordinary-create fallback. Source pin authentication and deployed transaction/scheduler behavior remain external gates.

Adapter intention/owner/binding are durably written before duplicate; Idempotency-Key is a durable binding ID and the adapter attempts creation once. Acknowledged ID and bound ownership are persisted before group attachment. Ambiguous create stays recovery_required, with no automatic unsafe retry. Trusted reconciliation is absent from customer HTTP routes and requires exact name, owner, binding, workspace, platform and type, one bounded-list match and quarantine validation. Other-tenant or name-only adoption is denied by those checks. BR01 currently prevents legitimate stock omission recovery; BR03 prevents a claim of stable routing authority during promotion.

Membership is rechecked at adapter awaits and after grant revocation on mutations. Compensation unschedules and clears groups; failure fences workspace authority and revokes grants when the integration supplies the callback. Startup fences interrupted bound/fenced/legacy uncertain state. This does not guarantee cancellation of already-issued upstream requests. Real commit-before-503, filesystem-failure, restart, duplicate idempotency, tenant attribution, routing remap and broker-revocation behavior must be exercised against the actual engine/DB/scheduler. The adapter source contains no ordinary-create fallback.

BR02 is conditional on BR01 being repaired, or a verified transport normalizer allowing PUT: credential-bearing PUT schedules `account_handler.go:1213-1241`'s background capability probe. `openai_apikey_responses_probe.go:124-197` neither checks inactivity nor schedulability nor group membership, and builds a model request using the actual key/mapping. `force_responses` and `upstream_billing_probe_enabled=false` are not skip conditions there. This is distinct from a schedulable orphan: it is an unplanned provider effect from preparing the template. Stock-source reachability is proven; no provider request was executed by this reviewer. Any zero-upstream-effects gate must count this asynchronous path, rather than initializing a receipt counter to zero.

## Verification and attributed external evidence

- PASS: independent offline adapter oracles, including all four stock omission checks, missing-template zero-admin-call denial, and routing-remap publication. `node sub2api-boundary-review/offline-oracles.mjs` produces the checked-in normalized observations. Assertions passing means the reported defects were reproduced.
- PASS: runner helper and financial/native evidence contracts, 7/7 under local Node v24.21.0.
- PASS: selected stock-default-denial and legacy-orphan tests, 2/2; HTTP/socket cases not selected.
- PASS: shell syntax; exact patch hash and all eight producer source/workflow file hashes.
- Coordinator contract artifact records exit=0 in pinned Node24 image with none-loopback-only networking; original task reports 61/61. Stored summary is empty. This reviewer did not rerun socket tests or treat that result as real-engine proof.
- Operator guidance reports real ungrouped DTO GET gate FAIL, kernel containment negative-control PASS, and initial sudo gate FAIL with repair underway. No finished sudo/install or actual admin scheduling E2E PASS is supplied.
- NOT RUN here: Docker/root/UID-change/kernel probes, network/socket/real DB/admin/scheduler tests, credentials, paid inference, genuine Actions dispatch, source authentication. Producer source-pin-check remains NOT VERIFIED. No Git operations were performed.

## Handoff and completion audit

Changed only `sub2api-boundary-review/{REPORT.md,review.json,offline-oracles.mjs,offline-oracles.json}`. Prior partial oracles were retained and extended. All producer and upstream code remained read-only. No commits/staging/pushes, installation changes or operator messaging occurred.

Required bounded review outputs now exist with exact patch hash, actionable path/line severities, minimal corrections, proven-vs-external evidence and CANARY_NO_GO. R07 fixed launcher, token custody, child environment/UID, safe output and FD/process-group assumptions were inspected; R11 actual DTO/handler/service/repository/transaction semantics, stable membership/routing, idempotency, reconciliation and cross-tenant marker checks were inspected. Test-double limitations and the newest runtime guidance were incorporated. Review completion is independent of gate success; no operator wait is needed.

Before any isolated Actions canary: integrate corrected code into a newly frozen patch and repeat independent review; authenticate stock source/images; pass actual admin/DB/scheduler/quarantine/recovery and zero-probe-effect gates; finish minimal sudo and sealed image installation with normalized kernel/FD/cleanup receipts; bind run/attempt evidence to signed broker claims. Preserve failed observations, inspect effects and fence ambiguous resources; do not automatically retry or restore unsafe create. Any eventual GO applies only to the isolated operator canary, never production.
