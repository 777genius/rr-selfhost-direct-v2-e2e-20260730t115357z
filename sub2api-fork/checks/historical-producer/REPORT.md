# Exact frozen patch review

**Strict canary: NO-GO for this exact proposal. Production GO: not claimed.** Two reachable branches still mutate provider-owned opaque reasoning. This bounded independent review is complete; corrections and new evidence belong to the producer/coordinator.

Reviewed upstream revision `96f4c115c9749078f90cbf210a01d39baf3f53b6`, patch SHA-256 `4d19a886a346e3d0dbf80b515d12d640a07fc36994f26d3dbddb9245e78f3357`. SOURCE.json SHA-256 `8b62f28c630f5942bd5615e28c64ea8299886006a20727a527f9c0bcd6fe9b2c`. Locations below use **patched repository-relative line numbers**; unchanged context files use staged upstream line numbers.

## Actionable blockers

### F1 — P1: ciphertext recovery bypasses preservation policy

`backend/internal/service/openai_gateway_forward.go:1121` still handles HTTP 400 `invalid_encrypted_content` on opted-in non-passthrough native API-key accounts by trimming encrypted reasoning, recording lineage and retrying. The helper at `backend/internal/service/openai_gateway_request_body.go:428` deletes `encrypted_content`; it processes all encrypted reasoning, not just one identified bad item. Later matching history is stripped at `openai_gateway_forward.go:754`. WS recovery at `openai_gateway_forward.go:850` and WS ingress at `backend/internal/service/openai_ws_forwarder_ingress.go:605` and `:1478` likewise lack the trusted preservation gate.

**Proven by inspected control flow:** the exact proposal leaves these inherited branches reachable. This contradicts the frozen README's claim that encrypted reasoning passes intact as provider-owned opaque history. Initial successful request tests do not cover it. No actual provider rejection or local behavioral reproduction was executed; whether the real provider emits that error remains external.

**Minimal remedy:** exempt opted-in accounts from ciphertext mutation, lineage recording and pre-stripping at all HTTP/WS boundaries; expose the original provider rejection. Preserve existing default/OpenAI/OAuth recovery. Add a real Forward/transport-recorder case returning that 400: original error, one upstream request, unchanged ciphertext, no lineage record. Also seed matching lineage and assert unchanged first outbound history; cover actual WS preparation/recovery. Keep policy=false recovery assertions.

### F2 — P2: later WS/image normalization corrupts opaque numeric history

`backend/internal/service/openai_gateway_request_body.go:1540` uses ordinary `json.Unmarshal` into `map[string]any`, and `:1544` marshals the whole request when image tools change. Supply the existing reasoning fixture (opaque integer `9007199254740993`) with `tools:[{"type":"image_generation","format":"png"}]`. The predicate in `backend/internal/service/image_generation_intent.go:283` selects the branch; migration at `backend/internal/service/openai_codex_transform.go:899` returns changed. Go float64 decoding then serializes that opaque number as `9007199254740992`. Real HTTP passthrough also invokes this function at `backend/internal/service/openai_gateway_passthrough.go:216`.

**Proven by control flow and standard Go JSON semantics; executable boundary test still needed.** The added fixture already checks this exact integer, but its requests contain no image normalization trigger. The green therefore does not prove numeric preservation on this reachable branch.

**Minimal remedy:** use the existing `decodeOpenAIJSONUseNumber` here, with no new dependency. Add real WS compatibility and HTTP Forward/passthrough cases using the legacy image fields; assert tool migration plus unchanged reasoning numeric Raw, content, ciphertext, IDs, references and call pairing. Use raw field edits if preservation must include lexical JSON fidelity.

## Other focused observations

At `backend/internal/service/openai_gateway_forward.go:130`, the earlier namespace sanitizer can delete a top-level `namespace` extension from opted-in reasoning; the raw WS compatibility helper retains it. This rewrite is proven, but provider use of that field is unverified. Treat it as a test-needed extension contract issue, not a third blocker: add an extension fixture and preserve opted-in reasoning while sanitizing other item namespaces.

