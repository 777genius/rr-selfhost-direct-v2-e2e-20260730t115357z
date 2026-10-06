W3 offline repair verification in this supplied worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-memory-profile/verify_offline.py
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-memory-profile/verify_handoff.py
```

The first command uses `.spike-inputs/original-inputs` in a disposable owned harness; it does not rewrite the input tree. It runs the original 16 Python and seven Node tests plus ten regression/security tests, raw numeric/source audits and unchanged reviewer probes. The legacy full analyzer fixture class remains NOT RUN if its raw W1 tree is absent. Red W2 and green W3 fixed-contract regressions are recorded separately from the unchanged reviewer's vulnerability assertions (which pass on vulnerable W2 and fail on repaired W3).

The second command applies the existing exact four-file native patch in memory, checks overlay equality and preservation, and exercises current W3 explicit-manifest authorization. It reads the isolated stream-memory package and writes only this profile package; its synthetic binary pin is not real build evidence.

Private migration now requires both existing output parent directories to be owned mode 0700, with no symlink ancestor or output, and two fresh distinct output names. It validates both payloads first, creates both files exclusively with mode 0600, and never replaces an existing output. Create the private parent through the controller's normal private-directory provisioning before migration. The sample command paths below are controller commands and were not executed by this worker.

All four compiler operations (version, GOROOT query, build and build-info) use the same sanitized local toolchain environment and pinned executable/caches. Ambient GOROOT and GOENV do not select the tree. Four stdlib pins are checked against the effective tree from that environment, then rechecked before compilation. GOMAXPROCS=2 is confined to toolchain subprocesses; runtime memory configuration stays fixed.

An explicit analyzer manifest must be byte-exact legacy or validated reviewed input. Absent/false/empty/invalid reviewed_source never authorizes an alternate source map. The input/receipt shape is documented in `reviewed-source.schema.json`; exact bytes and patch/binary bindings remain mandatory in Python. Old evidence must never be promoted to future source.

Prior controller-owned W2 config migration and preparation succeeded before review, using its private toolchain and exact staged collector. This is not Docker proof or current W3 proof. The remaining W2 instructions below are retained as controller context; use new W3 private config and receipt filenames and fresh run/output paths for subsequent execution.

The worker performs offline source/numeric/producer-contract verification only. The commands in the controller block below are instructions for the pinned isolated root machine; they were not run here. Integrate only `sub2api-memory-profile/` through the project controller lifecycle. No worker Git writes are needed.

Run the current offline checks from the project root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-memory-profile/prepare.py --verify-only --out sub2api-memory-profile/evidence/source-audit.json
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-memory-profile/audit_actual.py --out sub2api-memory-profile/evidence/actual-audit.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s sub2api-memory-profile -p 'test_*.py' -v
node --test sub2api-memory-profile/offline.test.mjs
```

`SOURCE_ONLY` verifies the current frozen native/profiling source and available operator bytes. It is explicit about the missing collector/toolchain runtime inputs. The skipped legacy analyzer fixture test requires the complete original W1 `actual-execution` fixture tree. The actual numeric audit uses supplied comparison/runtime/telemetry files; it cannot substitute for missing case/DONE/profile/build/cleanup receipts. W1 test outputs are archived in `evidence/w1-original/`.

Run from this W2 worktree with its supplied `.spike-inputs` bundle (input-manifest SHA-256 `cb701348c9b6115977e824bb37659cbcd5c782e9678f9e95004c2b13b26a9b7a`). The older W1 input tree has a different layout and cannot replace that bundle. For the root rerun, retain the existing synthetic `transport-isolated-r4` snapshot, private environment, lab config, fixture attestation and pinned service image digests from successful run 09. Do not copy raw private inputs into this repository. The driver still requires zero nondeleted upstream accounts, standard billing, exact fixture hashes, an internal owned network, no host ports and one setup/engine/tenant throughout each finite lane. An expired private synthetic bearer stops admission.

