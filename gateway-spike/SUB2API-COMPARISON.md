# Sub2API comparison for ReviewRouter

Research date: 2026-09-30. Read-only source/documentation review; no Sub2API deployment, credential import, agent launch or inference call was performed.

## Version and evidence boundary

Latest release checked through gh CLI: **v0.2.11**, published 2026-09-30 07:06:51 UTC, commit **96f4c115c9749078f90cbf210a01d39baf3f53b6**. Inspected main **42bc7f6cffe24bcb471608e48e66b4a0afa1f882**. GitHub compare confirms main is one commit ahead and only backend/cmd/server/VERSION differs, so the examined runtime/UI code matches this release.

This is source evidence. Bifrost has our three successful live Actions canaries; Sub2API has not yet passed those same canaries in our environment. Repository popularity and presence of tests are not measured availability or security evidence.

## Conclusion

Sub2API is a credible candidate when our scope includes multiple subscription account providers. It already implements account onboarding, OAuth refresh, scheduling, per-user/per-account concurrency, usage/billing and an operator dashboard. It could supply more of the subscription-pool machinery than the Bifrost BYOK spike.

It does not remove ReviewRouter's workspace/repository ownership, CI OIDC authorization, scoped run grants or workflow/batch setup. Its public API key is a platform credential, not the upstream master credential, but putting a permanent platform key into every repository would still expose durable access to the pool. Preserve the temporary per-run broker boundary regardless of gateway choice.

## Provider and agent support

| Requirement | Observed implementation | Assessment |
|---|---|---|
| OpenAI/Codex subscription | OpenAI admin OAuth routes and OpenAITokenProvider refresh/cache/error handling | Built-in account lifecycle exists; our pool migration still needs a separate canary. |
| Claude subscription | Anthropic account OAuth/setup-token routes; native Messages gateway | Built-in onboarding exists. Provider subscription permission and upstream behavior remain external dependencies. |
| Gemini / Antigravity / Grok | Separate admin OAuth routes and gateway profiles | Already supported families; not every arbitrary provider has a connector. |
| OpenRouter API key | Generic platform=openai, type=apikey, credentials.base_url plus Responses URL builder | Candidate base_url=https://openrouter.ai/api/v1. Force native Responses, review passthrough policy and model/pricing configuration. No dedicated OpenRouter account/quota connector found. |
| MiMo Token Plan | Same generic OpenAI-compatible key/base URL path; separate generic Anthropic key/base URL path | Candidate Responses base_url=https://token-plan-sgp.xiaomimimo.com/v1 and Anthropic base_url=https://token-plan-sgp.xiaomimimo.com/anthropic. No dedicated MiMo provider or Token Plan quota connector found. |

A MiMo model name in OpenCode Go's model list represents access through OpenCode, not direct MiMo Token Plan support. The platform constants enumerate anthropic/openai/gemini/antigravity/grok/kimi/zhipu/deepseek/minimax/opencode_go; neither mimo nor openrouter is a dedicated platform.

OpenRouter and MiMo connectivity is an inference from the generic code and official native protocol documentation, not a live proof. Both providers supported actual Codex review through our separate Bifrost spike.

## What the dashboard can and cannot give us

Upstream accounts and OAuth onboarding are registered under /api/v1/admin and guarded by AdminAuth. The admin middleware accepts an admin API key or a JWT whose user has the administrator role. Account CRUD, exports, refresh and OAuth exchanges are admin operations.

The normal user panel can manage Sub2API access keys, view available groups, usage and platform subscription/balance. Its /user/account-bindings routes bind login identities; they do not let an ordinary user add their own upstream Claude/Codex account.

The upstream Account schema has groups, proxy, scheduling/quota metadata and credentials, but no workspace or owning user field. Groups expose access to allowed users; they are not an ownership model for customers editing their own provider accounts. Our app can maintain that ownership and strictly filter server-to-server admin calls, but must enforce it on every list/read/create/update/delete/refresh/export operation. Never give customers a shared Sub2API administrator token.

The UI is Vue, while ReviewRouter's UI is React/Next.js. SSO can help login (Sub2API has OIDC login), but does not create workspace resource authorization. That OIDC login flow is also distinct from verifying GitHub Actions job claims. Embedding the shared admin page with iframe does not solve either permission problem. A separate Sub2API instance per workspace is another isolation approach, with deployment/migration/backup cost for every instance.

## Concrete limitations relevant to our design