`backend/internal/service/openai_compatible_reasoning_policy_test.go:54` asserts relative tool order and relative reasoning order separately. It does not fully assert their interleaving. Strengthen the actual outbound input sequence oracle to preserve association, accounting for intended message sanitation. No reordered history defect was found in the changed sanitizer itself.

## What the evidence establishes

Independently computed the patch hash, all four original file hashes and all five reconstructed patched hashes against SOURCE.json. Applied with `patch --batch --fuzz=0 -p1`, with no offsets/fuzz reported; reversed it and confirmed every original hash plus removal of the new test. Temporary reconstruction was removed. Exact hashes and outputs are in `verification.json` and `review.json`.

The supplied coordinator official-archive comparison is accepted as task-provided provenance. No network re-fetch occurred. The earlier producer files saying pin/red-green NOT VERIFIED/NOT RUN are historical, superseded for those checks by the task-provided coordinator evidence; the staged VERSION mismatch is not independently treated as a current blocker.

Receipt `.spike-inputs/candidate/coordinator-red-green.json`, SHA-256 `771e262d486a0b4eab400958798987f6c1fbe88238d2dd1d891e534d73e0db33`, consistently binds both cases to this revision and patch. It records red exit 1 without compilation failure, green exit 0, network `none`, and toolchain `golang:1.27.1-alpine@sha256:8a5910f31396cd4d89662f56c68b3ae31d374308270a1c3bd96672ee5ed43414`. The nine FAIL records include two parent test records and seven named leaf cases; the summary alone does not expose nine individual assertion messages. The user-supplied same-tests/pinned-toolchain attestation is accepted; raw logs/archive/command are absent from this receipt, so this reviewer did not independently execute or attest them.

Tests call real Forward and capture its actual outbound request with the existing in-memory transport recorder; WS tests call real compatibility and bridge preparation. They do not mirror normalization. The synthetic HTTP responses deliberately contain empty output, so their green proves request history handling for covered inputs, not a real model answer. OAuth equality tests establish unchanged preparation relative to the unflagged account, not live OAuth validity. Route-scope tests exercise preparation rather than actual forced-CC outbound forwarding.

## Satisfied boundaries and limits

The policy reads only a strict boolean from trusted Account.Extra, requires exact platform=openai/type=apikey and the native Responses route predicate, and does not read caller body/header/query policy fields. Query caller authority over Extra is excluded by the supplied task boundary, not audited through administrative handlers. Missing/false/string metadata and OAuth/setup-token remain on legacy behavior. Forced Chat Completions and a negative Responses probe disable the flag, consistently with the forwarding predicate. Other platforms do not gain the policy.

The reasoning-aware sanitizer retains raw reasoning and its IDs; unconstrained item_reference IDs survive. Non-reasoning ID/call_id handling is unchanged. Initial native HTTP and first/subsequent WS response.create preparation use the same account policy. Opt-in sanitation validates complete JSON, UTF-8 and object root before its own input processing; semantic item shapes remain provider validation. No dependency, model/protocol switch or response-stream change was added. Ordinary decoded HTTP and bridge paths use UseNumber; text truncation hooks are no-ops in this pinned tree.

Local Go/gofmt are unavailable; no new Go execution was attempted, and the two new reproduction prescriptions are not claimed as observed red/green. No Docker/root/network/live inference, credentials/auth homes, production identity access or Git writes occurred. Reads were limited to the four production files, added tests and directly relevant call-site/helper/receipt context. Only review artifacts were left under `sub2api-fork-review/`; no production source was edited.

After correcting and freezing the replacement patch, rerun pinned offline red/green plus the finding-specific boundary cases, then review/build one immutable engine with source/patch/image digests. External coordinator gates remain: authorized disposable native thinking-enabled Codex+MiMo canary with a genuine nonempty final answer satisfying the strict financial contract, same-image Codex+OpenRouter and Claude+MiMo regressions, custody/tenant isolation, rollback and teardown evidence. `response.completed` alone is insufficient. This report authorizes neither a canary on the defective exact patch nor production deployment.
