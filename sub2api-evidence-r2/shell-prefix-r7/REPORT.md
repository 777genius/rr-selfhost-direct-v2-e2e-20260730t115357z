Fixed supported shell-prefix admission for numeric evidence, separate BUSINESS_RULES.md reads, and shared gateway wallet.mjs reads. Root's original canary **36879127384** (reported source **c194**) remains **FAILED at evidence_tool_numeric**. No live rerun or success claim is made. Saved entry bytes are the RED baseline; the linked Git directory is unavailable, so its commit identity could not be independently resolved.

The supplied sanitized actual-command projection records argv **/usr/bin/bash -lc**, completed status, numeric-zero exit, and standalone negative example **1000 / -250 / 1250**, matching the supplied final finding projection. The old /bin-only regex rejects a command string derived from those argv; it also rejects both separate reads. This is a concrete reproduced admission defect consistent with the reported failure phase. The projection is argv and metadata, **not captured CLI stdout**. The regression derives a CLI-style quoted command string and executes only the projected Node expression locally against the real immutable fixture. Locally observed stdout is exactly the standalone numeric JSON plus newline, **60 bytes**. Neither a captured CLI command string nor a recovered private transcript is asserted. Both supplied projections are retained byte-for-byte in this directory.

All three read/numeric contracts now allow only **/bin/bash, /bin/sh, /bin/zsh, /usr/bin/bash, /usr/bin/sh, /usr/bin/zsh**, with exactly **-c or -lc** and matching surrounding quotes. Exact direct cat wallet.mjs and cat BUSINESS_RULES.md remain accepted. Direct Node eval remains accepted with **-e** and optional **--input-type=module**. Numeric admission requires one quoted eval argument mentioning wallet.mjs and withdraw; arbitrary executable paths, other flags, positional script paths, extra arguments, shell compounds/redirections, newline-separated commands, and unescaped shell substitutions fail. Wallet-read quotes now must match; the previous /bin wallet regex accepted mismatched quotes. No shell executable or arbitrary projected shell command is launched by these tests.

Complete-object, array-membership and strict JSONL finite/exact numeric parsing are **byte-identical** to entry. Every existing test in the three changed test files is retained with zero removed lines; six new tests add positive matrices for both prefixes, all three shells, both supported flags and quotes, plus malicious path/flag/command, nonzero/incomplete, mismatched numeric and stdout-prefix denials. The actual argv regression reaches the real top-level caller with substituted agent/network/seal I/O, real local Node output and a separate real independent Node reproduction, observed exit **0**. It requires wallet/rules reads and successful terminal, and denies bad output/tool states, compound reads, missing terminal and independent mismatch. Existing independent-mismatch tests observe actual Node exit **1**, no receipt. These are offline contract results, not genuine CLI/provider/Actions receipts.

The genuine CLI final-file/terminal handling, independent reproduction expression, financial finding gates, HIGH reasoning/granted model, sealing/import paths, OIDC/grant binding and transcript custody source remain unchanged. Preserved production/fixture hashes are independently compared against entry in change-metrics.json. No root operation, Docker, Go, network/provider call, provider key or auth access, Git write or sub-agent operation occurred. The single read-only Git status attempt failed to resolve the linked gitdir. Controller integration must apply the intact source diff and rebuild/reseal both changed evidence modules.

Identical RED/GREEN command on **Node v24.21.0**:

node --test --test-reporter=tap sub2api-spike/evidence.test.mjs gateway-spike/evidence.test.mjs sub2api-spike/run-client.test.mjs sub2api-evidence-r2/client-contract.test.mjs

- RED, saved entry production bytes + final tests: **42 passed / 5 failed**, exit **1**, red.tap. Baseline production is restored to fixed bytes in finally.
- GREEN, fixed production + identical final tests: **47 passed / 0 failed**, exit **0**, green.tap.
- Additional preserved OIDC/grant/isolation/receipt gates: **10 passed / 0 failed**, exit **0**, preserved-gates.tap. Exact command is in preserved-gates-result.json.
- Syntax checks for all five changed source/test files: exit **0**, syntax.json.

The existing full **129** coordinator tests are retained. The full workflow source-gate command is unchanged and was **NOT RUN** here because broker/customer/server tests open loopback sockets and network is prohibited. No full-suite green or live canary green is claimed. Historical evidence-r2 reports, logs, fixtures and metrics remain untouched.

Incremental source/test LOC relative to saved entry bytes (report/artifacts excluded):

| File | Added / removed | Final SHA-256 |
| --- | --- | --- |
| sub2api-spike/evidence.mjs | +5 / -3 | 64e3595a2f71c972e035b55215c1db0f156fc9d61e81ad11d119910864fa0833 |
| sub2api-spike/evidence.test.mjs | +42 / -0 | c10cc3252fb4bec0673d81a477aaac7cf12f765ac4ba81783b76b4f05cfacef4 |
| gateway-spike/evidence.mjs | +1 / -1 | 91970dd758b12be92181dc1ed6a15c5776048af4da5dd78b7d3fdf4396960a72 |
| gateway-spike/evidence.test.mjs | +10 / -0 | 831db6a72319fcf8d57dac4ff47cc50820c0bb4ea505449aab9cc6ca5de31f98 |
| sub2api-evidence-r2/client-contract.test.mjs | +24 / -0 | af8da54be31e31e24f1486fd2482aa01f7d0e8aa787090bd27986adec5b70b93 |

Production: **+6 / -4**. Tests: **+76 / -0**. implementation.patch contains exact diffs. change-metrics.json records baseline/final source hashes and artifact hashes.

Delivery is edit/test/handoff only. Remaining verification limits: no captured original CLI stdout, no live rerun, no full network-using source gate, and no installed seal/container validation. The original failed run stays failed. Delivered and stopped.
