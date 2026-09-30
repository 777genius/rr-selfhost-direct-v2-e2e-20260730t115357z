# Operator interface — first runnable patch

Worker never runs Docker, reads credentials or dispatches Actions. Independent review is required before executing operator scripts. This directory is a disposable test interface, not production installation.

Run the key-independent contract suite inside this checkout with **Node 24**:

```
node --test sub2api-spike/*.test.mjs
```

Private broker entry point:

```
node sub2api-spike/serve.mjs /private/broker.json
```

The example config is deliberately invalid until the coordinator sets reviewed main workflow SHA, prebinds the queued Actions run ID/attempt to a workspace/user and supplies PRIVATE server-only group-bound key files. Keys never enter grants. One broker owns one durable ledger volume. Restart invalidates all capabilities and denies issued run IDs. Do not clear a ledger to retry a paid request; authorize a distinct planned run after inspecting effects.

The customer boundary uses injected SERVER metadata and a clearly synthetic-only authentication server. It does not implement ReviewRouter SSO or production membership. Its public export contains metadata only. Admin raw exports include credentials and remain private. It records ambiguous creates as recovery_required and fails closed; an operator must reconcile the prefixed remote account before another create. No automatic retry.

Upcoming execution interface includes immutable-digest Compose, real admin roundtrip, synthetic transport/load/container lanes and sealed-client canary. Until normalized operator outputs exist, these lanes remain NOT RUN. The worker's Git lock preflight found `.git` to be a linked-worktree file and did not follow or bypass it. No commits, staging, push or history changes.

## Exact coordinator execution sequence

All commands here are performed by the trusted coordinator after reviewing the exact exported patch and obtaining immutable image digests. The worker did **not** execute these commands. Choose an unused private subnet/IP after checking host routes and other Docker networks; do not reuse baseline resources. Export only image references/path variables, never key bytes:

```
export CHECKOUT=/reviewed/disposable/checkout
export PRIVATE_DIR=/private/rr-sub2-spike-20260930-control
export BROKER_STATE=/private/rr-sub2-spike-20260930-broker-state
export RECEIPT_DIR=/private/rr-sub2-spike-20260930-receipts
export HARNESS_UID=1000 HARNESS_GID=1000
export CONTROL_SUBNET=OPERATOR_APPROVED_UNUSED_SUBNET
export BROKER_CONTROL_IP=OPERATOR_APPROVED_UNUSED_IP
export SUB2API_IMAGE=REVIEWED_SUB2API_IMAGE_AT_SHA256
export POSTGRES_IMAGE=REVIEWED_POSTGRES_IMAGE_AT_SHA256
export REDIS_IMAGE=REVIEWED_REDIS_IMAGE_AT_SHA256
export NODE_IMAGE=REVIEWED_NODE24_IMAGE_AT_SHA256
export ENGINE_CONFIG="$CHECKOUT/sub2api-spike/operator/sub2api.synthetic.yaml"
node sub2api-spike/operator/check-images.mjs /private/rr-sub2-spike-20260930-image-syntax.json
node sub2api-spike/operator/bootstrap.mjs "$PRIVATE_DIR"
# Coordinator precreates/chowns BROKER_STATE and RECEIPT_DIR to harness UID/GID.
node sub2api-spike/operator/stack.mjs up-synthetic "$RECEIPT_DIR/setup.json"
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm control --test sub2api-spike/*.test.mjs
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm control sub2api-spike/load.mjs /receipts/load.json
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm control sub2api-spike/operator/admin-roundtrip.mjs
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm control sub2api-spike/operator/container-native.mjs
docker compose -p rr-sub2-spike-20260930 -f sub2api-spike/operator/compose.yaml run --rm control sub2api-spike/operator/scheduling.mjs
```

Record stdout/stderr of contract tests privately, then return normalized counts plus failing test names, zero credential values. Preserve every failed attempt and its upstream request count; never replace earlier error totals with a passing final attempt. Operator setup journals refuse reruns after ambiguous creates. Raw script receipts are **observations**, not accepted final evidence: add reviewed provenance and requirement coverage under [receipt.schema.json](../receipt.schema.json), then validate and regenerate the report using `node sub2api-spike/build-report.mjs receipt1.json receipt2.json`. Multiple subcases of E01/E04 must be aggregated into one scenario entry with all error counts retained.

