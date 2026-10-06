The supplied transport-r3 JOB artifact retained the inherited `sub2api-transport-r2/` directory name. Its exact copies and the original transport-review-r4 REQUESTCHANGES are under `historical-input/`; their claims are preserved as historical. New active integration paths use r4.

Use the patch matching the exact checkout; do not apply both or stack old telemetry proposals. Input/result hashes are in `input-hashes.json` and `changed-loc.json`. Keep all original execution/receipts.

Local verification from workspace root (no real engine):

```sh
python3 sub2api-transport-r4/verify-overlay.py
node --test sub2api-transport-r4/adapter.test.mjs sub2api-transport-r4/pacing.test.mjs sub2api-transport-r4/mock-behavior.test.mjs sub2api-transport-r4/independent.test.mjs sub2api-transport-r4/load.test.mjs
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sub2api-transport-r4 -p '*_test.py' -v
python3 sub2api-transport-r4/audit.py
```

`client.test.mjs` is preserved for coordinator socket checks; it was NOT RUN here because this lane is offline. The independent test reproductions replace only I/O and execute the actual `load()` function. The other HTTP checks exercise actual HTTP parsers over in-memory Duplex streams and do not prove kernel TCP or engine gates. The slow32/64MiB check takes about48sec; the entire mock check about61sec.

Coordinator integration into a disposable copy of canonical:

```sh
patch --dry-run --batch --fuzz=0 -p1 < sub2api-transport-r4/lab-overlay.patch
patch --batch --fuzz=0 -p1 < sub2api-transport-r4/lab-overlay.patch
node sub2api-regression-lab/run.mjs --plan
```

For the exact code frozen under `.spike-inputs/prior-code/sub2api-regression-lab`, use `frozen-root-overlay.patch` instead of `lab-overlay.patch`, from the root containing that copied `sub2api-regression-lab`. Both produce the same six output files. The mount template carries `/lab/sub2api-transport-r4/adapter.mjs`; ensure the actual operator deployment also carries that file. The collector stays outside the operator container, in the coordinator's permitted observation namespace. No private configuration belongs in its spec or public outputs.

For EACH memory/soak cell, the coordinator independently inspects a new dedicated synthetic Go container and its fresh, sole-occupant cgroup with limit805306368bytes. Never reuse its lifetime. Bind actual immutable source/image/binary pins, actual64hex container ID, instance and actual host PID to the private deployment/config; `verifyDeployment` compares container IDs as well as the original pins. Retain lifecycle inspection separately, including creation-observation uncertainty. Readiness alone is not a live-process/freshness proof.

The public collector spec has:

- `batch_id`: one of the original18memory or2soak IDs; `instance`; actual `engine_pid`.
- `pid_start_ticks`: proc stat field22; `exe_device`, `exe_inode` from actual exe stat.
- `cgroup_path`: dedicated absolute path below cgroup2 root; `cgroup_device`, `cgroup_inode`; actual `container_id`.
- `fresh_container_inspected: true`: independent inspection includes the fresh dedicated cgroup lifetime; not inference from a peak counter.
- `container_created_ms`, `pid_created_ms`: ordered creation observations in Linux CLOCK_MONOTONIC milliseconds, preserving uncertainty in separate inspection evidence. Never convert wall clock to invented kernel birth times.
- Absolute `start_path` and `end_path`: this cell's new canonical evidence boundary files; no reused boundary/output directories.

Run after inspection, using existing owned output directory:

```sh
python3 sub2api-transport-r4/collector.py --spec /PUBLIC_OWNED/spec.json --output /PUBLIC_OWNED/telemetry
```

Confirm the actual collector handle remains live and the new `<case>.ready.json` matches inspection and contains the first sample. Refresh the private deployment pin for each new container. Once ready, execute exactly one original canonical command in the isolated operator:

```sh
node sub2api-regression-lab/run.mjs --case memory-messages-64-20
```

Use each original case ID, without retries of ambiguous cases. The runner's start/end boundaries use the same CLOCK_MONOTONIC domain as the collector. Its end acknowledges the completed finite load/effect/upstream-close checks. After the full5sec tail, collector flushes/fsyncs its NDJSON then exclusively writes `<case>.done.json`. A valid DONE matches actual identity, batch and end time, final sample timestamp and full-tail duration. Retain its actual exit status. Missing metrics, missing/unsupported smaps, bad identities/limit, >250ms gaps, errors or missing acknowledgment remain NOT RUN; never substitute zero. Raw HWM decline does not invalidate observations. A known threshold exceedance remains empirical FAIL.

Inspect `functional_status`, `memory_envelope.empirical_qualified_status`, `memory_envelope.physical_interval_rss_status`, aggregate `acceptance_status`, effects and cleanup independently. Empirical PASS can coexist with physical NOTPROVEN and aggregate NOT RUN. Historical11FAIL9NOTRUN/686attempts remain historical. Cancellation requirements and their intentional-drain FAIL remain unchanged.

Collect/retain all admitted failure tails and cleanup receipts; tear down only that owned disposable cell. Full real engine gating and physical interval proof are coordinator work, not locally executed by this handoff. Never wait for external gates to finish this lane.

Standalone layout is already assembled under `runtime/`, using the full exact frozen support and six final overlay files. Offline plan command: `node sub2api-transport-r4/runtime/sub2api-regression-lab/run.mjs --plan`. Verify provenance with `python3 sub2api-transport-r4/verify-provenance.py`. Each patch was applied in an owned disposable reconstruction with zero fuzz and zero offset, and both reconstructed load functions passed the behavioral numeric/exact-volume tests. `prepare-standalone.py` only creates a missing runtime; it refuses overwrite.

Memory functional acceptance requires finite nonnegative scalar counters, exact safe-integer upstream AND downstream body counts of 8/32/64MiB, and each downstream largest frame in [1.9MiB,2MiB). Text remains >4096 bytes, tool ID remains required, and comments/effects/terminal/close gates remain. Invalid downstream numeric evidence yields null aggregate fields and FAIL, without coercion. Counter sums beyond the safe-integer range also fail. Both source framing and measured downstream framing remain independent. Protocol conversion that alters wire volume or removes the qualifying downstream frame yields actual FAIL; no semantic byte normalization is implemented or independently proven.

The two repacked patches are byte-identical because the provided canonical/frozen six-file originals match. Use the provided hashes, not the original candidate’s legacy frozen-base hashes. The older prior manifest mismatch (two source files, eight absent telemetry-analysis references) is explicitly listed in `evidence/provenance.json`; no missing historical driver was fabricated.
