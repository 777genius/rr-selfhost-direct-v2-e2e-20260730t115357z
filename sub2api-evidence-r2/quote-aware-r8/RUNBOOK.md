The commands below use the exact full paths of the tested files. All are offline Node contract checks. Commands passed as classifier inputs in the fixtures must never be run as shell commands.

Financial/numeric caller contracts (54 tests)

```sh
node --test --test-reporter=tap /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-spike/evidence.test.mjs \
  /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/gateway-spike/evidence.test.mjs \
  /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-spike/run-client.test.mjs \
  /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-evidence-r2/client-contract.test.mjs \
  /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-evidence-r2/quote-aware-r8/quote-breakout.test.mjs
```

Preserved proof/binding contracts (10 tests)

```sh
node --test --test-reporter=tap /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-spike/oidc.test.mjs \
  /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-spike/granted-run.test.mjs \
  /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-spike/runner-isolation.test.mjs \
  /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-spike/receipts.test.mjs
```

Independent quote-breakout regressions (2 tests)

```sh
node --test --test-reporter=tap /srv/workers/jobs/review-router-gateway-spike/poc-20260930/workspaces/evidence-r8/sub2api-evidence-r2/quote-aware-r8/quote-breakout.test.mjs
```

Controller integration: apply the intact workspace diff through Project Integration, review the quote-aware patch, rebuild and reseal both installed evidence modules and selected-source imports, and run the complete existing source gate with the new quote-breakout test included. After approval, run the three paid root canaries with the existing granted model/HIGH configuration and publish their actual outcomes. None of these controller or paid actions were performed here. Keep historical run 36879127384 FAILED regardless of these offline results.
