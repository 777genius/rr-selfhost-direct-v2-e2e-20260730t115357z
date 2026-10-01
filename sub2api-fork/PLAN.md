# Sub2API fork compatibility and regression experiment

Owner request 2026-10-01: continue autonomously, fix the native Codex+MiMo thinking path and exercise end-to-end scenarios. Work stays in the existing disposable gateway project. No production cutover, customer identities, provider-key export, model switching or tool-output substitution.

## Required outcome

1. A small pinned upstream patch preserves unencrypted reasoning for explicitly configured native compatible accounts. Existing OpenAI/OAuth default behavior remains unchanged. No global normalization bypass or provider-type impersonation.
2. Genuine Codex+MiMo thinking-enabled Actions review passes the existing strict financial contract. Codex+OpenRouter and Claude+MiMo native paths regress on the same reviewed harness/image. Pinned clients, fixture, models and immutable engine build provenance.
3. Resolve the known control-plane custody and account-create orphan findings where the sandbox adapter owns the boundary. Keep default denial, per-workspace authority and native SSE error fence.
4. Re-run the current 77-scenario matrix at its actual boundaries. Reproduce failures before fixes. Cancellation must distinguish local disconnect/capacity release from a provider's remote inference policy. Synthetic OAuth does not become live OAuth proof; no production subscription account is imported.
5. Independent exact-code review, safe rollback, final report with failed attempts retained, custody scan and teardown of owned resources.

## Isolated lanes

- **Fork producer:** owns `sub2api-fork/` only. Read pinned v0.2.11 source from `.spike-inputs/upstream`; editable build source goes in ignored `sub2api-fork/build-source/`. Deliver patch against `96f4c115c9749078f90cbf210a01d39baf3f53b6`, focused backend tests, application/hash manifest and a short source report. Never commit the vendored source tree. No credentials, Docker, GitHub writes or live inference.
- **Harness producer:** owns the existing account adapter/tests, run-client, new runner-isolation helpers/tests and the disposable Actions workflow. Build privileged-control/unprivileged-agent UID separation and quarantine/reconcile for ambiguous account creation. Do not alter final evidence rules or financial fixture. No provider secrets, host Docker or live dispatch.
- **Regression audit:** owns `sub2api-regression-audit/` only. Inspect current evidence, fault lab and upstream source. Map every remaining FAIL/NOT RUN to a concrete reproducible experiment and acceptance oracle; identify feasible tests and genuine external limits. Read-only elsewhere; never inflate coverage through source-text or mock-only tests.
- **Coordinator:** handles exact-source transfers, public dependency preparation, isolated engine builds, trusted root-only key loading, genuine Actions dispatch, code integration and custody scans. Commits use `iliya <iliyazelenkog@gmail.com>` for author and committer. Final independent reviewer consumes exact integrated SHA and sanitized receipts.

All workers use hosted subscription-runtime, gpt-6.1-sol with explicit effort and serviceTier default. Each has a separate job/workspace and disjoint ownership. Do not interrupt a healthy max-attempts=1 worker to send guidance; deliver guidance at a safe point. Preserve partial outputs rather than resetting manifests or bypassing policy gates.

## Checks and stop rules

- Before adding a test, identify the real observable breakage that makes it red. A meaningful nearest-boundary contract is preferable to duplicated mocks or source grep.
- Paid executions are individually planned, retries disabled, known terminal failures may lead to a distinct corrected experiment. Inspect effects after an uncertain outcome before any new request.
- Stop live inference if key custody, tenant isolation, duplicate effects or unreviewed dispatch fails. Continue independent source/synthetic work.
- Native reasoning preservation must prove multi-turn tool association and genuine final answer, not just response.completed. Empty final output stays a failure.
- Build one immutable patched-engine image, record parent revision +patch hash +image digest. Test that image, never a moving tag.
- No claim of indefinite reliability, live OAuth coverage without test credentials, or guaranteed remote inference cancellation unsupported by the provider.

## Initial facts

Sub2API v0.2.11 latest release, LGPL-3.0. Existing sandbox head `956603247f893ece0b9d1ec08d2cbe013342c48d`. Six failing provider/client Responses were byte-identical. Exact last-request pair differs only five reasoning history items: stripped yields no message; retained yields message. Nonthinking workaround passed full financial contract; it is insufficient for this task. Original Actions failures remain recorded.
