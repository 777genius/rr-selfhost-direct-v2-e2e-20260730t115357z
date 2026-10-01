Bounded consumer glue for the approved disposable synthetic sandbox is delivered in the seven owned source/workflow files plus this directory. These are fixture and handoff tools, not a production deployment. See [REPORT.md](REPORT.md), [source-hashes.json](source-hashes.json) and [verification/](verification/). Other lanes, their historical receipts and native financial checks remain preserved. The controller applies/commits the workspace diff; this worker performed no Git writes.

Reproduce the worker's socket-free tests with Node 24.21.0:

```sh
node --test --test-name-pattern='offline|stock admin create' sub2api-spike/customer.test.mjs
node --test sub2api-consumer/operator.test.mjs sub2api-spike/run-client.test.mjs sub2api-spike/granted-run.test.mjs sub2api-spike/evidence.test.mjs sub2api-spike/runner-isolation.test.mjs
```

The caller tests substitute process/I/O boundaries and synthesize fixture events in memory while executing the actual caller, binder and financial validator. They never execute an agent binary or publish a real Actions receipt. The workflow test executes the actual embedded identity validator before its publication line. Customer tests substitute only admin transport and retain real filesystem persistence. HTTP suites, Go, actual engine/DB, Docker, installed UID/import isolation, providers and Actions are NOT_RUN here.

The following commands are prepared for the coordinator only and were NOT_RUN. Use the exact dedicated `rr-sub2-spike-20260930` project, reviewed source, pinned images, its isolated disposable database and root-owned0700 private directory. Stop all broker/runner/inference activity and engine processes before direct SQL seeding. Confirm the database is the dedicated fixture database and matches the pinned upstream schema. Do not run SQL against a shared or production database. Keep inference egress blocked for the admin zero-effects gate; the independent observer must still count attempts and DB capability writes.

The existing bootstrap sets `RUN_MODE=simple`; it cannot satisfy this lane's full DTO contract. The coordinator must configure and observe `RUN_MODE=standard` before starting the repaired engine. No bootstrap/Compose/serve source owned by other lanes was edited. Under `/private`, supply root-owned0600 `installation.json` only after validating the approved patched image:

```json
{
  "standardMode": true,
  "openaiDisableCapabilityProbe": true,
  "engineDigest": "sha256:<actual approved patched image digest, 64 lowercase hex>",
  "probePatchSHA256": "7d894dacf09a356992dfed1fb4b351c50b375a666b3e8625ae4fa2678748ff45"
}
```

Replace the digest placeholder with the actual image identity. This is an explicit supported-installation capability from server configuration, not cryptographic proof or a client attestation. Ordinary model metadata, customer input and inference bodies cannot authorize it. The observed image must match it. Supply the existing server-only admin key as root-owned0600 `/private/admin.key` through coordinator custody; do not place key bytes in agent environments, Actions inputs, receipts or CI artifacts.

Using the coordinator's reviewed Compose environment, from the repository root:

```sh
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml stop broker sub2api
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm --no-deps --user 0 control sub2api-spike/operator/live-setup.mjs plan /private
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml exec -T postgres psql -X -qAt -U rrsub2 -d rrsub2 < "$PRIVATE_DIR/template-seed.sql" > "$PRIVATE_DIR/seed-ack.json"
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml up -d sub2api
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm --no-deps --user 0 control sub2api-spike/operator/live-setup.mjs verify /private
```

`plan` writes two exclusive0600 files and creates no account itself. The SQL inserts six uniquely marked workspace/provider/protocol templates atomically as inactive, group-free and unschedulable, using synthetic inert credentials and an `.invalid` endpoint. It bypasses handler scheduling entirely while the engine is stopped; it never uses ordinary active real-key create. No provider request is needed for seed construction. Actual schema execution and absence of effects still need coordinator observations. `verify` requires standard full DTOs, checks all group representations, scope, type/platform/status/scheduler, exact IDs and the OpenAI boolean flag, and exclusively writes `fixtures.json` plus guarded `template-cleanup.sql`. Redacted null credentials and omitted empty group slices are valid; lite/malformed/contradictory authority is denied.

A lost SQL acknowledgement never permits reinsertion. Keep the plan and failed output privately, stop routing, and invoke `verify` against full list/GET authority: exactly one seed for each of the six markers must exist. Missing, extra/conflicting matches or reused IDs deny. Existing `fixtures.json` also prevents overwrite. A partial preparation failure requires private inspection, not an automatic setup retry. Account duplicate lost acknowledgements retain the adapter's durable intent; recovery requires its full owner/binding/workspace/name/type/platform contract and exactly one owned copy, with no second duplicate.

