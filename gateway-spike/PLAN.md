# Provider gateway live spike

Authorized by owner on 2026-09-30. Test-only; no ReviewRouter production changes.

## Question and acceptance

Prove a real GitHub Actions job can run Codex with MiMo Token Plan and OpenRouter through a pinned OSS Bifrost gateway, while provider keys remain server-side. Key custody and run authorization must not depend on agent name. Protocol adapters cover Responses now and Messages for Claude Code.

Repository: 777genius/rr-selfhost-direct-v2-e2e-20260730t115357z, immutable ID 1317214237. Existing public disposable repository; preserve old workflows and evidence. Host workers-fsn1-01, machine-id d856d40da5ad4e23b4f67773e5942842. Temporary isolated containers/networks, no production DNS/services/database or other jobs changed.

## Execution

1. Prepare broker + deterministic transport/security tests + synthetic review fixture + workflow. Hosted subscription-runtime implementation worker owns only gateway-spike/ and .github/workflows/provider-gateway-spike.yml. Use gpt-6.1-sol medium, fast tier authorized by the owner. No credential access, live model requests, Docker or GitHub writes by coding worker.
2. Pin Bifrost OSS transports/v2.2.4 (source ed8371a9779bfbc8aa689d4d77964cf8ce9308bf) and image digest. Enable mandatory inference authentication; private admin endpoints; content logging off; encryption at rest. Use native upstream Responses, no Responses-to-Chat bridge for native providers. Explicit MiMo region from existing runtime metadata.
3. Coordinator injects existing root-only credentials exclusively into gateway container. Never mount keys, auth roots, Docker socket or host directories into runner. Use separate internal control network for gateway administration and runner network for broker inference. No host public ports required for this spike.
4. Broker verifies GitHub RS256 OIDC signature from issuer JWKS, issuer, audience, exp/nbf, immutable repository/owner ID, trusted workflow ref and exact workflow SHA, event, ref, run ID/attempt. Pin expected SHA at startup. Allowlisted provider/model/protocol configured by server; reject unknown aliases/URLs/headers. Issue a random expiring run capability mapped to one pinned server-created Bifrost virtual key. Bound request count, concurrency, bytes and lifetime; no fallback and no automatic model-call retry. Capability is usable in CI but is not the provider key.
5. Ephemeral repo-scoped GitHub runner in isolated container runs workflow_dispatch. No repository provider secrets referenced or injected. The workflow obtains OIDC then a run capability, configures clean ephemeral agent home, runs synthetic review with tool use, asserts finding and saves sanitized evidence. Codex must inspect files using an actual tool, not merely echo a prompt. Run one planned canary per provider; inspect outcome before any remedial retry. Use read-only review tools.
6. Validate Claude Messages via deterministic upstream contract; prefer a real Claude Code/MiMo canary if available, and distinguish mock versus live proof. Preserve version, event types, tool results, errors/cancellation. Do not promise all agent/provider combinations.
7. Independent hosted gpt-6.1-sol review of exact code/patch, integrate with owner identity, then execute unresolved gates. Scan outputs/server receipt against provider secret bytes locally on server without returning values or hashes. Assert no master key in runner env/files/mounts/artifacts/logs; runner cannot reach gateway admin or secret roots.
8. Save report with exact commit/image/client versions, Actions URLs, live/synthetic results, remaining risks, measured authored LOC, spike effort and full-product estimate. Stop only own ephemeral runner/gateway/broker containers and revoke per-run capabilities; retain evidence and source.

## Meaningful checks

Tests must fail for a real observable regression: forged/expired/wrong repo/workflow OIDC, capability expiry/revocation, wrong model/provider, missing auth, cross-key scope, body limit, bounded in-flight requests, stream tool call and failure/truncation/cancellation. Test boundaries rather than source-text snapshots. No blind retries after ambiguous provider dispatch.

## Boundaries

This is a standalone spike, not website/vault migration, customer workflow rollout, release or proof of universal model compatibility. Existing Codex subscription pool remains unchanged. Self-hosted Actions proves runner isolation and real GitHub OIDC but does not prove internet-facing TLS ingress or the SaaS UI flow. Production design needs existing OIDC integration, workspace key custody/rotation, per-run limits, audited metadata, dual-mode workflows, revocation and migration of old repo secrets after a successful canary.

Actual isolated hosting scope: review-router-gateway-spike/poc-20260930, separate controller and registry. Review roles use gpt-6.1-sol; no Astra under updated owner instructions.
