Use Python 3, the exact supplied official source tree at pin `96f4c115c9749078f90cbf210a01d39baf3f53b6`, and the supplied standalone gofmt SHA256 `86dd91f69254432a37ca365f964720677040fd6f049a412c23e25f8b3812f342`. No sibling historical package, private runtime environment or stored connection string is required for these commands. Choose an output path outside the package that does not yet exist.

```sh
python3 -B /path/to/package/verify-artifacts.py --upstream /path/to/official-source --gofmt /path/to/standalone-gofmt
python3 -B /path/to/package/scan-package.py
python3 -B /path/to/package/prepare.py --upstream /path/to/official-source --gofmt /path/to/standalone-gofmt --output /path/to/new-prepared-source
python3 -B /path/to/package/verify-runtime-receipts.py --source /path/to/new-prepared-source
python3 -B /path/to/package/offline-checks.py --upstream /path/to/official-source --gofmt /path/to/standalone-gofmt
```

Preparation applies `fullsource.patch`, byte-exact canonical `labtests.patch`, and final `tests-overlay.patch` in that order. It rejects changed upstream bytes, unexpected upstream paths, patch hash/context/position mismatches, noncanonical or unsafe paths, existing outputs and unsupported source links. `--check` performs the same exact reconstruction entirely in memory. It checks all source stages and the complete executed backend ledger, then gofmt; it never invokes Go compilation. The runtime verifier can reconstruct in memory with `--upstream` and `--gofmt` instead of `--source`.

`old-tests-overlay.patch` is retained `e86f…` historical input, not the final overlay. `bulk-production.patch`, `bulk-regression.patch`, `bulk-unit-tests.patch`, `unit-fixture-adaptation.patch`, `w9-to-bulk.patch`, `w9-to-final.patch` and `w9-to-actual.patch` permit separately bound review of the composition. Apply neither the old overlay nor these component patches on top of the prepared final tree. The production full patch already includes the affected-ID repair and admin unused-import deletion.

The actual receipt checker defaults to this package's byte-exact supplied `evidence/`. `--evidence` accepts a relocated copy; it still requires the exact bound evidence hashes. This is verification of the supplied actual executions, not certification of arbitrary future runs. Fresh controller reruns require new observed process/source evidence and deliberate review of their bindings; do not relabel copied historical receipts or infer execution hashes/exits from counts. Inspect `actual-bindings.json`, `executed-source-hashes.json`, `source-manifest.json` and raw process receipts when independently reviewing provenance. The 144 producer projection and 171 reassembled raw records are both explicitly accounted for.

Worker checks use only Python and the supplied standalone gofmt. The controller may separately execute the real integration tests against its own isolated services, using the existing lab's documented environment interface. This package stores no DSN, credentials, keys or live authentication. Actual tests, service startup and migration deployment are outside this worker's authorization.

Keep the critical independent W7 review pending until its real decision arrives. No production GO: migration243 rejects populated history, live OAuth upgrade is NOT RUN, new effects prove the repository cache-observer boundary rather than actual Redis scheduler writes, and a separate actual Go binary checksum/observed complete RED source ledger are absent from supplied evidence. Preserve these limits in integration and review. No `git add`, commit or push belongs to this linked-worktree handoff.
