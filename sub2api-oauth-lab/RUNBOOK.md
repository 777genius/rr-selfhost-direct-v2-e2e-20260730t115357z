# OAuth lab w1: coordinator execution

Worker result: **NOT RUN**. Neither `go` nor `gofmt` is installed in this sandbox. A one-shot loopback bind succeeded; no PostgreSQL, Redis, provider, or existing service endpoint was contacted. These are prepared integration fixtures, not compiled or passing regression evidence.

## Scope and patch

Expected parent: Sub2API `96f4c115c9749078f90cbf210a01d39baf3f53b6`, supplied under `.spike-inputs/upstream`. `source-manifest.json` fingerprints the supplied source, selected dependency boundaries, modules, migrations, three authored tests, and `tests.patch`. The parent SHA is the supplied pin, corroborated by the original spike manifest; it was not independently resolved from Git in this worker. Verify the staged tree against the coordinator's pinned source before execution.

Apply in a separate disposable source copy without nested Git. The patch adds only:

- `backend/internal/repository/oauth_lab_fixture_test.go`
- `backend/internal/repository/oauth_lab_worker_test.go`
- `backend/internal/repository/oauth_lab_lifecycle_test.go`

From that source root:

```sh
patch --dry-run -p1 < "$OAUTH_LAB_PATCH"
patch -p1 < "$OAUTH_LAB_PATCH"
```

`OAUTH_LAB_PATCH` is the absolute path to this lane's `tests.patch`. Do not use `-tags integration`: upstream's repository integration `TestMain` launches Docker and may exit successfully without running tests when Docker is absent. The independent `oauthlab` build tag extends the same-package repository integration boundary while excluding that harness. There are no new modules or production changes. No global HTTP transport or DNS replacement is installed.

## Required disposable services

Only the trusted synthetic operator supplies configuration. Use a newly created dedicated database whose name begins `oauth_lab_`, with `public` as its current schema, and an empty nonzero Redis database (for example `/1`). The fixture rejects an account-populated database and populated Redis database before applying upstream migrations. This guard supplements operator isolation; it is not authorization to probe other services. A failed or interrupted run requires inspection of its owned rows/resources before another run. Never point these variables at existing deployments.

The following commands are **coordinator instructions, not worker executions**. The coordinator supplies immutable image references, an already prepared Go 1.27.1 image with its module cache, a disposable source copy, and a writable receipt directory. Choose fresh resource names for every execution. Services and test process share an internal Docker network with no host port publication. Do not mount a Docker socket, credentials, auth homes, or production state into the test process.

```sh
# Set these to coordinator-resolved immutable OCI references and prepared paths:
# OAUTH_LAB_PG_IMAGE, OAUTH_LAB_REDIS_IMAGE, OAUTH_LAB_GO_IMAGE
# OAUTH_LAB_SOURCE (source root), OAUTH_LAB_MODULE_CACHE, OAUTH_LAB_RECEIPTS
# Fresh simple alphanumeric/underscore suffix:
OAUTH_LAB_SUFFIX=w1_20261001_unique
OAUTH_LAB_NET=oauth-lab-${OAUTH_LAB_SUFFIX}
OAUTH_LAB_PG=oauth-lab-pg-${OAUTH_LAB_SUFFIX}
OAUTH_LAB_REDIS=oauth-lab-redis-${OAUTH_LAB_SUFFIX}
OAUTH_LAB_DB=oauth_lab_${OAUTH_LAB_SUFFIX}
for OAUTH_LAB_IMAGE in "$OAUTH_LAB_PG_IMAGE" "$OAUTH_LAB_REDIS_IMAGE" "$OAUTH_LAB_GO_IMAGE"; do
  case "$OAUTH_LAB_IMAGE" in *@sha256:*) ;; *) exit 1 ;; esac
done

docker network create --internal "$OAUTH_LAB_NET"
docker run -d --name "$OAUTH_LAB_PG" --network "$OAUTH_LAB_NET" \
  --network-alias oauth-lab-pg --tmpfs /var/lib/postgresql:rw \
  -e PGDATA=/var/lib/postgresql/18/docker \
  -e POSTGRES_USER=oauth_lab -e POSTGRES_DB="$OAUTH_LAB_DB" \
  -e POSTGRES_HOST_AUTH_METHOD=trust "$OAUTH_LAB_PG_IMAGE"
docker run -d --name "$OAUTH_LAB_REDIS" --network "$OAUTH_LAB_NET" \
  --network-alias oauth-lab-redis "$OAUTH_LAB_REDIS_IMAGE" \
  redis-server --save '' --appendonly no --databases 16
```

