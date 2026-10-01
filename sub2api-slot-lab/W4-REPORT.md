# W4 native logging preflight repair

The full frozen W3 candidate is restored at the top level. Only two producer values change in root-driver.py: log.output_to_stdout becomes true and LOG_OUTPUT_TO_STDOUT becomes true. File output stays false; Docker log-driver none stays intact. All historical W2/W3 reports, failures, ledgers, launch evidence and candidate files are preserved byte-for-byte except those two driver values.

The supplied actual W3 diagnostic4 exited before inference because both logging outputs were false (zero provider effects, cleanup true). The supplied pinned native validator rejects `!ToStdout && !ToFile` at native-config-validator.go:2805. The focused offline contract executes prepare with inert synthetic inputs and captures emitted config/environment, independently applies that predicate to both surfaces, and verifies private mode 0600. Both old surfaces are RED; repaired surfaces are GREEN. This checks the predicate without claiming Go execution or complete native config validation.

Run `PYTHONDONTWRITEBYTECODE=1 python3 sub2api-slot-lab/w4-verify.py`. All 34 original Node tests, 14 original Python tests and unchanged W3 launch regression pass, plus one focused W4 contract (16 Python). Frozen W2/image test paths are relocated in memory because the inputs are nested under original-inputs in this slot; test files remain unchanged. W4-LEDGER.json records integrity, results and hashes. The full candidate remains below 60 files.

Explicit native entrypoint, root 0:0, cap-drop ALL, no-new-privileges, internal network, exact image/source custody, Redis gates, native SSE and default controls are unchanged. The original 84-row plan and 1250ms bound are unchanged. Stdout is accepted by native logging while Docker's none driver prevents persistent container logs; file logging remains disabled.

Actual 84-row root verification remains PENDING for the controller. This worker ran no Go, Docker, root entrypoint, network, secret access, Git writes, or subagents. Offline success does not prove inference or cancellation runtime success. Historical ROOT_RESULT.json remains historical failure evidence.
