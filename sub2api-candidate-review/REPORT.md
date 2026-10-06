# Independent final candidate review

The consumer glue is approved for integration into the exclusive disposable sandbox source. The exact native candidate requires one focused correction, R3, before source approval. Neither decision claims a deployed native canary or completed consumer/native end-to-end integration. External operator gates are limitations; this review is finished without waiting for them.

## R3 — P2: initial HTTP cleanup deletes an opaque reference namespace

At `backend/internal/service/openai_responses_namespace.go:223–225`, the new preservation exemption covers `reasoning` but omits `item_reference`. `Forward` calls this helper at `openai_gateway_forward.go:130` before selecting normal or passthrough HTTP forwarding. An item reference is also outside the tool-call namespace allowlist, so its `namespace` is deleted with the trusted preservation flag enabled.

Reproducible input for an OpenAI API-key account with boolean `openai_preserve_compatible_reasoning:true`:

```json
{"model":"mimo-v2.6-pro","stream":false,"store":true,"input":[{"type":"item_reference","id":"rs_provider","namespace":{"provider":"opaque"},"extension":9007199254740993}]}
```

Both HTTP modes remove `input[0].namespace` before the first upstream request. This violates the requested complete opaque reasoning/reference preservation invariant. The R1 repair comparison snapshots already normalized input, so it cannot detect this earlier mutation. Existing namespace coverage checks reasoning and ordinary messages; its reference fixture has no namespace.

Minimal fix: extend the preservation exemption to `item_reference`, using the same type normalization as the opaque-item guard. Keep ordinary and default namespace cleanup enabled. The supplied [independent_reference_namespace_test.go](independent_reference_namespace_test.go) exercises real `Forward` with the existing recorder in both HTTP modes and both policy states; it also compares the whole reference through `UseNumber` and retains ordinary cleanup controls. Copy it into the coordinator's exact disposable patched `backend/internal/service` tree and run:

```sh
go test -tags unit ./internal/service -run '^TestIndependentCompatibleReferenceNamespaceHTTP$' -count=1
```

That command is a prescription, **NOT RUN** by this reviewer: Go and socket execution were explicitly prohibited. R3 is established by the reachable source branch and unconditional deletion, not presented as a measured Go failure. It is an API-key candidate defect, independent of unrelated product OAuth adoption.

## Scope A: exact native identity and R1/R2 closure

Reviewed all 1,208 changed lines across all 16 files, including the authored tests and the relevant original caller/helper context. The original pin is `96f4c115c9749078f90cbf210a01d39baf3f53b6`. The reviewed patch SHA-256 is:

`432cffdf3b2a2659da76403242942b45177d69f60fda17efd14605d7798e7135`

Applied the frozen patch to copies of its touched originals under this review directory. All 12 original and 16 patched file hashes match `native/SOURCE.json`; 1,153 additions plus 55 removals match the full stated scope. Full exact file identities are in [reviewed-source-hashes.json](reviewed-source-hashes.json) and [native-hash-verification.json](native-hash-verification.json). Inputs were not changed.

R1's repair defect is closed in source: normal HTTP, passthrough HTTP, native WS ingress and HTTP bridge all use the account-aware proposal comparator before consuming retry budget. The strict `UseNumber` comparison covers complete reasoning and reference items by input index, including null/plain content, status/cache/extensions and exact numeric representations. A protected mutation returns the sentinel and an original semantic rejection through a terminal path; ordinary field repairs and default behavior remain available. Existing invalid-cipher replay/lineage recovery is excluded by the account policy, with HTTP/WS/SSE rejection handling retained. R3 is a separate initial-normalization gap, not evidence that the R1 comparator itself is ineffective.

R2's empty-image defect is closed in source: the strict `UseNumber` decoder avoids float rounding, and traversal exempts complete reasoning/reference items while ordinary empty images are still removed. The common HTTP and passthrough callers pass the account policy. Strict trusted boolean policy, API-key/native Responses scope and OAuth/default controls remain. No additional concrete new header or runtime safety defect was identified in the bounded inspection; existing filtered response-header handling remains in use.

The frozen coordinator receipt proves 287 passing records on pre-format patch `e115263fcf343e5abf2676cda339bfc3d6ea94df6170e91f5c4ff5a568bb4c3d`, against 75 failed baseline records and 212 passes without compilation failure. The format receipt identifies only the newly authored repair test as reformatted, with production bytes unchanged. It explicitly says the formatted behavior gate was not run in that snapshot. The user's separate final exact-432 gate is therefore pending evidence, not represented as completed by this review.