`max_account_switches: 0` is **not effective** in inspected constructor: it defaults to three unless configured greater than zero. The configuration templates express desired policy but do not prove it. Same-account pool retry is separately set to zero for synthetic tests. Stop live setup until fault observations prove no duplicate uncertain upstream effects, or the coordinator explicitly resolves the incompatibility with an independently reviewed engine change. Broker retry count being zero does not disable engine retries. Do not silently bridge protocols or strip Codex proprietary classifiers to pass.

For B/G lifecycle gates, restart only owned services with `node sub2api-spike/operator/stack.mjs restart-engine OUT.json`, `restart-broker`, `stop-postgres`/`start-postgres`, and `stop-redis`/`start-redis`. Probe before/during/after with separate synthetic run IDs and retain errors, duration and effect counts. A crashed broker deliberately leaves its exclusive ledger lock: independently prove the prior container/process terminal before removing **only `/state/run-ledger.json.lock`**, preserving the ledger. Never clear durable run denial state. `backup-restore.sh` restores into a separate networkless owned instance and retains a PRIVATE credential-bearing dump; compare intended counts and run the broker replay test before accepting G04. It currently emits counts only and does not claim full G04 coverage.

## Planned real Actions A01–A03

Only after source/image provenance, independent review, synthetic native paths, uncertain-effect and custody/isolation gates are satisfactory:

1. Keep the existing `rr-gateway-spike-runner:20260930-sealed` fixture and clients untouched. Record immutable runner image ID/digest and measured Codex 0.159.2 / Claude Code 2.1.285. Derive a separate runner registered **only** with `rr-sub2-spike-20260930`, attached to the new runner network. No host socket/homes or database/control mounts. Independent coordinator configures Actions connectivity without giving model subprocesses parent OIDC environment; never publish host ports.
2. Use `sub2api.live.yaml`; create server-only API-key accounts through actual admin API with exactly MiMo Responses `https://token-plan-sgp.xiaomimimo.com/v1`, MiMo Messages `https://token-plan-sgp.xiaomimimo.com/anthropic`, OpenRouter Responses `https://openrouter.ai/api/v1` / model `openai/gpt-4.1`. Use `openai_responses_mode=force_responses` and record the actual passthrough choice. Customer adapter `connect` takes only provider/protocol, reads SERVER credential profiles and pins a private group. Authorized provider key files are opened **only by trusted setup**, never by worker/runner. No subscription pool import.
3. Place `/private/broker.json` and private group-bound key files into the broker-only mount. Set workflow SHA to mechanical integrated reviewed main SHA. Bind queued `runID:attempt` to workspace and server membership before starting the unique runner. Configure optional synthetic customer listener to the broker's exact control IP, never wildcard. No secrets in YAML; actions permissions are contents:read/id-token:write.
4. Execute exactly one planned workflow dispatch for each A01/A02/A03; pause the newly queued unique runner while binding its run ID, then start broker/runner. A failed or timed-out paid run requires private effect inspection before a distinct run is authorized. No automatic rerun. The client uses real separate Read/cat, checks successful terminal and independently reproduces the financial example on the sealed implementation.
5. Supply normalized operator receipt with workflow/harness SHA, source/digests, actual versions, duration, upstream request count, genuine tool/terminal/financial booleans and complete D01–D04 custody/network observations. Client `result.json` alone is insufficient operator evidence. Failures remain FAIL even if a later attempt passes.
6. Teardown only this project with `stack.mjs teardown OUT.json`; remove its staged key copies/state/raw dumps after custody scan, retaining original authorized files. Disable this newly owned workflow through coordinator after evidence export. Confirm private/admin/database ports remain unpublished and baseline containers/evidence are untouched.

F07/F08 need explicit **test-only** OAuth identity approval and normalized lifecycle receipts. Without it they remain NOT RUN. F04/F05 synthetic lifecycle concurrency cannot be proven by asserting mocked token values; source inspection indicates stored gateway base URLs do not redirect real OAuth lifecycle endpoints. No test identity or interception sandbox has been supplied.
