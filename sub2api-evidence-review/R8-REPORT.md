APPROVE — independent frozen R8 review complete. The two R7 quote-breakout defects are repaired; no new blocking classifier counterexample was found. Approval covers these frozen offline source bytes. Root must rebuild/reseal the installed image and run three new paid canaries after approval. Those canaries are NOT RUN. STOP.

Both exact known strings were tested through codexNumericEvidence only, never through a shell:

~~~text
/usr/bin/bash -lc "node -e 'withdraw wallet.mjs "; echo injected; "'"
/usr/bin/bash -lc 'node -e "withdraw wallet.mjs '; echo injected; '"'
~~~

Identical assertions expecting false against independently reconstructed, hash-confirmed R7 evidence.mjs: **0 PASS / 2 FAIL**, exit 1, actual true in both cases. Against frozen R8: **2 PASS / 0 FAIL**, exit 0. The R7 module was reconstructed by reversing the supplied patch only in scratch; its hash exactly equals the R7 independent REQUEST CHANGES source hash. The imported gateway validator is unchanged. Only the regression import location was relocated to each scratch tree.

At sub2api-spike/evidence.mjs:9–32, literalWord structurally consumes one bounded literal word. It tracks single/double quotes, decodes POSIX backslashes, permits adjacent quoted/unquoted safe segments and escaped literal quotes, and rejects unclosed quotes, dangling escapes, NUL/internal CR, active dollar/backtick expansion, whitespace separating arguments, compounds, redirects, comments and glob syntax. The backslash-before-nonspecial-character rule inside double quotes is preserved. At lines 41–47, only exact /bin or /usr/bin bash/sh/zsh with -c or -lc and one literal argument can unwrap; the inner command must be node, optional --input-type=module, -e, and one literal JS word. Unsupported paths, flags, extra argv and outer compounds fail closed. JavaScript semicolons inside that word remain valid. This is a bounded classifier, not a generic shell or JavaScript parser; wallet/withdraw are token checks, while real independent wallet execution and the financial finding contract remain separate proof gates.

Fresh Node v24.21.0 offline verification used copies of frozen sources, unchanged test imports/assertions, TMPDIR in owned scratch, and CONSUMER_WORKFLOW_SOURCE selecting the authoritative workspace workflow:

- Existing numeric/financial/caller contract suites: **52 PASS / 0 FAIL / 0 SKIP**, exit 0.
- Preserved OIDC/grant/isolation/receipt suites: **10 PASS / 0 FAIL / 0 SKIP**, exit 0.
- Additional independent classifier adversaries: **3 PASS / 0 FAIL**, exit 0. They exercise both-layer compounds/expansions, extra argv, backslash parity 0–6 before dollar expansion, adjacent literal segments, escaped semicolon/quote, malformed delimiters, line continuation and the 65,536-character word bound. No input shell command was executed.
- Syntax checks for both evidence modules/tests, production caller and caller contract: all six exit 0.

Exact contract command, from scratch/green:

```sh
node --test --test-reporter=tap sub2api-spike/evidence.test.mjs gateway-spike/evidence.test.mjs sub2api-spike/run-client.test.mjs sub2api-evidence-r2/client-contract.test.mjs
```

Preserved command substitutes sub2api-spike/oidc.test.mjs, granted-run.test.mjs, runner-isolation.test.mjs and receipts.test.mjs. Separate classifier commands select breakout.test.mjs in scratch/r7 and scratch/green, and independent.test.mjs in scratch/green. Agent/network/privilege/seal I/O is substituted; local wallet execution and caller independent reproduction use real Node subprocesses. Green projected-argv reproduction checks exact 60-byte stdout and independent exit 0; deliberate incorrect final balance checks real independent exit 1 and no receipt. Selector coverage verifies a rejecting transitive validator from the selected source, after real reproduction.

The entire numeric-output parsing block is independently byte-identical to R7. Whole-output complete finite object, immediate root-array member, and strict JSONL after whole-document SyntaxError remain supported. JSONL requires at least two nonblank complete finite objects and consumes every nonblank line; exact three-field matching cannot be assembled across rows. Prose, malformed lines, nested candidates, string numbers, overflow/nonfinite fields and mismatches remain denied. Existing root-array behavior permits irrelevant other members; it does not recursively extract examples. Numeric exit must be number 0, item/status truly completed. Separate exact wallet/rules reads, actual independent immutable wallet execution, negative financial finding, final-message file and successful terminal remain required. Failed terminal events remain disqualifying through the shared validator.

All R7 test names remain in order. Numeric assertions increase 50→58 with 16→21 tests; caller assertions remain 63 and 16 tests. Gateway source/test bytes are unchanged from R7. Six changed test lines correct invalid synthetic shell quoting; they do not remove assertions or relax expected denials. Production caller, grant binder, runner isolation, OIDC, receipts and immutable wallet/rules match authoritative workspace entry hashes. This preserves the valuable original 129/R7 assertions within the tested and supplied full-gate evidence; the entire socket-using gate was not independently rerun here.

