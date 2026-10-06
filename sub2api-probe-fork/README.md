Prepared a standalone patch against the fresh supplied Sub2API v0.2.11 / `96f4c115c9749078f90cbf210a01d39baf3f53b6` tree. It adds 266 lines across two production files and two narrow unit-test files. Go compilation, tests, original red controls, race checks and gofmt are **NOT_RUN**: this worker has no Go/gofmt executable or supplied pinned module cache. This is a bounded review handoff, with no canary approval.

`patches/disable-capability-probe.patch` is the complete repo-relative patch; apply from the upstream repository root with `patch --batch --fuzz=0 -p1 < disable-capability-probe.patch`. It needs no earlier fork patch. `SOURCE.json` binds exact original/patched file hashes, complete tree hashes and patch SHA-256. Source files match the existing before-hash manifest; Git commit authenticity remains unverified because the staged source has no Git metadata. `verification.json` records successful actual standalone application to an original copy, with no fuzz, matching patched hashes and an unchanged upstream input.

Only a persisted trusted admin account `Extra` boolean `openai_disable_capability_probe: true` suppresses the background Responses capability probe, scoped to `platform=openai` and `type=apikey`. Missing, null, false and non-boolean values retain existing behavior. OAuth and all CN-provider branches retain existing behavior. The handler checks before scheduling its goroutine; the concrete service reloads the repository account and checks before HTTP or capability metadata writes. No forwarding, billing, refresh, model selection, protocol or dependency changes are included. Disabled/unschedulable accounts without this flag still probe as before.

The control lane must persist the flag on its scoped inert template before credential preparation. The switch reads account Extra; it does not read inference request bodies. It neither authorizes an inference opt-in nor changes customer forwarding. Stock admin APIs remain a trusted boundary; this patch adds no new customer API. A probe whose fresh load observes true cannot execute or write capability metadata; a later flag change cannot cancel an already dispatched request. The coordinator should test the real database/handler timing boundary before credentials are installed.

Inspected stock `DuplicateAccount` calls `duplicateAccountExtra`, which deep-copies via JSON and discards an explicit list of runtime keys. The new boolean is outside that list and survives unchanged. The new duplicate test invokes the actual duplicate service, checks the stored copy and verifies map independence. The duplicate implementation and `account.go` are unchanged.

The tests use the existing concrete `AccountTestService`, repository and HTTP interfaces. Actual PUT handler execution feeds actual generated model requests to a counting in-memory HTTP handler; method, Responses path, synthetic key, mapped model and required tool choice are checked. Both HTTPUpstream methods dispatch through the counting handler, so a switch between Do and DoWithTLS cannot bypass the counter or use a nil embedded transport fallback. No sockets or provider requests are needed. The PUT matrix checks zero repository loads as well as zero HTTP/model calls and metadata writes when disabled, alongside positive controls, non-boolean values, nil Extra, OAuth, other platforms, all four CN providers, and ignored credential/top-level request fields. CN support/mode writes are checked. A channel barrier pauses the actual queued handler goroutine inside the fresh repository load; `testing/synctest.Wait` waits for blocked/completed goroutines instead of short sleeps. The direct service test independently counts requests and metadata writes with a default positive control.

Coordinator verification, using its pinned Go 1.27.1 and existing module cache (set `PROBE_GO` and `PROBE_GOMODCACHE` to supplied paths):

```sh
mkdir -p .spike-inputs/probe-go-cache .spike-inputs/probe-go-tmp
cd .spike-inputs/probe-source/backend
env GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off \
  GOMODCACHE="$PROBE_GOMODCACHE" GOCACHE="$PWD/../../probe-go-cache" TMPDIR="$PWD/../../probe-go-tmp" \
  "$PROBE_GO" test -mod=readonly -tags=unit -count=1 -timeout=120s \
  ./internal/handler/admin ./internal/service \
  -run '^(TestCapabilityProbe|TestDuplicateAccountPreservesTrustedCapabilityProbeDisable|TestProbeOpenAIAPIKeyResponsesSupport|TestSelectResponsesProbeModel|TestDecideResponsesProbeSupport|TestResponsesProbe)'
```

Run the same focused tests with `-race` if the coordinator's pinned toolchain supports it. Check formatting with that toolchain's sibling `gofmt -l` on the four patch files. Preserve run outputs bound to the patch hash; if formatting or repairs change bytes, regenerate one complete standalone patch and both manifests before review.

Original red controls are identified, **not executed**. Keep the two added test files and temporarily restore the two production files from `.spike-inputs/upstream` inside `.spike-inputs/probe-source`. These tests do not depend on the new helper, so they can run against original code:

| Test case | Expected original failure | Patched requirement |
| --- | --- | --- |
| `TestCapabilityProbeTrustedExtraPUT/true` | Repository loads 1, HTTP/model call 1, metadata write 1 | All three counts 0 |
| `TestCapabilityProbeQueuedFreshAccount/newly_disabled` | After barrier release, HTTP/model call 1 and metadata write 1 | Both counts 0 |
| `TestCapabilityProbeServiceNoEffects/disabled` | Request count 1 and metadata write 1 | Both counts 0 |

The default controls should pass original and patched; duplicate preservation should already pass original. Removing only the handler guard must fail the PUT load-count assertion even if the service prevents HTTP. Removing only the service guard must fail the queued/direct-service zero-call assertions. Restore the complete standalone patch against the original afterward.

Read the complete BR02 boundary review. Its required real handler/counting synthetic server and delayed execution gate remains coordinator-owned, followed by independent review; live credentials/providers must wait for that gate. This lane performed no external E2E, network, Docker/root operations, credentials/auth-home access or Git writes. Authored deliverables are confined to `sub2api-probe-fork/`; editable source is the ignored `.spike-inputs/probe-source/`, with no nested Git or vendor tree.

Coordinator applied pinned gofmt to account_capability_probe_test.go only. All production bytes unchanged; original artifact retained and SOURCE patch/tree hashes updated. Prior behavioral results cover the same code; final combined checks still required.
