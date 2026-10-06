# Native Redis slot lab

The red contract is [RED.md](RED.md). This is an isolated root-operated E2E harness for actual native Sub2API handler ownership in real Redis. It does not modify product source. Actual database, Redis, Docker, network and provider runs are **NOT RUN** by this worker. Cancellation W3 + memory W2 must be merged and built externally before execution; the current supplied native/probe image is not claimed to pass.

The runnable package consists of one Python root driver, five owned Node modules and four reused public transport modules. `prepare.py` uses the public canonical `sub2api-transport-packaging/prepare-standalone.py` helper's safe reader and exact runtime ledger to reconstruct those four modules from the canonical overlay. It verifies four exact modules and records their hashes, then applies explicit small mock deltas. It neither copies nor claims to reconstruct all 103 historical runtime files. With `--base-root`/`canonical_base_root`, the same helper optionally verifies the full 103-file runtime before selecting the same four modules. No `.spike-inputs` path is required to rerun the package.

Offline commands from the repository root (Python standard library, Node 24; no sockets):

```sh
python3 sub2api-slot-lab/prepare.py --output sub2api-slot-lab/build
node sub2api-slot-lab/build/sub2api-slot-lab/run.mjs --plan
node --test --test-reporter=tap sub2api-slot-lab/offline.test.mjs
python3 -m unittest discover -s sub2api-slot-lab -p offline_test.py
```

Preparation deliberately refuses an existing output. Preserve or remove your own generated `build/` before repeating it. The tracked package contains no copied historical runtime tree. Offline checks validate queue shapes, request membership, cancellation failures, actual setup/admin-transport calls with inert offline responses, exact lease reads, fragmented native SSE fixtures, deadline overhead including assertions, preservation of real failure counts/TTLs before gate evaluation, durable create intentions and ownership-safe Docker cleanup recordings. They cannot establish product behavior.

Root execution, only on an authorized disposable machine with local immutable images and a **fresh synthetic control fixture**:

```sh
python3 /PUBLIC_CHECKOUT/sub2api-slot-lab/root-driver.py \
  --config /ROOT_OWNED/slot-root-config.json \
  --output /ROOT_OWNED/new-slot-run
```

Follow [RUNBOOK.md](RUNBOOK.md) and fill `root-config.example.json` and
`build-attestation.example.json` in a separately held private root directory.
Private files require exact mode 0600 and no symlink ancestors. Public patch and
producer manifest inputs can be 0644. Root must independently pin the reviewed
full merged source manifest, final merged production patch and actual image build
receipt to the same exact source fingerprint/component provenance. The driver
rejects historical images/binaries, empty or unreviewed components, missing maps,
and unknown receipt schemas. It compares the actual image ID/Config before
launch and the running native executable after launch. These checks use external
root trust; public file hashes cannot prove private compilation or execution.

Prepare a fresh transport-isolated-r4 synthetic fixture separately with full hash
attestation for snapshot.sql, engine.env and lab.json, matching PG18/Redis image
pins, and zero ALL accounts/API keys including deleted rows. The root driver
rechecks those counts on the actual restored fresh owned DB. This worker does
not read or copy private fixtures. Actual native W2 default regressions remain
pending the independent native W3 repair: the actual merged image is NOT READY,
E2E is NOT RUN, and the final reviewed merged patch hash is still unknown.

One new internal network and one new PostgreSQL 18 instance with tmpfs at **`/var/lib/postgresql`**, PGDATA `/var/lib/postgresql/18/docker`, one password-authenticated private Redis and one native engine are used. No host ports or external network attach exists. Root-owned Redis password lives in a mode-0600 file mounted read-only; the observer authenticates directly over the internal network, never via CLI arguments. The driver uses deterministic per-run names with a random unique run ID, ownership labels and an intention journal before each creation. The absolute 20-minute deadline includes setup/observation command overhead; operator stops 15 seconds early to reserve cleanup. All normal exits and SIGINT/SIGTERM attempt exact label-verified container/network teardown, with no global prune. SIGKILL/host loss cannot guarantee cleanup: use the retained journal to inspect exact owned identities and remove only resources whose ownership still matches. A cleanup error or deadline failure is a failed run, not a successful gate.

