# OAuth lifecycle integration handoff

**Prepared; runtime and compilation NOT RUN.** This lane adds three same-package Go integration test files, a repository-relative `tests.patch`, source/test hash manifest, per-case ledger and coordinator runbook. Only `sub2api-oauth-lab/` was authored. No production source, other lane, credential/auth home, live provider, existing endpoint, Docker/socket, commit or push was used.

Read `sub2api-fork/PLAN.md` and the original `sub2api-spike/PLAN.md`, `REPORT.md`, and `results.json`. Original F04/F05/F06 lifecycle gaps motivated this contract. Those files and their existing verdicts remain untouched. A successful synthetic execution would add bounded synthetic evidence, never live subscription or production-pool proof.

## What the patch exercises

The patch extends `backend/internal/repository` with the separate `oauthlab` build tag. Using `integration` would invoke upstream's Docker `TestMain` and could silently exit before executing tests. Each case uses unique account/issuer identities. Two real child test-binary processes independently instantiate PostgreSQL account repositories, Redis caches/locks, the real OpenAI HTTP token client/parser, OAuth refresh API, refresher, token provider, and gateway bearer selector. No shared coordinator object or fake persistence supplies a pass.

Normal concurrency prepares eight real database snapshots and releases request goroutines across the two processes. Real Redis contention is observed while the single-use issuer holds the first rotated HTTP reply. Background/request cases run the actual startup background-service cycle in both race orders. Reconnect/disable are committed through the actual account repository while the issuer reply is held; both durable and actual Redis scheduler account snapshots are checked after background completion. TTL expiry is observed from Redis before a second process obtains a live successor lease. The previous owner's release must not erase that lease. Redis outages use a fixture-owned TCP failure endpoint: one-process serialization and a separate two-process race have different oracles, with cross-process failure retained as FAIL if observed.

Confirmed synthetic `invalid_grant` is exercised through request and actual background paths, followed by real scheduling-repository queries and new synthetic bearer work. Lost PostgreSQL acknowledgement is injected only after a real transaction commits; an independent repository must find R1. A companion real PostgreSQL trigger rejects credential persistence after issuer consumption and observes the real background retry policy. It must never retry consumed R0 automatically. The issuer rotates at most once per independent identity and all resource authorization results come from actual HTTP interactions using the gateway selector's bearer.

## Current evidence

| Check | Result | What it proves |
|---|---|---|
| Go/compiler/gofmt availability | NOT RUN; neither executable present | Worker cannot compile, format with Go, or execute Go tests |
| One-shot loopback bind | Available | A local socket can bind; no OAuth test or external service was contacted |
| PostgreSQL/Redis lifecycle execution | NOT RUN | No operator-supplied test configuration was used |
| Twelve behavioral cases | NOT RUN | Authored fixtures only; no actual upstream runtime FAIL or PASS exists yet |
| Patch preparation/dry-run and hash consistency | See `verification.json` | Packaging integrity only, never OAuth behavioral coverage |
| Git lock/repository preflight | Repository metadata unavailable | `.git` points outside this worktree at an unavailable target; lock visibility does not prove an unlocked repository. No bypass or Git mutation followed |

The supplied pin is `96f4c115c9749078f90cbf210a01d39baf3f53b6`, matching the original spike manifest. Git cannot resolve the current linked worktree metadata here, so `source-manifest.json` records the actual staged source fingerprint and selected source/module hashes rather than asserting an independently verified commit checkout. The coordinator must match the staged source to its pinned input before compiling. The source's `go.mod` requires Go 1.27.0; the authorized coordinator toolchain is Go 1.27.1. No substitute toolchain or dependency install was attempted.

## Observable red conditions

| Case | Actual regression that makes the test red |
|---|---|
| normal_8_concurrent | More than one token POST, lost R1, malformed issuer form, or any A0/unknown bearer instead of eight successful A1 requests |
| background_then_request | Actual background refresh and stale request race sends another R0 or republishes/selects A0 |
| request_then_background | Startup background refresh fails to respect the request-held Redis lock or selects stale bearer later |
| reconnect_while_refresh | A stale refresh overwrites committed reauthorization in PostgreSQL, scheduler Redis or subsequent gateway bearer selection |
| disable_while_refresh | Disabled row becomes schedulable, or background publishes its stale active/schedulable snapshot to actual Redis |
| lock_ttl_expiry | Consumed R0 is sent again, or old owner deletes another process's demonstrably live successor lease |
| redis_outage_process_local_8 | Actual Redis connection failures allow duplicate local refresh or stale bearer selection |
| redis_outage_two_process_race | Independent coordinators refresh the same consumed R0 under outage or fail open to A0 |
| revocation_request_path | Confirmed invalid_grant is swallowed, stale bearer selected, or revoked account remains available for new work |
| revocation_background_path | Background invalid_grant fails to exclude the account and deny subsequent bearer work before effects |
| issuer_rotation_lost_db_commit_ack | Hidden acknowledgement of actual PostgreSQL commit causes consumed-R0 replay, loss of durable R1, or false revocation |
| issuer_rotation_db_write_rejected | Real failed PostgreSQL persistence after issuer rotation automatically retries R0 or admits new work with uncertain consumed credentials |

These are intended behavioral contracts, not source-text assertions. Inspection indicates likely unhandled OpenAI races: its successful persistence uses unconditional `UpdateCredentials`; the background service may publish a stale account snapshot; OAuth refresh-lock release performs unconditional Redis `DEL`; Redis failures retain only a coordinator-local mutex; default OpenAI provider policy falls back to the existing token after errors; OpenAI credential-persistence failures enter the background retry loop. These are **source hypotheses**, not experimentally observed FAILs. Nothing was patched to weaken them or preemptively change production behavior. Existing unit stubs were read for constructors and contracts, not counted as integration proof.

## Limits and handoff

The executable boundary is actual gateway bearer selection followed by a fixture-issued HTTP resource request, not the production gateway's native HTTP Forward/SSE/billing stack. Full scheduling-service admission is not claimed: scheduling eligibility is checked through the real repository and Redis account snapshot. Reconnect represents actual management credential persistence, not a browser OAuth login. Fabricated JWTs exercise the actual decoder/expiration parser; they do not prove signature verification, JWKS, subscription entitlement or live refresh behavior. The lost-ack driver fault is a precise test boundary after a real durable commit, not an OS network-partition experiment. No real token or token hash appears in authored receipts.

The runbook supplies isolated PostgreSQL/Redis preparation, exact bounded coordinator commands and required positive receipt fields. The configured workload has a conservative 56 application-level refresh-attempt bound; the synthetic issuer additionally rejects beyond its 128-request global budget and the receipt gate rejects any overrun. All cases have SQL/issuer/Redis/IPC barriers and deadlines; there is no sleep-only assertion. No test-level retries, new dependencies or production seams were added. Compilation/runtime repairs are explicitly left to the coordinator's pinned Go 1.27.1/module-cache environment, with original failures and revised hashes retained. Do not interpret a skip or missing receipt as PASS.

The authorized fixture-preparation fallback is delivered. No operator wait or external action was requested. The remaining uncertainty is compilation and real isolated-service execution, recorded as NOT RUN rather than fabricated regression evidence. Coordinator integrates the scoped patch under the requested iliya identity; workspace changes remain uncommitted.
