# Independent OAuth correctness/security review

**Decision: REQUEST CHANGES.** The frozen W2 candidate has real coordinator evidence of successful compilation, 23 synthetic service cases and the separate metadata unit test. It also has concrete gaps outside those cases: ordinary asynchronous usage writes can discard a successful rotation and permanently protect the old token; fresh bearer selection does not carry the matching identity/proxy snapshot into forwarding; ownership does not follow a refresh token across account IDs; shadow scheduling semantics regress; manual PAT validation is skipped.

This is a completed bounded review, not approval to ship. Only this report directory and its offline reproductions were written. No production edits, Go/service execution, network, credentials/auth homes, Docker/socket access, Git operations, live providers or agents were used. External gates below are limitations; this lane stops here.

## Exact reviewed inputs

| Input | Binding |
| --- | --- |
| Official archive pin | `96f4c115c9749078f90cbf210a01d39baf3f53b6` (supplied/coordinator-attested; no new Git or network provenance check) |
| Full replacement source.patch | `f26d8e06e4efeebfc4b705efb0f55c52a670ce1a64aee92753fc399b54cecd52` |
| tests-overlay.patch | `5131c0f6e070cc89587786aee0a7ef9d6182094bb0069639b01ee437e1a938fe` |
| Canonical lab tests.patch | `a2276bd1f8a90a7554a81749f669bb4ffddf874883374824ecafa91a3b6e46d4` |
| Official backend fingerprint | 3,137 files, `1d3236198621e693d1c5d971ecd4e3bebf5ca8075b8801869e292792b390165b` |
| Actual execution.json | `9cebf5ed84b6e86bd7a67ca155116313f64d987778bd4a7266d92adef5727347` |
| Actual public case receipts | `fd52d497beeb1b137c91cb8686b6e1d39d4b374c63e0618a152085a27303e27f` |
| Actual gofmt-list.json | `d97a5703aed8da2cdb8b2fa9f1e155cef8db7484d86f3929bac02e81ccb65fa4` |

[evidence.json](evidence.json) records every changed production/test file's before/after hash, independently recomputed fingerprint and receipt reconciliation. All **6,313** entries in `.spike-inputs/INPUT-HASHES.json` matched. A zero-fuzz offline reconstruction of source → canonical tests → overlay reproduced all **28** changed production/test file hashes using only touched files. Source review covered the full replacement diff, materialized new durable/Lua/migration code, modified definitions/imports and surrounding production callers, official shadow/PAT behavior, the real OAuth HTTP implementation, migration runner, and all five materialized lab/contract test files. This is not a claim of an exhaustive audit of every unchanged upstream line.

The producer handoff's NOT RUN statements are historical. The newer pinned Go 1.27.1 coordinator receipt reports exit 0, 32.92 seconds, no failed/skipped tests, compilation successful, 23 named service cases and the metadata unit pass. The public file contains 23 distinct parsed case items, all PASS, each matching a passed test name. It deliberately exposes only status and field names: raw counters, PIDs, events, versions, timings and durable-state values are unavailable for independent re-audit. `execution.json.receipt_count=3` is not the number of case items; without raw captures its aggregation cannot be reconciled further. The task attests real PostgreSQL/Redis execution, and the fixtures implement it. Historical 12-case 6 PASS/6 FAIL baseline results are not W2 failures.

The independent issuer oracle marks a fabricated refresh token consumed before releasing its HTTP response and rejects any second attempt; resource HTTP separately accepts only successor/reauthorized phases. Parent assertions reread real PostgreSQL and inspect actual Redis values. Thus these cases are stronger than repository/provider mocks. They still cover one rotation generation per fixture, fabricated identity decoding and a bearer-only synthetic resource. Production wiring adds a privacy/account-enrichment factory; the child supplies none, so that downstream HTTP work and its latency are outside these receipts.

The actual formatter receipt lists **25** unformatted Go files. Its separate `paths` array lists 27 candidate paths; the authoritative output list is `files`. Formatting is an explicit pending mechanical integration gate, not the reason for this decision, and no frozen source was reformatted here.