## Scope B: consumer glue and concrete risk inspection

No additional source blocker was found in the bounded consumer review. Inspected SQL generation/ownership, template versus Copy identity, preparation/duplicate/promotion/read policy enforcement, replacement compensation, asynchronous workspace/group/template/credential checks, grant binding, workflow receipt identity, import sealing and UID/output boundaries.

BR02 enforces an immutable server installation capability snapshot and boolean capability-probe suppression on prepared, copied, promoted and owned OpenAI DTOs. Missing installation or dropped policy fails closed. The capability JSON is a trusted configuration requirement; it does not authenticate a deployed image.

BR04 binds the grant in the actual caller before home/version/agent effects. Claimed identity is an immutable projection, while the workflow checks run, attempt, workflow SHA, provider, agent and protocol before publication. High reasoning and genuine financial/tool/terminal/numeric checks remain. The fixed root manifest must include the binder and transitive imports before Node starts; runtime path checks are additional enforcement, not independent proof of installed custody.

BR05 seeds six inactive, unschedulable, ungrouped synthetic templates in a transaction with table locks and an owner-based no-retry guard. Cleanup requires exact IDs, scope/platform/type, owner, inert state and zero group associations before deleting. Inspection found no concrete SQL seeding or extra replacement ownership escape. The generated psql meta-command was independently checked and is correct. Neither seed nor cleanup SQL was executed against PostgreSQL. The roundtrip requires independently observed cumulative effects and a drain acknowledgement; unavailable telemetry remains null.

Independent Node 24 contracts executed with no network or agent effects: **3 passed, 0 failed**. They exercise immutable grant binding with mismatches, strict installation snapshot behavior, and the generated SQL output contract. See [independent-contracts.test.mjs](independent-contracts.test.mjs) and [independent-contracts.tap](independent-contracts.tap). These tests do not replace the root's broader gates.

The frozen actual HTTP receipt records exit 0; the user reports 93/93 HTTP/socket contracts. The frozen receipt does not include the raw log or count, so 93/93 remains attributed to the root report. The actual stock probe-only receipt contains eight PASS results and zero synthetic provider requests; the real PostgreSQL capability-field audit records zero observed updates/false writes. Those gates bind the approved capability suppression component, not a deployed reasoning-432 integration.

All 117 selected frozen consumer/coordinator/native manifest hashes matched. Full source hashes, including the binder and transitive consumer runtime files, are recorded in [reviewed-source-hashes.json](reviewed-source-hashes.json); manifest checks are in [input-hash-verification.json](input-hash-verification.json).

## Mandatory integration and native-canary gates

1. Fix R3, run the independent reference regression, retain the unchanged independent R1/R2 prescription, and obtain the exact final pinned native gate on the resulting artifact.
2. Deploy and identify the approved reasoning and capability suppression components together in the exclusive disposable engine.
3. Wire server installation and quarantine templates through `serve.mjs`; install the independent observer `/snapshot` and `/drain` implementation. The frozen server lacks this wiring and the observer is external/unimplemented.
4. Execute stopped-engine template seeding and guarded cleanup against pinned PostgreSQL, then actual STOCK-consumer integration with the corrected normal-template/Copy identity oracles, counted transport attempts, capability-field audit and delayed-work drain.
5. Verify fixed installed manifest/image custody including the binder and transitive imports, UID/FD/descendant containment, then run the genuine native financial canary with preserved high reasoning and genuine tool/terminal/numeric evidence.

These are mandatory evidence gates for integrated/runtime approval, not work this reviewer waited for. Product OAuth adoption is a separate lane and does not block the API-key source candidate for unrelated unimplemented features.

## Handoff

Only `sub2api-candidate-review/` was written. It contains the review JSON/report, exact source/hash evidence, a partial exact native materialization for path/line review, three passing independent Node contracts, and an unexecuted Go regression prescription. No candidate source was repaired, no Git changes were staged/committed/pushed, and no root, Docker, Go, network, provider, auth-home or credential operations were run. The native materialization includes only the 16 touched files and is not a complete build tree. Review deliverables are complete; R3 and external integration/runtime gates remain explicit.