Use the root operator's existing actual Go1.27.1 executable/hash and prepopulated module cache. The original reviewed W1 stdlib freeze must supply `runtime/mprof.go`, `runtime/mstats.go`, `runtime/pprof/pprof.go` and `runtime/pprof/protomem.go`. Do not generate expected hashes from an unreviewed replacement toolchain. The producer compares these expected hashes to the actual Go installation at preflight. The compilation cache must be the operator-verified Go1.27.1 cache from the successful root wrapper, configured as `compilation_cache`; compilation alone gets `GOMAXPROCS=2`.

Recover the exact collector from run 09's retained `stage/code/sub2api-transport-r4/collector.py`, or W1's original actual collector. The staged hash must be `a5165669fee17b9da362aa7a31fdac690e1c29bd785a9a51955155648f3997a3`; the pre-overlay original hash is `99964d6e4581b25b582f27f2ff8ce2fe54866dd2448dd9f452af39860d13a5de`. The older checked-in collector has different bytes and is rejected. Keep the default W1 source manifest fixed.

Controller commands (substitute actual owned paths; use fresh outputs after 12):

```sh
python3 sub2api-memory-profile/operator_config.py \
  --old-config /OWNED/private/root-config-w1.json \
  --out /OWNED/private/root-config-w2.json \
  --receipt /OWNED/private/reviewed-toolchain-w2.json \
  --stdlib-freeze /OWNED/memory-profile-w1/.spike-inputs/go-stdlib \
  --compilation-cache /OWNED/fork-build/gocache \
  --collector-source /OWNED/profile-responses-fixed-00000009/stage/code/sub2api-transport-r4/collector.py
python3 sub2api-memory-profile/prepare.py --collector-source /OWNED/profile-responses-fixed-00000009/stage/code/sub2api-transport-r4/collector.py --stage /OWNED/source-check-w2
python3 sub2api-memory-profile/root-driver.py --config /OWNED/private/root-config-w2.json --out /OWNED/profile-responses-fixed-00000013 --protocol responses --lane fixed
python3 sub2api-memory-profile/root-driver.py --config /OWNED/private/root-config-w2.json --out /OWNED/profile-responses-control-00000014 --protocol responses --lane control --match /OWNED/profile-responses-fixed-00000013
python3 sub2api-memory-profile/analyze.py /OWNED/profile-responses-fixed-00000013 --control /OWNED/profile-responses-control-00000014 --out /OWNED/profile-responses-comparison-w2.json
python3 sub2api-memory-profile/root-driver.py --config /OWNED/private/root-config-w2.json --out /OWNED/profile-messages-fixed-00000015 --protocol messages --lane fixed
python3 sub2api-memory-profile/root-driver.py --config /OWNED/private/root-config-w2.json --out /OWNED/profile-messages-control-00000016 --protocol messages --lane control --match /OWNED/profile-messages-fixed-00000015
python3 sub2api-memory-profile/analyze.py /OWNED/profile-messages-fixed-00000015 --control /OWNED/profile-messages-control-00000016 --out /OWNED/profile-messages-comparison-w2.json
```

The migration tool creates both files exclusively mode 0600 in guarded private parents, emits no configuration values and refuses existing outputs. It records expected stdlib hashes from the reviewed freeze. `root-config.example.json` documents all required public shape fields; placeholders fail validation. The canonical base tag remains a fixture pin; removing its last tag could delete the preexisting bare-ID image before the control. The reusable driver no longer needs `actual-root-wrapper.py`: PG18 uses parent-directory tmpfs; Redis shares only the synthetic private password via a readonly file; Docker builds from a canonical root local tag verified against the fixed base ID; COPY installs an executable; the build uses the reviewed cache. Each run records its own binary, derived image, verified base-tag receipt and Dockerfile hashes. Controls require the same binary/source, while different derived-image hashes are allowed and recorded.