Before roundtrip, the coordinator installs a separate instrumented transport/DB-write observer (implementation belongs to the external control lane) at `http://probe-observer:8791` on the approved internal network. Supply root-owned0600 `/private/observation.json`:

```json
{"endpoint":"http://probe-observer:8791","captureID":"<32 lowercase hex for this dedicated observation>"}
```

`GET /snapshot` returns `{captureID, engineDigest, requests, capabilityMetadataWrites}` with cumulative nonnegative safe integer counters. `POST /drain` accepts `{captureID}` and returns the same fields plus `drained:true` only after independently observing completion of all queued probe work. The observer must cover every upstream dispatch path, including alternate transports/retries, and every capability metadata write. It must isolate this capture, preserve counters without reset and bind the actual image. A sleep, timer or declared zero is insufficient. Stock positive controls should observe the known hidden effects, then the patched gate must observe zero deltas for both counters. No observer implementation or real telemetry is fabricated by this lane.

```sh
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm --no-deps --user 0 control sub2api-spike/operator/admin-roundtrip.mjs
```

The roundtrip supplies trusted template IDs and installation capability, measures baseline/final deltas, and retains unknown counts as JSON null with `telemetry:NOT_RUN` on missing evidence. Nonzero effects fail. A failed lifecycle stays FAIL even if telemetry later drains successfully. Journal creation is exclusive, resource names include the fixture owner, and each acknowledged group/user/key ID is journaled before subsequent awaits. Lost group/user/key acknowledgements require the coordinator to read full DTOs/list authority for the exact unique owner-qualified name/email and validate user/group/key relationships before any cleanup; zero or multiple candidates deny mutation. Never rerun a POST to recover its acknowledgement.

To wire the general customer server, the controller/owning lane must pass the sealed server installation object into `new AdminAPI({..., installation})` and the verified `fixtures.quarantineTemplates` into `customerAdapter`. Current `serve.mjs` supplies neither; it intentionally fails closed for preparation until that separately owned integration is applied. No customer-controlled source may populate these fields.

Before a native canary, install the reviewed updated `run-client.mjs` and existing `granted-run.mjs` under the fixed root-owned `/opt/rr-sub2-harness/sub2api-spike/` directory, with sealed ancestor/import/package paths. The unchanged fixed launcher checks the manifest before Node import evaluation. Regenerate it in the installed image, including the binder:

```sh
cd /opt/rr-sub2-harness
sha256sum sub2api-spike/run-client.mjs sub2api-spike/granted-run.mjs sub2api-spike/runner-isolation.mjs sub2api-spike/evidence.mjs gateway-spike/evidence.mjs operator/runner-containment.mjs reviewed-workflow.sha > harness.sha256
chmod 0444 harness.sha256 reviewed-workflow.sha sub2api-spike/granted-run.mjs sub2api-spike/run-client.mjs
```

The coordinator installs `reviewed-workflow.sha` containing the exact final integrated40-hex workflow source SHA, verifies root ownership/no group-or-other writes throughout import ancestors, and records the installed manifest and immutable image identity. Preserve the existing launcher, UID isolation and financial/native validator. The new runtime path checks augment the manifest; offline stubs cannot prove installed import sealing. No genuine canary is authorized or executed by these tests.

Cleanup commands below are also NOT_RUN. First stop dispatch/routing, revoke grants and block engine inference. Write root-owned0600 `/private/cleanup-control.json` with the verified fixture owner and `routingStopped:true`, `grantsRevoked:true`, `engineInferenceBlocked:true` only after the coordinator has performed those operations. The isolated retirement command uses existing full DTO/ownership validation and recovery, never changes durable intent IDs or adopts by name alone:

```sh
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm --no-deps --user 0 control sub2api-consumer/retire-owned.mjs
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml stop sub2api
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml exec -T postgres psql -X -qAt -U rrsub2 -d rrsub2 < "$PRIVATE_DIR/template-cleanup.sql"
```

Do not run template cleanup until owned copies are confirmed retired. The SQL requires all six exact IDs AND fixture-owner/workspace/provider/protocol/type/platform matches, inactive/unschedulable state and no memberships under table locks, or aborts the entire transaction. It deletes no arbitrary prefix-matched account. Preserve ambiguous or foreign/reused IDs for operator investigation. If a cleanup acknowledgement is lost, inspect those exact IDs and the retained journal; do not infer a successful deletion or repeat writes blindly. With no live/uncertain owned resources remaining, the coordinator may use the existing reviewed `stack.mjs teardown` for only the dedicated named project/networks/volumes, removing fixture users/keys/groups through destruction of that disposable database. Retain private failed observations according to existing custody rules. Shared resources and other lanes stay outside cleanup.
