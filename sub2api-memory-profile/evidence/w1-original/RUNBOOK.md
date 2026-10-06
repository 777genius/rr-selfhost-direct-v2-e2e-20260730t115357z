This is an executable disposable source harness. The worker has **not run root, Go compilation, Docker, network, providers, or authentication**. Execute runtime commands only as the project controller on the pinned isolated root machine. All outputs are new test-owned directories. Never apply the instrumentation to a production checkout or call a public profiling port.

First supply the existing synthetic `transport-isolated-r4` private fixture as a frozen clone: `snapshot.sql`, the matching `engine.env`, and private `lab.json`. Use the isolated synthetic database, never the live-provider database. The dump must have zero nondeleted upstream accounts; the actual setup creates its own exclusive account/group/user/key once per lane. Redis starts as a fresh owned private clone with persistence disabled, using the same pinned Redis image. This avoids attaching any shared container or network. The original driver reused shared services and restarted the engine per case; this driver does neither. A snapshot/export is an operator prerequisite, not an action performed by this worker.

Place `profile-fixture.json` beside those files, with **actual** SHA-256 hashes, not placeholders:

```json
{
  "source": "transport-isolated-r4",
  "status": "PASS",
  "real_provider_keys_copied": false,
  "images": {"postgres": "ACTUAL_NAME@sha256:ACTUAL_DIGEST", "redis": "ACTUAL_NAME@sha256:ACTUAL_DIGEST"},
  "hashes": {"snapshot.sql": "ACTUAL_HASH", "engine.env": "ACTUAL_HASH", "lab.json": "ACTUAL_HASH"}
}
```

`lab.json` must retain the real **synthetic** private admin bearer and two synthetic sentinel labels from that fixture; an expired bearer causes a stop. Keep the fixture and configuration root-owned mode 0700/0600, do not publish their contents, and do not copy any real provider credentials. The driver restores the dump into a new owned Postgres container and checks zero active accounts before admitting requests. It reuses the actual native setup/load/cleanup functions. Account **definitions and IDs** remain the same between bursts; balances, usage, billing records and caches can change. Do not describe all account state as unchanged.

Copy `root-config.example.json` to a private operator location and fill actual immutable Postgres/Redis image references, fixture attestation hash, local Go 1.27.1 executable/hash and a populated Go module cache. The driver does not pull images or download modules. It checks machine `d856d40da5ad4e23b4f67773e5942842`, amd64, at least 3GiB available RAM and 5GiB available disk, all supplied input hashes, exact combined native/probe source, and matching build toolchain stdlib. Standard billing remains enabled. Memory environment settings retain the fixture/base image values and are compared privately without logging them. Only profile directory and logging sink settings are overlaid: file logging is disabled; stdout is discarded by Docker's `none` log driver. No body/environment logs are collected.

Start with the fixed N5 vertical slice and its time-matched control, separately for each protocol. Example controller commands (NOT RUN by this worker):

```sh
python3 sub2api-memory-profile/root-driver.py --config /OWNED/private/root-config.json --out /OWNED/profile-responses-fixed-00000001 --protocol responses --lane fixed
python3 sub2api-memory-profile/root-driver.py --config /OWNED/private/root-config.json --out /OWNED/profile-responses-control-00000002 --protocol responses --lane control --match /OWNED/profile-responses-fixed-00000001
python3 sub2api-memory-profile/analyze.py /OWNED/profile-responses-fixed-00000001 --control /OWNED/profile-responses-control-00000002 --out /OWNED/profile-responses-comparison.json
```

Use matching distinct output directories for Messages. Each fixed lane is ten N5 bursts: 50 scenario requests, 400MiB exact wire volume, five-second collected idle tail after **each** burst, one engine and one owned tenant throughout. Control has the same startup/setup/healthy preparation but **zero scenario streams**. It reproduces the measured checkpoint elapsed times from the completed workload lane; it is not a guessed fixed-duration sleep. Setup effects are recorded separately from scenario effects.

The broad schedule is also implemented, without requiring any production patch:

```sh
python3 sub2api-memory-profile/root-driver.py --config /OWNED/private/root-config.json --out /OWNED/profile-responses-staircase-00000003 --protocol responses --lane staircase
```