1. **Credential storage:** account_repo.go writes normalized credentials directly into JSONB and queries values such as api_key/refresh_token with SQL operators. The reviewed account write path does not apply application-layer encryption. The AES encryptor uses the TOTP encryption key and does not establish encrypted upstream account storage. Disk/database encryption can be supplied by deployment, but should not be confused with a per-credential vault. Rotation, exports, backups and scheduler caches belong in the custody review.
2. **Gateway compatibility:** Responses support is probed and can be overridden with openai_responses_mode=force_responses. openai_passthrough is off by default; the gateway has model/tool/payload normalization, cross-protocol bridges and failover. Even passthrough has policy handling. Configure native paths and validate exact errors/tool identity/cancellation instead of assuming an unchanged stream.
3. **Outbound URL policy:** the example config has URL allowlist disabled, private hosts allowed and insecure HTTP allowed. Those defaults suit trusted operator configuration; customer-supplied URLs require a strict provider catalog/allowlist, private-network protection and HTTPS. Do not publish admin/config access to users.
4. **Account continuity:** switching upstream accounts can affect session/cache/encrypted reasoning state. Validate sticky sessions, concurrent OAuth refresh, quota exhaustion, failover and revoked sessions for the subscription adapter. Ready account connectors reduce our implementation, but do not make provider sessions permanent.
5. **Product overlap:** Sub2API brings its own users, API keys, groups, subscriptions, billing and payment UI. Choose one authoritative workspace/billing model and explicitly map the other. Running PostgreSQL + Redis is also a new operational dependency.
6. **Upstream/OSS conditions:** project README explicitly warns about upstream service terms and revoked/banned accounts. LICENSE is LGPL-3.0-or-later; README also includes a No Commercial Authorization notice. This report makes no legal conclusion about commercial rights; direct frontend reuse/distribution and the notice need their own license review if adopted.

## Architecture choices

The following figures are planning judgments, not benchmark results. LOC refers to our production integration code, excluding tests, config/docs and vendored OSS; ranges require a product source audit.

| Choice | Confidence | Expected reliability | Complexity | Rough production LOC |
|---|---:|---:|---:|---:|
| Private Sub2API gateway/account engine + our UI, ownership and OIDC broker | 8/10 | 6/10 | 7/10 | 2,500-4,500 |
| Bifrost BYOK + preserve the existing Codex subscription pool | 9/10 | 7/10 | 6/10 | 2,200-3,300 |
| Fork/extend Sub2API admin into customer workspace account management and embed/reuse it | 5/10 | 5/10 | 9/10 | 4,500-8,000 |

For the present MiMo/OpenRouter delivery, Bifrost has stronger direct evidence. For adding many subscription providers, evaluate private Sub2API as a replacement engine before writing new OAuth connectors. Do not initially replace the working Codex pool or expose the admin UI to customers.

## Bounded next spike

Reuse the existing disposable repository and create an isolated Sub2API deployment pinned to the release image digest. Do not connect production accounts or change the existing pool. Use the same fixture, success validator, temporary OIDC capability and complete custody scan.

1. Codex -> native MiMo Responses, with an existing authorized test key supplied only server-side.
2. Codex -> native OpenRouter Responses, with explicit model selection and no implicit model fallback.
3. Claude Code -> native MiMo Messages, successful Read evidence and correct finding.
4. Synthetic Responses failed/truncated/tool-call cases; unauthorized/admin path denial; capability expiry/replay/revocation; upstream master-key absence from the complete runner/log/artifact surfaces.
5. Two explicitly test workspaces: unauthorized account list/read/edit/delete/refresh must be denied by the integration boundary.
6. If considering a subscription-pool migration, add a separate owner-authorized test subscription identity for OAuth refresh, session affinity, concurrency and failover. Do not import the production pool during this comparison.

Estimated new spike effort: **4-8 engineering hours** for three key-based canaries with prepared host/keys, plus **4-8 hours** for a meaningful subscription lifecycle lane if an explicit test identity is available. Roughly **250-600 new production spike lines + 150-350 meaningful test lines**, reusing the previous broker/client/evidence code. This is a provisional estimate, not work already executed.

## Primary sources

- [Release v0.2.11](https://github.com/Wei-Shaw/sub2api/releases/tag/v0.2.11).
- [Pinned README](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/README.md).
- [Provider constants](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/domain/constants.go).
- [Admin routes and account onboarding](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/server/routes/admin.go).
- [Ordinary user routes](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/server/routes/user.go).
- [Account storage](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/repository/account_repo.go).
- [Account schema](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/ent/schema/account.go).
- [Native Responses forwarding](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/service/openai_gateway_forward.go).
- [Responses capability/mode](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/backend/internal/pkg/openai_compat/upstream_capability.go).
- [Deployment policy examples](https://github.com/Wei-Shaw/sub2api/blob/96f4c115c9749078f90cbf210a01d39baf3f53b6/deploy/config.example.yaml).
- [MiMo native Codex configuration](https://mimo.mi.com/docs/en-US/tokenplan/integration/codex-configuration).
- [MiMo native Claude configuration](https://mimo.mi.com/docs/en-US/tokenplan/integration/claudecode).
- [OpenRouter Responses endpoint](https://openrouter.ai/docs/api/api-reference/responses/create-responses).