## Prioritized concrete findings

### F5 — P1: usage telemetry can strand a successful refresh indefinitely

**Evidence:** [revision trigger](../.spike-inputs/patched/backend/migrations/241_openai_oauth_refresh_ownership.sql#L32), [async usage publication](../.spike-inputs/patched/backend/internal/service/openai_gateway_usage.go#L1125), [UpdateExtra](../.spike-inputs/patched/backend/internal/repository/account_repo.go#L2752), and [completion/load predicates](../.spike-inputs/patched/backend/internal/repository/openai_oauth_durable.go#L94).

The trigger compares the entire row except five bookkeeping/credential fields. `extra` is included. A normal `codex_usage_updated_at`/usage snapshot update therefore increments `oauth_revision` and rewrites its credential projection, even though the bearer, refresh token, owner, lifecycle and routing are unchanged. The upstream repository already calls these usage keys scheduler-neutral; W2's trigger overrides that distinction.

Sequence: claim revision N → issuer consumes the old refresh token → an already admitted request's asynchronous usage write commits → revision becomes N+1 → returned successor fails completion's revision/document CAS. Completion returns the newer active row with `applied=false`; the attempt stays pending. Since the account still contains the consumed old refresh token, the loader and scheduling predicate continue protecting it indefinitely. Subsequent requests cannot recover automatically. No issuer replay is needed to cause the outage.

**Minimal remediation:** separate the refresh/lifecycle/routing revision from cache/telemetry revisions, or exclude explicitly identified neutral Extra mutations from the refresh fence while preserving the full credential document, owner, disable/reconnect and proxy/group fences. Do not release an uncertain claim or retry issuer HTTP. A known returned result may be reconciled against the unchanged refresh identity without letting lifecycle/routing edits lose.

**Required regression:** pause a real successful issuer response, publish an ordinary real usage Extra update, then release the response. Require the successor durably saved, one issuer call, no pending admission block, and preservation of the telemetry update. Existing reconnect/disable/routing tests must remain safe. The offline reproduction executes the actual completion/load predicates with the trigger's source-derived revision effect and an unchanged-state completion control; it does not execute a PostgreSQL trigger.

### F1 — P1: the selected bearer and forwarded route can come from different revisions

**Evidence:** [GetAccessToken](../.spike-inputs/patched/backend/internal/service/openai_gateway_service.go#L1203), [Forward token selection](../.spike-inputs/patched/backend/internal/service/openai_gateway_forward.go#L783), [request/proxy selection](../.spike-inputs/patched/backend/internal/service/openai_gateway_forward.go#L1049), [identity headers](../.spike-inputs/patched/backend/internal/service/openai_chatgpt_headers.go#L8), and `openai_plugin_transport.go`'s direct proxy handoff.

`GetAccessToken` replaces only its local `account` variable with a newly loaded durable account. Its API returns a token/mode, not that validated account. `Forward` retains the old selected account when building `chatgpt-account-id`, FedRAMP/auth metadata, request mappings and proxy URL. A reconnect or proxy replacement committed after selection but before token acquisition can therefore send the new bearer's bytes through the old proxy and pair it with the old upstream account identity. The completion routing CAS does not protect this later forwarding boundary.

This is a tuple-coherence defect, not a demand to retract an already admitted HTTP request after disable. The current implementation actively loads a *new* bearer but keeps *old* route/header inputs. Consequences include authentication failure and sending new credentials through a proxy the durable configuration has replaced. No actual credential exposure was measured in this offline review.

**Minimal remediation:** return/use one validated credential-and-routing snapshot (with revision) at the forwarding boundary; reselect or deny if the selected snapshot changed. Preserve shadow-specific scheduling/quota identity separately while taking bearer, parent identity and proxy from the same credential snapshot. Apply this to HTTP and WebSocket call sites.

**Required regression:** pause between selection and token acquisition, commit reconnect with changed upstream identity/proxy, and assert the real forwarded request is denied/reselected or uses an entirely coherent new tuple. The lab worker explicitly omits `Forward` and supplies no real HTTPUpstream; its synthetic resource checks only the chosen bearer. It cannot establish this property. The supplied reproduction is a source-bound interleaving model, not an executed Go forwarding test.

### F2 — P1: durable ownership is account-scoped, allowing the same consumed token on another account

**Evidence:** [claim](../.spike-inputs/patched/backend/internal/repository/openai_oauth_durable.go#L53), [attempt schema](../.spike-inputs/patched/backend/migrations/241_openai_oauth_refresh_ownership.sql#L4), generic admin create (`admin_account.go:478`), CRS create (`crs_sync_service.go:673`), and [token-only duplicate detection](../.spike-inputs/patched/backend/internal/repository/openai_oauth_durable.go#L244).

Claim row locks, `(account_id,revision)` uniqueness and all consumed-token history predicates are scoped to one account ID. Two generic-created/imported account rows holding identical refresh material can each durably claim and each reach issuer HTTP. Reimporting the old material under another ID after a crash/failed completion also bypasses the retained non-replay evidence. The dedicated DuplicateAccount operation correctly refuses OAuth, but generic creation/import and the DB schema do not enforce refresh-token uniqueness. The token-only endpoint detects ambiguous duplicates; ordinary account/manual/background refresh does not.

**Minimal remediation:** key durable consumption evidence by a stable keyed digest of issuer/client/refresh-token identity, with transactional uniqueness/ownership across account IDs, or enforce one canonical credential owner and make imports reference it. Preserve consumed/uncertain evidence across account deletion/recreation. Avoid plaintext token indexes. Continue to allow a genuinely reusable, successfully completed nonrotating refresh token under an explicit safe state transition.

**Required regression:** two real account IDs with the same fabricated token must produce one consumption domain; a second ID importing an uncertain/consumed token must be protected without issuer replay. The SQLite reproduction executes the extracted INSERT with documented dialect adaptations: same account/new revision inserts zero rows; another account/same token inserts one. This proves the relational scope gap, not actual PostgreSQL locking or a live provider replay. All 23 current service fixtures use one credential-owning account per case.

### F3 — P2: durable credential admission applies the parent's scheduling vetoes to Spark shadows

**Evidence:** [durable loader](../.spike-inputs/patched/backend/internal/repository/openai_oauth_durable.go#L22), [parent admission](../.spike-inputs/patched/backend/internal/service/openai_oauth_durable.go#L185), scheduler parent lookups and gateway parent resolution, versus [upstream credential predicate](../.spike-inputs/patched/backend/internal/service/account.go#L207) and `openai_spark_shadow_parent_health_test.go:92`.

Official behavior deliberately allows an active credential parent with `Schedulable=false`, a global rate-limit window or global overload to serve an independently schedulable Spark shadow. W2 requires `a.schedulable` in `LoadOAuthState` and calls `IsSchedulable()` after parent resolution in selection/token paths. Manually paused parents are rejected by SQL; globally limited/overloaded parents are rejected by the later predicate. Shadow traffic and some quota queries fail even though `IsCredentialUsableForShadow()` accepts the parent. Genuine disable, deletion, credential uncertainty and shared transport cooldown should still reject.

**Minimal remediation:** introduce durable credential-parent admission distinct from direct-account scheduling admission; keep pending/revision/document/lifecycle validation, but apply the official credential-parent predicate and the shadow's own scheduling restrictions. Ensure refreshing the parent for a shadow uses the same durable owner without requiring the parent's direct scheduling switch.

**Required regression:** exercise real scheduler + bearer selection with paused, globally rate-limited and overloaded parents; verify independent shadow success, and verify true parent disable/pending/shared cooldown still denies. Existing upstream predicate unit tests alone do not traverse the new SQL loader. The offline extracted-loader check rejects an active paused parent while the independent upstream oracle accepts it.

### F4 — P2: manual PAT/token-only account refresh is now a silent no-op

**Evidence:** [manual helper](../.spike-inputs/patched/backend/internal/service/openai_oauth_durable.go#L155), its early conditional return at line 99, [NeedsRefresh](../.spike-inputs/patched/backend/internal/service/token_refresher.go#L102), and [previous PAT validation/enrichment operation](../.spike-inputs/patched/backend/internal/service/openai_oauth_service.go#L341).

Both admin account refresh handlers now use the forced-window conditional helper. `NeedsRefresh` returns false for PAT and for accounts lacking a refresh token, independent of window size. Those handlers report success without reaching the existing PAT whoami validator or access-token-only metadata/privacy enrichment. A revoked/invalid PAT can receive a successful manual-refresh response and metadata does not refresh. PAT request bearer use remains separately supported; this finding concerns explicit manual operation compatibility, not an allegation that PAT needs rotating OAuth refresh.

**Minimal remediation:** retain a separate explicit PAT validation/access-only enrichment branch with durable revision/document CAS for its metadata writes. Keep rotating OAuth under the claim path. A forced rotating-refresh window does not express manual validation intent.

**Required regression:** use a bounded offline fabricated validation endpoint or coordinator fixture and observe exactly one PAT validation operation, invalid-PAT failure, and updated validated metadata. For access-only accounts, verify intended enrichment semantics without posting an empty refresh token. The local reproduction proves branch reachability only; no provider was contacted.

## What the frozen tests actually support

| Requirement | Evidence and scope |
| --- | --- |
| One PostgreSQL owner across request/background/admin/CRS/mixed Redis | Shared durable helper and owner-required service entry points inspected. Request/background/mixed Redis have real synthetic PASS cases. Admin/CRS convergence is source evidence; no handler-level service case. F2 limits ownership to an account ID. |
| Uncertain consumption is never retried by lease expiry/restart | No pending expiry/takeover; timeout/transport uncertainty returns provider containment before retry policy. Crash, TTL expiry and real rejected-write cases PASS for one account ID. Never delete this evidence to restore availability. |
| Lost completion ACK requires exact completion | Reread checks exact owner, attempt revision, completion revision, result document and current row. Driver fixture commits the real transaction before hiding ACK; its observer distinguishes completion UPDATE from claim INSERT. PASS is meaningful for that fault. Claim-ACK loss, every driver failure and role variant are not independently measured. |
| Revision/document/lifecycle/routing CAS | DB-generated decimal revisions, complete-document and owner CAS, proxy/group triggers, transactionally persisted result/outbox. Same/reversed caller clocks and stale disable/new reconnect cases PASS. F5 identifies an excessive telemetry fence; F1 identifies a later forwarding mismatch. |
| Cache hit durable eligibility | Cache hit rereads after actual Redis I/O; matching DB token/revision/expiry required. Paused-read/direct-disable case PASS. Cold-path cache publication follows a final DB read; this does not promise instantaneous revocation after that admission point. |
| Owner-safe release, tombstones, exact large integers | Literal Lua uses decimal string length/lexical order, not floating point; comparison/delete release uses the acquisition handle. Real Redis cases PASS. Local literal-Lua assertions also pass for adjacent >2^53 values, matching/stale token reads, equal/older writes after tombstone and newer revision republication. Harness is Lua 5.3, not a Redis rerun or cluster/eviction acceptance. |
| Redis outage availability | Eight local requests must all succeed in the fixture; real PASS supports that bounded case. Two-process contender tests allow safe denial and do not establish universal successful availability or latency SLOs. PostgreSQL remains mandatory. |
| Scheduler metadata | Original seven allowed fields plus exact `_oauth_revision`; access/refresh/ID tokens excluded. Serialized-map equality/immutability and adjacent revisions checked by separate real Go unit PASS. Existing `api_key` field remains deliberately allowed; do not describe all metadata as credential-free. Full account cache payload still contains credentials. |
| PAT/token-only compatibility | Request PAT branch inspected; manual validation regression F4. Raw refresh-token endpoint now requires exactly one registered active/schedulable OAuth account, matching proxy and available client identity. Unregistered-token onboarding previously accepted by the upstream endpoint now fails; this is an explicit breaking contract needing migration/versioning, not a reason to restore an unsafe bypass. |
| Migration/SQL permissions/storage | Added tables/column/triggers inspected against Ent account/proxy/group/outbox schema and transactional checksum migration runner. Fixture uses actual migrations and injects a real rejection trigger. No restricted production-role, upgrade load, full migration regression/race suite or schema-diff acceptance is supplied. |
| Live OAuth, latency, retention | Unmeasured. Synthetic issuer JSON/resource observations cannot clear real entitlement, provider token behavior, latency, backup/deletion or retention policy. |
| Native API key/probe and OAuth image integration | Separate fork/image lane. Neither native correction reports nor these repository cases prove integrated OAuth image deployment, forwarding/SSE/billing or mixed-image behavior. |

## Storage/security observations and rollout limits

`expected_credentials` and `result_credentials` retain full JSONB documents, including old/new refresh and access tokens and other credential fields. There is no production cleanup/TTL, encryption envelope or deletion linkage in this patch. Hard deletion deliberately leaves attempt records; soft deletion also leaves them. Redis full-account payloads and fence hashes have no TTL; access-token payloads have bounded TTL. Non-replay evidence is necessary, but retaining complete plaintext historical documents forever is not necessary for every completed attempt. Storage growth, backup copies, retention duration and unauthorized access were not measured. This is a concrete increased data footprint with an unresolved retention design, not evidence of a breach.

Before any bounded rollout, define minimal retained keyed fingerprints/non-replay records, redact completed historical credential payloads where safe, protect pending/reconciliation material, and establish deletion/backup/role access handling. Do not clear pending records or Redis fences on a timer as a workaround. Supply actual least-privilege runtime-role checks for reads/inserts/completion, account/group/proxy trigger writes and outbox publication. These functions are ordinary invoker functions; no SECURITY DEFINER or new GRANT is supplied. The same-role synthetic migration run does not establish a separate migrator/runtime permission model.

After fixing the concrete findings, a small isolated rollout should use the exact rebuilt patch/image and migration binding, one canonical credential owner, bounded account set and immediate protected-state monitoring. Keep PostgreSQL required and fail closed on uncertain state. Measure provider success, DB query/contended wait load, p95/p99 latency, pending age and repair outcomes. The loader may poll every 20 ms for up to two seconds, hydrate via Ent then validate SQL, and several selection/token paths repeat those reads; quantify that cost instead of inferring it from the 32.92-second suite duration. Verify role/upgrade/rollback behavior and the original suite plus the new focused regressions with the authorized coordinator. Rolling back to upstream refresh logic while pending consumed-token evidence exists risks replay; quarantine/reconcile affected identities first.

No live-provider clearance, OAuth image integration approval, retention clearance or latency guarantee is granted. Formatting and other external gates are handed off without waiting.

## Reproduction and handoff

Run from the workspace root:

```sh
python3 sub2api-oauth-review/reproductions/offline_review.py
```

Observed result: PASS for 6,313 immutable input hashes, exact 28-file patch reconstruction, 23 public receipt/name checks, five source counterexamples and literal-Lua assertions. **PASS here means the independent checks/counterexamples hold; it does not mean the candidate is approved.** SQLite removes PostgreSQL casts and adapts UPDATE alias/RETURNING syntax; it does not implement PostgreSQL row locks/triggers. Two counterexamples are branch/interleaving models; telemetry models the inspected trigger's effect and executes actual completion/load SQL. No report duplicates the whole upstream tree, and temporary touched-file reconstruction is deleted automatically.

Deliverables: `REPORT.md`, `review.json`, `evidence.json`, `reproductions/offline_review.py`. Production inputs remain immutable. The independent review is complete; remediation and integration belong to the controller.