The fixed lane remains N5×10, 50 finite 8MiB streams / 400MiB per protocol, with full five-second RSS tails and separate preparation effects. Matched controls perform no scenario work and reproduce workload checkpoint times. Optional staircase remains N1×10, N5×10, N20×5: 160 requests / 1,280MiB per protocol, invoked with `--lane staircase`; its control references that completed lane. Measurement is bounded to 600 seconds, a burst needs 110 seconds remaining reserve, cleanup has a separate 20-second reserve. Stop on ambiguous identity/effects, incomplete frames/volume/terminal evidence, active streams, collector/safety/budget failures. No restart, retry, forced GC, peak reset or threshold adjustment fills gaps. Failed/partial cleanup prevents COMPLETE.

Preserve attempts 01–08 as pre-case failures. Do not rerun into old outputs. Retain full run/source/input/build/base-tag receipts, binary, setup/burst/cleanup receipts, raw RSS/READY/DONE, runtime NDJSON, checkpoint acknowledgements and binary profiles. Export only body-free evidence. Private Redis config and private fixtures stay in the operator's private directory; no password value is passed in Docker arguments or public receipts. Root must verify the repaired W3 producer afresh; successful historical wrapper receipts remain historical evidence.

To prepare reviewed future stream/cancel source, supply a separate exact JSON input:

```json
{
  "schema": "rrsub2profile-reviewed-v1",
  "base_manifest_sha256": "8a8103f73486912aa86f972fd2914bbff295d91126483447930da15ca227f704",
  "base_image": "sha256:6df1cc33771f1bc94028cc18440a13e7d31a3513331bbb8d7d686584d19b79e2",
  "binary_sha256": "REVIEWED_ACTUAL_MERGED_BINARY_SHA256",
  "patches": [
    {
      "path": "/OWNED/reviewed/stream.patch",
      "sha256": "REVIEWED_PATCH_SHA256",
      "files": {
        "backend/internal/service/EXACT_CHANGED_FILE.go": {
          "before_sha256": "EXACT_BASE_FILE_SHA256",
          "after_sha256": "EXACT_RESULT_FILE_SHA256"
        }
      }
    }
  ]
}
```

One or two patches are accepted, in explicit order; `before_sha256: null` denotes an explicitly listed new native Go file. Existing files require exact before hashes; all results require exact after hashes. Only adding/modifying backend Go source is supported. The profiling file, dependency/toolchain files, historical manifest fields, operator bytes and base image cannot change. Hash-pin this reviewed JSON in private root config as `reviewed_source` and `reviewed_source_sha256`; omit both for current legacy defaults. Preparation can be reviewed offline with `--reviewed-source /OWNED/reviewed/manifest.json --collector-source ... --stage /OWNED/reviewed-stage`. Root build must match the reviewed merged binary hash.

For a reviewed future run, analyze with `--expected-manifest /OWNED/reviewed-stage/source-manifest.json` and a fresh matched control. Default analyzer acceptance stays W1 exact. Explicit future acceptance proves configured source identity, not behavioral correctness. Run native/HTTP/WS regression and the required stream/cancel runtime/ownership gates separately. This package does not implement the separate 20-cycle pending-slot cancellation lane. Never promote existing W1 receipts to a new source or a future cancellation claim.

All numeric interpretation stays `DIAGNOSTIC_ONLY`: pprof is sampled/weighted and can lag two natural GC cycles; ReadMemStats is a current allocator snapshot and is not a reachable-root measurement. No postburst checkpoint in the supplied runs is cycle-eligible. The finite window cannot establish indefinite leak/plateau or RSS repair. Keep the 20 actual historical RSS FAILs negative. Inspect retained profile stacks with the matching toolchain offline only; allocation sites and goroutine totals do not establish orphan reader/slot ownership. See `SEMANTICS.md` and `REPORT.md`.
