# Standalone provider gateway spike

Completed live on 2026-09-30 in disposable project **review-router-gateway-spike/poc-20260930**. See [REPORT.md](REPORT.md) for Actions evidence, measured effort, limitations and the product delivery plan.

## Proven path

GitHub Actions OIDC -> ReviewRouter spike broker -> private OSS Bifrost -> provider.

CI receives a random temporary run capability. The upstream provider key and the Bifrost virtual-key value stay on the server. Credential authorization is independent of agent identity; clients use native Responses or Anthropic Messages profiles. Actual Codex/MiMo, Codex/OpenRouter and Claude Code/MiMo reviews passed. This is a standalone proof, not a deployed SaaS feature.

## Reproduce safely

```sh
node --test gateway-spike/*.test.mjs
node gateway-spike/broker.mjs /private/broker-config.json
# Called by the approved disposable Actions workflow, from gateway-spike/:
node run-client.mjs mimo codex
```

The live environment was torn down and its workflow disabled. Reproduction requires a fresh isolated gateway, approved workflow SHA, ephemeral repo-scoped runner and explicit planned canaries. Never run these agents against a real user project.

`broker.config.example.json` contains no master key. Set `workflowSHA` to the exact immutable SHA of the approved main workflow. Use real Bifrost DBKey UUIDs for `keyID`, not display names. Owner ID is 13103045 and disposable repository ID is 1317214237. `BIFROST_ADMIN_AUTH` is a private server admin session and never belongs in the runner.

## Authorization and lifecycle

The broker verifies RS256 signature/JWKS, issuer, audience, times, repository/owner IDs, exact workflow ref/SHA, event, main ref, run ID and attempt. It reserves run/provider/protocol scope in a durable append-only ledger before admin effects. Same-process replay returns the existing capability; restart and ambiguous failures consume the old scope and deny reminting. One broker process only; production requires transactional storage and reconciliation.

Limits are 2 MiB JSON, 32 attempts per run, two in-flight requests, 120-second request timeout, TTL <= 900 seconds bounded by GitHub OIDC expiry (about five minutes in these runs). Expiry/revocation abort active streams. Delete failures leave local access denied and log metadata only. `close()` attempts to revoke every known virtual key; the operator must reconcile orphaned gateway keys after interruption.

Only these fixed routes exist:

- GET `/health`.
- POST `/grant` with provider/protocol only.
- POST `/openai/v1/responses`.
- POST `/anthropic/v1/messages`, including the exact `?beta=true` SDK variant.

Other queries, admin paths, Chat, count_tokens and arbitrary URLs are rejected. Caller authentication/routing headers are replaced; only Anthropic version/beta headers propagate. Model must exactly match the capability's server binding. Codex `client_metadata` is removed. Proprietary Claude safeguards are unsupported; this spike explicitly uses the client's `default` permission mode with Read/Glob/Grep only.

The broker forwards Bifrost response bytes/status without retry or fallback. Bifrost may normalize error envelopes: the pinned build turned upstream Responses `response.failed` into HTTP 400 JSON. The actual Codex error probe still exited unsuccessfully and never reported completion. Truncation produced failure, not an invented successful review.

## Pinned private gateway

OSS Bifrost **v2.2.4**, source **ed8371a9779bfbc8aa689d4d77964cf8ce9308bf**, image **maximhq/bifrost@sha256:5f8215163cea192451f4b2ee5e0b583874ffe9435a5ab733e08c07aaf38ace57**.

`bifrost.template.json` is a secret-free transport/auth template, not a complete deploy configuration. Empty provider keys prevent inference. The operator must supply root-only key material via server environment references, a private encrypted config store, a private logging configuration, DBKey UUIDs, and isolated networks. Mandatory inference authentication was verified with actual unauthenticated 401 probes.

Verified provider profiles:

