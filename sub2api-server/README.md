# Server wiring w1 handoff

Delivered scope: `sub2api-spike/serve.mjs`, `sub2api-spike/serve.test.mjs`, and this evidence directory. Shared customer authority/provenance, AdminAPI implementation, broker and OIDC sources were not edited. No dependencies added.

`boot(config, { brokerPort, customerPort })` now passes `customer.installation` to the actual shared AdminAPI and `customer.quarantineTemplates` to the actual shared customerAdapter. Server-only `requireProbeInstallation` and template map structure validation run before broker construction, ledger effects, or listeners. Template DTO and ownership validation remain in the existing adapter/AdminAPI; boot does not contact the engine to certify templates. Customer adapter initialization/recovery and synthetic control-server validation finish before broker construction. Pre-broker authority revocations are retained until broker construction; existing suspension/revocation policy is preserved.

Production CLI ports remain 8787/8788 and broker binding remains unchanged. Customer control binding rejects missing and wildcard hosts; the existing synthetic-only authentication gate remains mandatory. Importing the module no longer reads CLI configuration or starts servers. Boot returns the actual listeners and an awaited shutdown function. Startup listen failures close both servers; SIGINT/SIGTERM use that shutdown function.

The configuration is an operator-custodied server-only input. A well-formed installation declaration is not independent authentication of the installed engine. Root-only config custody, patched-image provenance, private control-network topology and actual engine behavior remain operator responsibilities. No production SSO is introduced.

## Evidence and verification

- `before.tap`: observed pre-fix regression, 0/1 pass. Import failed with ERR_INVALID_ARG_TYPE because module-top startup read an absent CLI config path. Original serve source SHA256: `749cd722f800661c89cb73f0ada8566fd395495d9e14e3fc48f94a0a52105f24`.
- `offline.tap`: 3/3 passed after fix. Actual boot rejects invalid installation without any HTTP listen invocation, customer state file or broker ledger/lock. Malformed template structures, wildcard bindings, invalid customer state and synthetic-auth initialization failure reject before broker ledger/listen effects. Import succeeds without startup.
- `adapter-offline.tap`: 18/18 existing offline shared adapter regressions passed. These verify independent ownership/group/probe-policy behaviors without replacing authority logic.
- Both edited JS files passed `node --check`.
- `socket-attempt.partial.tap`: incomplete attempt at the full server suite. Sandbox policy blocked local/private network access to 127.0.0.1. It contains only the first three successful tests and is NOT a full-suite pass.

Commands executed successfully:

```sh
node --check sub2api-spike/serve.mjs
node --check sub2api-spike/serve.test.mjs
node --test --test-reporter=tap --test-name-pattern='server import|invalid installation|malformed templates' sub2api-spike/serve.test.mjs
node --test --test-reporter=tap --test-name-pattern='offline' sub2api-spike/customer.test.mjs
```

Delivered socket tests use actual boot, actual AdminAPI HTTP transport and a disposable synthetic stock-shaped admin fixture. They check configured template GET/duplicate, server-only credential/flag retention and public projections, update retention, both-listener shutdown/port reuse, and customer-bind failure rollback. They are **NOT RUN to completion** here because the sandbox denied loopback network access. Their failure modes before this change are import-time startup, missing AdminAPI installation/template propagation, broker ledger creation before customer validation, and incomplete customer shutdown. Only the import failure has an observed pre-fix execution; no other red results are claimed.

Coordinator verification command in an authorized disposable sandbox:

```sh
node --test --test-reporter=tap sub2api-spike/serve.test.mjs
```

**NOT RUN:** stock Go gates, Docker/patched-image integration, real admin/engine roundtrip, live provider gates, root config custody and production operations. No external gates were waited for or polled. No live receipts or metrics are claimed. Local synthetic tests cannot establish stock engine transaction semantics or patched-image authenticity.

Git lock preflight was attempted once: the linked gitdir and its index.lock could not be accessed (git status reported the gitdir was not a repository; index.lock inspection reported no such path). Lock absence is therefore not verified. No bypass, git add/commit/push, credentials/auth-home access, root, Docker, external network or live provider operations were performed. The source diff is left for the project controller; shared-source SHA256 values match the initial observed values.

`source-sha256.txt` records final edited-source and untouched shared-source hashes. Remaining risk: socket behavior and external installation gates need coordinator verification; broker constructor internals/cleanup were deliberately left outside this lane.

## Server wiring w2 handoff

SR1 broker initialization cleanup is now corrected in `sub2api-spike/broker.mjs`; actual filesystem regressions were added in `sub2api-spike/broker.test.mjs`. The w1 wiring and existing socket cases remain byte-identical. Current evidence, exact artifacts, pre-fix failures and external NOT RUN limitations are in [W2-REPORT.md](W2-REPORT.md); [w2.patch](w2.patch) contains only the two broker-file changes. The w1 broker-out-of-scope statement and hashes above are historical, not the current w2 state. No external operator gates were waited for. Coordinator owns integration and any mixed-index normalization after worker stop.