Run separately for Messages and create a matched control referencing each completed staircase lane. The exact order is N1×10, N5×10, N20×5 at 8MiB, **160 scenario requests / 1,280MiB per protocol**. Each lane has a 600-second measurement supervisor including engine startup/setup. A new burst requires 110 seconds of remaining reserve for its bounded client/collector/profile work. Cleanup gets a separate bounded 20-second reserve. The instrumentation has an independent 650-second limit. Admission stops on missing identity, ambiguous effects, incomplete volume/frame/terminal evidence, active mock streams, collector failure, safety exceedance or budget expiry. No restart/retry fills a missing burst. PARTIAL runs and cleanup failures remain partial and are rejected by the analyzer.

The driver builds with `-tags=rrsub2profile -trimpath -buildvcs=false`, then builds a **new** derived image offline from the historical pinned base. It records actual new binary/image hashes and verifies the running `/proc/PID/exe` hash. All 3,323 source-after hashes and all operator-after hashes are checked. The historical image and binary are explicitly distinct. Startup/health execs finish before collection. Each original kernel collector retains sole-PID/cgroup/executable identity checks, whole-snapshot FD retries, unchanged 250ms timing rules, within-five-second return endpoint and full-tail DONE. The small collector overlay only accepts unique burst ID suffixes. Profiles are written after DONE and before the next collector, without an HTTP profiler.

Each individual stream has an admitted `.rNN` ID, a body-free downstream completion record and one independently numbered mock attempt/effect. The analyzer rejects missing/duplicate IDs, incomplete or oversized frames, wrong exact volume, multiple effects, nonfinite or coerced numeric fields, checkpoint reuse, PID/cgroup/source/binary changes, cycle-counter forgery, missing profile kinds, partial JSONL, failed cleanup or shortened tails. It independently replays the original RSS adapter. A recorded RSS return FAIL stays FAIL. That failure alone may continue a bounded diagnostic lane; a sampled cap/delta/cgroup watchdog failure stops it. This distinction changes diagnostic admission, never the reliability verdict.

Interpret all checkpoints and postwarmup slopes (first two bursts excluded explicitly), including cumulative allocations, natural-cycle allocator observations, sampled weighted heap profiles, heap inuse/idle/released, RSS and sockets. Fixed N5 separates completed burst count from maximum concurrency; compare against the matched no-work control to examine startup/background drift. A plateau over this finite window is not proof of indefinite boundedness. Missing later natural cycles produce INCONCLUSIVE attribution. Even with cycles, identifying retained roots requires stack-owner review using the retained compiled binary and the matching Go tool's **offline** pprof commands, for example `go tool pprof -top -sample_index=inuse_space /OWNED/run/build/profile-server /OWNED/run/profiles/checkpoint-010-heap.pb.gz`. This command reads an existing file and does not collect or request GC.

Current instrumentation does **not** count active handlers/readers, upstream body owners, slots/waiters, reservation refs, billing queued/running tasks or idle pool owners. Those fields remain unavailable; mock active=0 and sockets do not prove their release. Goroutine stacks can guide attribution but do not fabricate orphan counts. The separate 20-cycle pending-slot/cancel lane from the frozen plan is **not implemented** here; no slot-cancellation or drain-lifetime claim is made. Existing native reasoning/reference fields and conversions are unchanged. Actual Go native/HTTP/WS regressions and the instrumented runtime run remain controller work, and must not be marked green from these Python/Node tests.

Allowed offline verification commands, already run by the worker:

```sh
python3 sub2api-memory-profile/prepare.py --record
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sub2api-memory-profile -p 'test_*.py' -v
node --test sub2api-memory-profile/offline.test.mjs
.spike-inputs/gofmt -l sub2api-memory-profile/overlay/backend/cmd/server/rr_sub2_profile.go
```

Retain `run.json`, staged source/operator manifest, build receipt, setup and cleanup receipts, all raw RSS/DONE files and all runtime/profile checkpoints. Keep private configuration/journals out of public evidence. The project controller applies/commits/pushes through its integration lifecycle; this worker leaves the new directory intact and stops.