Use the original lab's PostgreSQL 18.6 and a coordinator-pinned Redis 8 build, and record actual versions/digests. The SQL role must be able to execute upstream migrations and create/drop the fixture's targeted PL/pgSQL trigger. Trust authentication above is confined to the fresh internal synthetic network; there are no real authentication values to export. Wait on the specific fresh containers' health/readiness before the test command; do not query supplied existing services. The tests themselves apply the supplied migrations once to that database. All subcases run serially, create distinct database IDs and fabricated identities, and remove only their own account/cache/outbox records. The rejection trigger has a unique name and targets only its own account ID.

## Coordinator command

The Go image must contain exactly Go **1.27.1** and the prepopulated module cache required by the staged `go.mod`/`go.sum`. Supply `OAUTH_LAB_MODULE_CACHE` as the module-cache directory itself. Go compilation and runtime were not verified here; preserve compiler/runtime failures and any repaired test/patch hashes as distinct attempts. Do not edit acceptance expectations to turn an upstream contract regression green.

```sh
docker run --rm --network "$OAUTH_LAB_NET" \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$OAUTH_LAB_SOURCE/backend,dst=/work" \
  --mount "type=bind,src=$OAUTH_LAB_MODULE_CACHE,dst=/go/pkg/mod,readonly" \
  --mount "type=bind,src=$OAUTH_LAB_RECEIPTS,dst=/receipts" \
  -w /work -e GOTOOLCHAIN=local -e GOPROXY=off -e GOSUMDB=off \
  -e GOPATH=/go -e GOCACHE=/tmp/oauth-lab-go-build -e GOMAXPROCS=2 \
  -e OAUTH_LAB_ENABLE=disposable-synthetic-only \
  -e "OAUTH_LAB_PG_DSN=postgres://oauth_lab@oauth-lab-pg:5432/$OAUTH_LAB_DB?sslmode=disable" \
  -e OAUTH_LAB_REDIS_URL=redis://oauth-lab-redis:6379/1 \
  --entrypoint /bin/sh "$OAUTH_LAB_GO_IMAGE" -c \
  'go version > /receipts/go-version.txt; go test -json -tags oauthlab -run "^TestOAuthLabLifecycle$" -count=1 -timeout=8m ./internal/repository > /receipts/go-test.jsonl 2>&1; OAUTH_LAB_EXIT=$?; printf "%s\n" "$OAUTH_LAB_EXIT" > /receipts/test-exit-code.txt; exit "$OAUTH_LAB_EXIT"'
```

For an already isolated operator test environment, the equivalent backend command is:

```sh
GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOMAXPROCS=2 \
  go test -json -tags oauthlab -run '^TestOAuthLabLifecycle$' -count=1 \
  -timeout=8m ./internal/repository > "$OAUTH_LAB_RECEIPT_PATH" 2>&1
```

It requires the same three explicit `OAUTH_LAB_ENABLE`, `OAUTH_LAB_PG_DSN`, and `OAUTH_LAB_REDIS_URL` variables. Without them the test calls `t.Skip`: **NOT RUN**, regardless of a zero exit code. All three must be present before fixture setup. A connection/migration failure or compile error is an execution/setup failure, not a proven upstream OAuth race.