| Profile | Base provider | Origin | Upstream route | Tested model |
|---|---|---|---|---|
| MiMo Responses | openai | `https://token-plan-sgp.xiaomimimo.com` | `/v1/responses` | `mimo-v2.6-pro` |
| OpenRouter Responses | openai | `https://openrouter.ai` | `/api/v1/responses` | `openai/gpt-4.1` |
| MiMo Messages | anthropic | MiMo region origin above | `/anthropic/v1/messages` | `mimo-v2.6-pro` |

Bifrost's Anthropic ingress internally selects `responses`/`responses_stream` even for native Messages requests. Enable these operations and their Messages path overrides on the anthropic custom provider. The upstream wire remains Anthropic; an OpenAI adapter or Chat bridge is not required. Bifrost's internal normalization is still a compatibility dependency and is not a claim of universal byte-for-byte transparency.

Admin creates `/api/governance/virtual-keys` with `allow_all_providers:false`, one exact provider/key/model binding and expiry. The response is `{virtual_key:{id,value,...}}`; DELETE its ID revokes it. Provider-level PUT and provider-key PUT are separate endpoints. Never accidentally clear the key value during metadata updates.

Primary references: [custom providers](https://docs.getbifrost.ai/providers/custom-providers), [virtual keys](https://docs.getbifrost.ai/features/governance/virtual-keys), [Codex profile](https://docs.getbifrost.ai/cli-agents/codex-cli), [MiMo Codex](https://mimo.mi.com/docs/en-US/tokenplan/integration/codex-configuration), [MiMo Claude Code](https://mimo.mi.com/docs/en-US/tokenplan/integration/claudecode). Exact pinned source was inspected via gh CLI.

## Runner isolation and evidence

Gateway and admin share a private control network accessible to broker/operator only. The runner joins the separate inference network and its own egress network, never the control network. No host public ports, host mounts or Docker socket are exposed to runners. These are private self-hosted Actions jobs, not GitHub-hosted runner/public TLS evidence. Internet egress exists for GitHub; a production provider-egress allowlist remains future work.

Pinned clients: Node 24.21.0, Codex **0.159.2**, Claude Code **2.1.285**. Workflow actions: checkout **v7.0.1** at `3d3c42e5aac5ba805825da76410c181273ba90b1`, upload-artifact **v7.0.1** at `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`. Permissions are contents:read/id-token:write; checkout credentials are not persisted and no repository provider secrets are referenced.

Agents receive a clean temporary home and an allowlisted environment, without OIDC runtime auth, provider key or subscription auth. The fixture is a pinned root-owned read-only image snapshot; the client compares its bytes with checkout before granting access. Prompt does not reveal the bug. Evidence requires successful actual source-reading tools and a correct concrete negative-withdrawal example, not merely output mentioning a filename.

Codex's nested read-only sandbox could not create bwrap inside this Docker host. The spike instead used `danger-full-access` inside the isolated unprivileged outer container, with the fixture sealed against writes/chmod/rename. This proves fixture review and key custody, not a production-wide read-only agent sandbox. Other runner files remain writable/readable according to their normal permissions; repo-scoped runner credentials need separate production isolation.

Only fixed normalized `evidence/result.json` is published. Successful private homes are removed. Failed transcripts stay inside stopped private disposable runners for diagnosis and were deleted with those containers after custody verification. All 14 complete exported runner filesystems, configuration/logs, 14 Actions logs, three normalized artifacts and the source bundle were scanned against actual master-key bytes on the server: zero matches.

## Remaining product work

Reuse existing SaaS key custody, workspace policy, OIDC exchange and provider configuration. Add credential references instead of provider GitHub secrets, transactional run grants, rotation/revocation, public TLS, metadata redaction and compatibility gates. Keep the existing Codex subscription/account-pool relay as its own credential adapter. The spike did not modify or regress-test that production route.

The hosted implementation/review workers used subscription-runtime, `gpt-6.1-sol`, explicit medium/high effort and isolated workspaces. Agent tests and provider requests used only the disposable project. No ReviewRouter production code or deployment changed.
