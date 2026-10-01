# BR04 bounded provenance implementation

The owned contribution is implemented. Full normalized Actions evidence binding remains an integration gate: caller/workflow files were left untouched for their owner. No external E2E or canary approval is claimed.

Read BR04 in `sub2api-boundary-review/REPORT.md`. It identifies untrusted normalized runtime run/attempt being printed without comparison to the signed OIDC authorization. The thin contract now makes that comparison possible without introducing another platform, translation layer, dependency or provider key.

## Plan and resulting contract

1. Preserve the signed RS256 verifier and immutable configured workflow policy. Return the already validated signed `workflow_sha` as `workflowSHA`, alongside canonical string `runID`/`attempt` and expiry.
2. Reject missing/malformed verified identity before body admission, workspace resolution, issuance ledger mutation or capability generation. Snapshot the verified claims and resolve provider/protocol through the selected configured scope. Grant request bodies still permit only provider/protocol, so caller-supplied run metadata is denied.
3. Store the original authorized identity with the in-memory grant. Add `runID`, `attempt`, `workflowSHA`, `provider`, `protocol` to the existing capability/model/expires response. Cached responses project that stored identity; a fresh token does not replace identity or extend cached expiry. Run replay, revocation, request limits and ledger schema remain intact.
4. Provide `bindGrantedRun(grant,runtime)` for the trusted caller. Require exact string run/attempt/workflowSHA matches and the supported provider/agent native protocol selection before execution. Return a frozen five-field identity receipt; never return capabilities, tokens, model or expiry. MiMo/Codex Responses, MiMo/Claude Messages and OpenRouter/Codex Responses are accepted; other combinations deny.
5. Test actual signed OIDC and the binder offline, add real HTTP broker-to-binder assertions and fail-closed synthetic verifier contract tests, preserve existing native financial assertions, and hand caller/workflow integration to the coordinator.

Only the assigned six source/test files and `sub2api-provenance/` changed. Source changes total 95 added/removed lines, below the 250-line bound. Existing synthetic fixtures already use the actual signed test verifier with the new valid contract; the new synthetic contract-denial test derives its good claims from that real signed verifier. No source-grep or mirrored verifier mock is used as proof.

## Evidence and verification limits

PASS: `node --test sub2api-spike/oidc.test.mjs sub2api-spike/granted-run.test.mjs sub2api-spike/evidence.test.mjs` under Node v24.21.0, 8/8. This proves policy-bound signed workflow identity, numeric signed attempt normalization, immutable-claim rejection, exact runtime binding, supported agent selections, positive-only receipt projection and existing native/financial evidence behavior. Existing malformed/fabricated financial success and UTF-8/native terminal rejection assertions are retained and pass.

PASS: `node --check sub2api-spike/broker.mjs` and `node --check sub2api-spike/broker.test.mjs`. An initial syntax error from a misplaced inline comment was corrected before these checks and offline tests.

NOT RUN: full HTTP/socket suite. The actual attempt `node --test sub2api-spike/oidc.test.mjs sub2api-spike/granted-run.test.mjs sub2api-spike/broker.test.mjs` was rejected by the sandbox with `Network access to "127.0.0.1" was blocked: local/private network addresses are blocked by the sandbox policy.` No HTTP assertion result is claimed. Coordinator must run the full suite in its pinned Node24 disposable environment.

The added HTTP tests exercise actual signed tokens through `/grant`, deny spoofed body metadata and missing/mismatched signed claims before ledger issuance, bind exact accepted provenance, reject runtime spoofing, retain byte-equivalent cached grant responses despite changed token expiry, deny attempt/provider-protocol rescope and revoke replay, and count zero upstream inference effects. A malformed injected verifier contract denies before even workspace resolution; an intentionally changed valid-shaped verifier identity cannot overwrite cached authorization. Existing active-stream expiry/revocation tests now also assert grant replay denial. These are authored assertions pending socket execution, not evidence of their passing.

NOT RUN: Docker, root/UID changes, network/provider access, live inference, credentials, auth-home access or genuine Actions execution. Broker startup still writes the existing empty ledger/lock; the zero-ledger-effects assertion refers specifically to grant issuance, not removal of startup persistence. Production authenticity depends on the configured real `sub2OIDCVerifier`, not arbitrary injected verifier functions.

## Exact patch and handoff

Source patch: `sub2api-provenance/source.patch`.
SHA-256: `b24c8297f52fac03fa47c91febba095bfd624791145e1354ec832c791fc50b14`.
`worker-result.json` records each current source file hash and the patch line counts. Patch contains only the six owned source/test changes, including both new modules. It was constructed against the source state inspected at turn start; Git diff is unavailable because the linked worktree points to inaccessible/missing Git metadata. No staging, commit or push occurred.

`integration-snippet.md` supplies coordinator-only imports, immediate post-grant binding, verified-field receipt construction, and workflow checks of run/attempt/workflow/provider/agent/transport. Install the binder in the fixed sealed trusted harness/module manifest. Preserve all existing actual tool reads, native transport/terminal checks, financial findings and independent numerical reproduction. No fabricated answer or raw token-bearing evidence is permitted.

Completion audit: verifier and grant additive contracts implemented; binder and positive receipt implemented; offline signed/native tests verified; actual HTTP assertions supplied but execution pending; caller/workflow integration snippet delivered with caller files unchanged. The bounded contribution is ready for integration. Overall goal remains active until coordinator integration and the required external verification prove normalized E2E receipts are actually bound before agent execution.

## Continuation completion audit

Re-inspected current artifacts and source. All six source hashes and the exact source-patch hash still match the delivered contribution. The current `run-client.mjs` does not import or call the binder and still builds receipt run/attempt/workflow fields from environment values; the current workflow uploads evidence without the requested receipt identity checks. Thus the full goal is demonstrably incomplete in this worktree, rather than merely lacking an E2E result. No caller/workflow changes were made because their ownership restriction remains in force. No socket-policy bypass, Docker execution or external inference was attempted. Further integration and socket verification require coordinator-owned actions; the goal remains active.

## Blocked audit

The same coordinator-owned integration and verification boundary remains after three consecutive goal turns. Reinspection confirms the caller still has no binder invocation and the workflow still uploads without requested identity validation. The owned bounded implementation and handoff are complete; no meaningful authorized source work remains here. Mark the full goal blocked until coordinator integration and permitted HTTP/E2E verification provide new authoritative evidence.

## Coordinator fixture repair

Pre-existing hard-coded inert Bearer assertions triggered the normal handoff scanner when broker.test.mjs changed. Expected authorization now derives from the explicit synthetic rig configuration, preserving assertions. Original authored files and patch are retained immutably. The scanner remains enabled; new source.patch/hash bindings supersede worker hashes for this isolated test repair. Full socket checks must rerun before capture.

The redundant nested source.patch is retained privately, not published: its deleted baseline synthetic fixture text trips the raw-file scanner. The normal runtime exact handoff patch is authoritative, with all normal patch/blob secret validation enabled. Actual full socket suite PASS 49/49 on pinned Node24.

Final fixture resolution: keep original broker.test.mjs byte-for-byte and place additive BR04 HTTP cases in grant-provenance.test.mjs. The scanner checks old blobs too; no baseline synthetic literals are exported by modifying that file. No old tests or assertions were removed. Normal exact handoff scanner remains enabled.