Supplied root-node-gate.json reports actual Node24 consumer/server/numeric gate **140 PASS / 0 FAIL / 0 SKIP**, exit 0, zero provider requests, source base 413b450769744f95611e630a24a77d12f3491c6c. All six recorded source hashes independently match frozen candidate bytes, including the shared gateway module/test. Gate SHA-256: 40576e6ace69beebdf9036b14d4ab49cc83e5b8c7e1f12cceffb5cfa1f73eff3. This is supplied root evidence, not a root operation or independent full-gate rerun. Its summary lacks a complete per-test transcript and hashes for every file in that broad command; scope/provenance limits remain explicit.

Historical **36879127384 remains FAILED at evidence_tool_numeric**, workflow c194829638fc77fc4a75628412ef7cce5b98e8e7. The actual-agent projection reports wrapped tool outputs (negative result 163 bytes); the session-derived argv projection reports standalone numeric stdout (60 bytes). These are different projections. The caller regression safely renders the latter argv with escaped single quotes, runs its Node expression directly, and supplies synthetic completed/read/terminal events. This is an offline compatibility fallback, not original captured CLI stdout or proof of the original CLI event sequence. The source caller is unchanged and still requires native completed command events and exact stdout. No fragment scanning, promotion of projections into live receipts, or historical success is justified. Missing original transcript remains a diagnosis limit.

Heredocs, including quoted literal delimiters, are explicitly unsupported and fail closed. No generic-parser/heredoc compatibility requirement is invented. Known wrapper/eval forms and escaped/adjacent literals are covered. Installed seal correctness, provider process custody and live E2E are outside this offline approval; unchanged custody code and supplied projections are not fresh live proof.

Independently recomputed **221/221** frozen manifest entries: all match. Manifest SHA-256: 9e51dd50a6a7e627ce6b34bfb86762bf8cebc52f18bc4b0bbd5029fe08e2a9a4. Supplied R7 report SHA-256: 6b7fdb8a3ee15548769fd38c03101ca3240e6e35d9a12ababc46cca3152e59b4.

Incremental R8 versus hash-confirmed R7 LOC, independently reconstructed from the patch:

| File | Added / removed | Frozen R8 SHA-256 |
| --- | --- | --- |
| sub2api-spike/evidence.mjs | +32 / −5 | 69eb8801bf3adf3cbee8761cb497016322ad6eddb8418170b0d26ac72fd84a3e |
| sub2api-spike/evidence.test.mjs | +56 / −5 | 746d60dbdb0e93fe8c501fd4d5fc0fa4e0bfb5921ab2bd9e04895b898b382945 |
| sub2api-evidence-r2/client-contract.test.mjs | +1 / −1 | 4d18b17f345d77c2378aa30054705b8907be3228aa76164e7eecbf2f339a46e8 |
| gateway-spike/evidence.mjs | +0 / −0 | 91970dd758b12be92181dc1ed6a15c5776048af4da5dd78b7d3fdf4396960a72 |
| gateway-spike/evidence.test.mjs | +0 / −0 | 831db6a72319fcf8d57dac4ff47cc50820c0bb4ea505449aab9cc6ca5de31f98 |
| sub2api-spike/run-client.mjs | +0 / −0 | 3308b5cbaaf2b5be10d616ace4a1e47a24e013fa944514ae61054fd37d7fb490 |

Production delta +32/−5; existing tests +57/−6; retained new breakout fixture +15/−0. No reviewer production/test source changes. Only this new R8-REPORT.md is added to the workspace; canonical review history remains intact.

Scratch evidence directory: /srv/worker-state/jobs/review-router-gateway-spike/poc-20260930/rr-gateway-spike-20260930-evidence-review-r6/tmp/agent/r8-independent. Artifact SHA-256:

- `audit.json`: `c8567371a5cbd57c9a3905c39fa7519111e41e438b8d5cbe8490f1c66b7126cc`
- `commands.json`: `01d9e158ad1c1141608ed5bbe8eb7d3f6ae8ebbbef3caed35209d15492b97dd7`
- `contracts.tap`: `af762b1ab15be37bffcf7a615585b831efaa5b7565d6bfc3cb9bb2365815f799`
- `independent.tap`: `e841fdb31db494de6c329e384bbd69cff8dc3b1262cf9d80d574f5610a7558e0`
- `preserved.tap`: `83ad6effe8335f50be56eb6c4ab714ffef3dad5897d060d227c277e2b0c28947`
- `r7-red.tap`: `eee9669528a719b36a9a93bf5e22fb696cb6350cb0f209b9176a5d4b0e2831df`
- `r8-green.tap`: `44908d1d9c8417d32644c181227a49bfe1828331ab3ef537feff477bbad00816`
- `syntax.json`: `dbbdf60d4c0b5739883de74730a24fadb13dce3e4f0eabc4c6589d0852b327a6`

No Go, Docker, root/privileged operation, network, keys/auth, Git write or subagent was used. Review delivered within the requested seven-minute bound. Root rebuild/reseal and three new paid canaries remain required after approval. STOP.