The issuer has a global 128-request acceptance guard. The authored workload admits at most 56 application-level refresh attempts across twelve cases, assuming the supplied HTTP client makes one POST per refresh invocation; actual counts are mandatory and any unexpected transport retries or budget exceedance fail the run. No test-level retries or repeated `-count` runs are authorized by this command. Background behavior intentionally uses the real upstream service with its explicit three-attempt limit so automatic retry after consumed R0 is observable. Request operations and startup background cycles have contexts, each case has a 25-second bound, each child has a 30-second process bound, and the whole test has the timeout above. Redis polls assert observed key state, not elapsed sleeps. Other synchronization uses SQL commit observations, issuer request barriers, real Redis command results, IPC acknowledgements, and actual background-cycle completion.

## Positive receipts and boundaries

Each completed case emits one `OAUTH_LAB_RECEIPT` JSON object inside Go test output. For a PASS, require the corresponding Go subtest's terminal pass event and all of:

- Unique `case_id`, positive `synthetic_account_id`, independent `synthetic_identity_id`.
- Two distinct `child_pids`, each backed by `ready` and operation results in `events`; `child_exits_ok=true` and `owned_cleanup_ok=true`.
- Actual PostgreSQL/Redis/Go versions, elapsed duration, exact staged source and final test/patch hashes, image digests, coordinator execution identity/attempt, test command and exit status. The outer operator receipt adds provenance fields not available inside the test process.
- Positive case-specific barriers listed in `results.json`; actual issuer/effective-rotation/resource counts, no malformed forms, and total issuer requests at most 128. A setup failure, absent result, timeout, skip, empty output, or missing barrier is never PASS.
- Durable state from an independent PostgreSQL account-repository reread; safe symbolic credential phases only. Parser assertions verify fabricated JWT identity fields and response expiration against the real parser. No JWT, bearer, refresh-token value, raw error body, or token hash belongs in a receipt.

Retain failing assertions and original receipts. Cases expected to expose source risks are ordinary failing tests, never `Skip`, `xfail`, or `assert expected bug`. `REPORT.md` distinguishes unexecuted source hypotheses from actual failures. A Go process exit code alone is insufficient; a green subset cannot establish the twelve-case contract.

This tests two OS processes with independently constructed real repositories, Redis clients, refresh APIs/executors, token providers and gateway auth selectors. Background cases run `TokenRefreshService.Start()`'s actual initial cycle and wait for its structured completion event, then `Stop()` joins it. The real `openaiOAuthService{tokenURL: localIssuerURL}` and `OpenAITokenProvider.SetRefreshAPI` seams are used unchanged. The synthetic resource request sets its Authorization header from the actual `OpenAIGatewayService.GetAccessToken` result. Full native HTTP `Forward`, Responses/SSE, billing, tenant admission and live OAuth/JWKS are outside this nearest auth-selection contract. In particular, the synthetic HTTP resource client is fixture code; it is not a claim that the production HTTP forwarding stack was executed.

Reconnect is an actual PostgreSQL credential replacement plus actual Redis invalidation/publication, representing the management persistence boundary; no browser login or authorization-code exchange is claimed. Lost-ack injection commits a real PostgreSQL transaction then hides its acknowledgement at the test SQL-driver boundary; it does not emulate a network partition or fabricate R1. The companion targeted PostgreSQL trigger causes a real rejected write after issuer consumption, exposing consumed-R0 retries when R1 is not durable. Redis outage is real TCP connection failure on a fixture-owned loopback endpoint, not stopping a shared server or substituting a fake cache. These remain synthetic tests; original live F07/F08 and production-pool regression F09 coverage do not change.

After receipts are collected, the coordinator removes only the two named disposable service containers and their fresh internal network, and the disposable source/receipt staging it owns. Do not remove other lanes or shared caches. Integration, commits and pushes belong to the coordinator using the requested iliya identity; this patch contains no Git writes.
