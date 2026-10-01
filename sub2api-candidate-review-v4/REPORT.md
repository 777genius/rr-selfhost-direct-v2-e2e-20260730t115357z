# Bounded independent R3 review

**APPROVE_FOR_DISPOSABLE_SANDBOX_SOURCE_INTEGRATION.** R3 is closed in the exact replacement `30cb1d6b5060cbf41b822fa46fc996fafd91acbc470d89bf2882be90eb24b4d5`. No concrete new defect was found in the bounded delta review. Replacement compilation, formatting and behavior are **NOT RUN** by this reviewer. The separately running root gate has no result asserted here. Integrated deployment and native canary approval remain unproven.

The canonical candidate-review-w3 REQUEST_CHANGES_R3 report and JSON are captured locally as `sub2api-candidate-review/REPORT.md` and `sub2api-candidate-review/review.json`. Both were read; their exact hashes are in [source-hashes.json](source-hashes.json). Its consumer source approval and accepted R1/R2 findings carry forward within their recorded scope. Consumer, probe and OAuth lanes were not reevaluated.

## Exact identity and minimal scope

Applied both `.spike-inputs/native/checks/rejected432.patch` and `.spike-inputs/native/patches/native-reasoning.patch` independently to frozen `.spike-inputs/upstream` originals in memory, with exact hunk context and line-count assertions. All 12 original hashes and 17 replacement hashes match `.spike-inputs/native/SOURCE.json`. The upstream revision is `96f4c115c9749078f90cbf210a01d39baf3f53b6`; archive custody is the frozen coordinator's assertion, not a fresh network authentication.

The replacement contains 1,196 additions and 55 removals, totaling 1,251 changed lines across 17 files. Applying the R3 delta to reconstructed reviewed432 produces byte-for-byte the same 17-file result. All 16 reconstructed reviewed432 files also match the canonical review's captured materialization. Every other 15 native files, including the four previous authored test files, are byte-identical to reviewed432.

Only `backend/internal/service/openai_responses_namespace.go` changes production behavior: one normalized type assignment and one exemption change. The other delta file is the byte-identical independent 42-line `backend/internal/service/independent_reference_namespace_test.go`, SHA-256 `5863f7d72bf5d31865f4a162c614895358fefdc042de9b6128f4d75021e9fa47`. Its original prescription is `sub2api-candidate-review/independent_reference_namespace_test.go`. The delta is 44 additions and one removal; its SHA-256 is `a638e61dfff17f140104b5ba14bb08fd9907dc8fc26191b0a172a85831dd648e`.

Exact source paths and all original/current/prior hashes are recorded in [source-hashes.json](source-hashes.json). No native source blobs or patches were copied into this review directory. [verify_sources.py](verify_sources.py) reproduces the artifact verification without persisting reconstructed sources.

## R3 closure and controls

At `backend/internal/service/openai_responses_namespace.go:220–225`, the exemption now recognizes both reasoning and item_reference using lowercased, trimmed type values, exactly matching the classification in the unchanged opaque repair comparator at `openai_responses_rejected_field_retry.go:57–59`. The existing trusted policy remains enforced at `account.go:1355–1360`: native OpenAI API-key Responses accounts and a strict boolean true. Caller `openai_gateway_forward.go:130` invokes the helper before selecting normal or passthrough HTTP.

Protected items are copied from their complete raw JSON item, including namespace, extensions and large numeric literals. Even when ordinary siblings force rebuilding the input array, those item blobs are written unchanged; no float decoding or selective protected-field reconstruction was introduced. The final raw input replacement preserves whole-item semantics without promising identical surrounding request whitespace.

Source branch controls were inspected, not executed as runtime tests:

| Input/control | Policy true | Policy false |
| --- | --- | --- |
| reasoning / item_reference | Complete item retained | Namespace cleanup retained |
| Mixed case and surrounding whitespace on either protected type | Same complete-item exemption as opaque comparator | Namespace cleanup retained |
| message, missing type, unknown type, reasoning suffix or reference suffix | Namespace removed | Namespace removed |
| Tool call with keepToolCallNamespaces enabled | Existing allowlist retained | Existing allowlist retained |
| Nested namespace / non-array input | Existing direct-input-only behavior retained | Existing behavior retained |

The unchanged ID sanitizer's exact lowercase reasoning exemption was also checked against these controls. Whitespace trims to the protected type; mixed-case protected types are outside its case-sensitive constrained-ID/non-pair-call cleanup branches and therefore are not stripped there. No concrete reachable case/whitespace defect was identified. This is a bounded source conclusion, not provider acceptance evidence for noncanonical types.

The unchanged native WSv2 guard at `openai_responses_namespace.go:61–68` skips initial namespace stripping. WS ingress and HTTP bridge normalization and protected retry paths remain the reviewed432 bytes. The patch adds no global bypass, fallback or model change. Default and ordinary sanitation are intact. No new mirrored tests were added for coverage.

The independent regression uses actual Forward and its existing upstream recorder for normal/passthrough HTTP under both policy states. It checks whole-reference equality through UseNumber, the exact integer and ordinary namespace cleanup. Its four cases are a coordinator runtime prescription, not local observed passes.

## Evidence boundary and exact remaining gates

The frozen `.spike-inputs/native/checks/r3-source-audit.json` includes coordinator receipt excerpts for exact432: 287 PASS records; the independent reference run exits 1 with the two opted-in HTTP failures and two passing default records. The separately named raw coordinator receipt files are not present in this snapshot. These frozen excerpts and the user-provided observations concern reviewed432 only; neither establishes replacement success.

All following gates are **NOT RUN by this reviewer**, and are limitations for runtime/integration approval rather than unfinished independent review work:

1. Exact replacement Go compilation and full pinned native behavior gate, retaining prior focused patterns and unchanged independent R1/R2 prescription (`sub2api-fork-review-v2/independent_boundary_test.go.txt`, SHA-256 `3ca97c2d50f0c3c498c51d1fb0af9b7fa5352089953f84d1224e6ea5e03887ce`). The frozen producer prescribes `python3 sub2api-fork/checks/run-backend-tests.py`; that runner is not captured in this worktree. Its root execution is separately owned; no result is invented.
2. Exact patched backend R3 gate: `go test -tags unit ./internal/service -run '^TestIndependentCompatibleReferenceNamespaceHTTP$' -count=1`, with all four cases required to pass. The replacement already contains the test; do not install a duplicate. Exact432 red evidence is frozen, not rerun here.
3. Replacement gofmt verification. Any formatting mutation requires new patch/file hashes and a gate bound to the resulting artifact.
4. Deploy and identify approved native reasoning and capability suppression together in the exclusive disposable engine; prove exact image/source custody.
5. Wire trusted installation and quarantine templates through serve.mjs, install independent snapshot/drain observer, and execute stopped-engine seed/guarded cleanup against pinned PostgreSQL.
6. Actual STOCK-consumer integration with accepted template/Copy ownership oracles, transport counters, capability-field audit and delayed-work drain.
7. Fixed installed harness manifest including binder/transitive imports, image custody and UID/FD/descendant containment; genuine native financial canary with high reasoning and tool/terminal/numeric evidence.

Only `sub2api-candidate-review-v4/` was written. Artifact verification passed; no Go/runtime test was executed. No root operations, Docker, network, providers, auth homes, credentials, Git mutation or candidate source edits were performed. Review deliverables are complete without waiting for external gates. The material risk is unverified replacement compilation/formatting/runtime behavior, not an outstanding source finding.