The matrix has 20 opt-in cycles for each `(Responses|Messages, account|user)` plus one default negative control per pair. Every cycle creates fresh numeric group/account/user/API-key IDs, uses one stable native API key for all its requests, and journals ambiguous native creates without retry. Account lane sets account concurrency 1/user concurrency 2; user lane sets user concurrency 1/account concurrency 2. Each opt-in cycle performs:

1. Hold first SSE after the provider has accepted a real request and flushed a semantic frame; the client must observe its valid >4 KiB text-delta acknowledgement. Require actual first user/account/API-key leases in Redis.
2. Start second request and require its actual target wait counter **1**, first members still present, and no second provider attempt. Account waiting must hold two user/API-key request leases and one account lease; user waiting holds one of each. Reject an unavailable account/no-queue response as an admission failure.
3. Disconnect second; within 1250 ms require both wait counters 0, only original first lease members still present, and still no second provider attempt.
4. Disconnect accepted first with **persisted account Extra** `native_api_key_cancel_on_disconnect: true`; within 1250 ms including control/Redis round trips require all three actual lease counts and both counters 0. The real provider observes an incomplete response close **and physical socket close**, no terminal, no manual release/reset and no safety timeout. These wire observations establish abortion of the provider response body; they do not instrument a Go `Body.Close` invocation. Lease ownership is established independently by actual Redis reads.
5. Healthy third must produce valid native SSE completion, exactly one provider dispatch/effect, then zero slots/waiters. Poll an additional 1250 ms for orphan effects or leases. After all cycles, read every owned key again and require exactly 168 accepted requests/effects, no rejection, no active provider streams.

The default negative controls omit the flag entirely, verify its absence through the trusted admin readback, cancel an accepted first request and repeatedly observe the provider stream remaining open through 1250 ms. Only explicit release lets the stream finish its normal drain. There is no default 1250 ms lease/body-release promise. A healthy third then proves recovery. They use two accepted requests each and no pending request. The complete matrix therefore has 168 accepted provider requests (160 opt-in + 8 default), 248 actual gateway requests, and 252 reserved unique request IDs, four of which are unused default pending IDs. The fail-closed mock records and rejects any unknown/preparation/probe/pending/duplicate dispatch before acceptance; any rejection fails the gate. This protects the accepted-request budget while exposing retries as failures.

The observer issues only AUTH and read-only MULTI/EXEC containing ZCARD/ZRANGE/PTTL on `concurrency:account:<id>`, `concurrency:user:<id>`, `concurrency:api_key:<id>`, and GET/PTTL on `wait:account:<id>`/`concurrency:wait:<id>`. It never scans, flushes or deletes Redis keys. API-key leases are stats-only in the supplied source; they are observed and checked, never treated as a concurrency admission cap. Lease/counter TTLs must exceed 5 s while occupied so expiry cannot manufacture a 1250 ms recovery pass. Source discovery hashes are in `source-inspection.json`; cached Ops counters, FD counts and writer state do not establish leases.

Evidence: `evidence/<run-id>.<protocol>.<lane>.<cycle>.json` contains numeric ownership, actual Redis members/counts/raw GET values/TTLs and start/completion timestamps for every observation, provider records, action times, native SSE summaries, and cleanup results. `final-zero.json` records all 420 final exact key checks; `final-provider.json` records all 168 provider dispatches/effects. `result.json` becomes PASS only after both final checks. `deployment.json`, `root-result.json` and `cleanup-journal.json` bind installation and teardown. Private bearer, native keys, provider sentinels and Redis password stay in `/private`, never in exported evidence. Keep the whole root output mode 0700 and share only reviewed evidence.
