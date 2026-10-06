# Root handoff — NOT READY

The actual native W2 default regression and interaction regression remain pending
independent native W3 repair. The final merged patch hash is unknown until that
work finishes. Offline green receipts below cannot authorize GO or attest that
private source ran. Real Redis/PG18/native image E2E remains NOT RUN.

1. Independently review the final full merged production patch after the native
   writer finishes repairs. Preserve native `30cb…`, probe `7d89…`, single W3
   cancellation `46b48c…` and memory W2 `12d830…` as component provenance. Final
   overlap hunks may legitimately differ. Do not substitute historical `6df1…`
   image or `e331…` binary.
2. Publish a public producer manifest with schema `slot-reviewed-merged-source-v1`,
   `review_status: APPROVED`, `inventory_scope: full-build-context`, upstream commit
   and `component_provenance` equal to the four full hashes in build-manifest.json.
   Supply nonempty `base_files` and `merged_files` maps of every build-context source
   relative path to SHA256 (including backend/go.mod). `production_changes` must
   enumerate exactly every changed path with `before_sha256` and `after_sha256`
   (null for absence). Pin `production_patch_sha256` to the full deduplicated final
   patch with a hunk per changed path, and `source_fingerprint_sha256` to SHA256
   of Python json.dumps(merged_files, sort_keys=True, separators=(',', ':')).encode().
   Inventory completeness and review authenticity are the external root's trust
   responsibility. A worker-authored JSON APPROVED value is not independent review.
3. The trusted root build pipeline must emit the actual receipt described by
   build-attestation.example.json for that same observed build: build ID, exact
   source fingerprint and build input fingerprint, final patch/manifest SHA256,
   same four component pins and public file paths, immutable output image, actual
   image ID, binary hash and canonical image Config hash. Root configuration
   separately pins the reviewed manifest, final patch and private build receipt
   byte hashes. Do not derive expected pins from whichever inputs happen to exist.
   Preflight rejects missing/empty maps, unknown components, missing receipt
   schema, historical build identities and source disagreement before launch.
   Actual Docker image ID/config and running /proc executable must then match
   the receipt. These comparisons implement external root trust, not independent
   proof that public source hashes caused compilation of private code.
4. Prepare a new private transport-isolated-r4 source-family fixture separately:
   full hash attestation for snapshot.sql, engine.env and lab.json, fresh owned
   PostgreSQL 18 DB with zero ALL accounts and ALL API keys, including deleted
   rows. Never reuse a production snapshot or import provider credentials. Root
   verifies all counts again in the actual newly restored DB before engine start.
   This worker does not read or copy that fixture. Keep private inputs regular,
   owned by the current operator (entrypoint requires root), exact mode 0600;
   every ancestor must be a real directory. Descriptor-based O_NOFOLLOW traversal
   reads and hashes the same opened bytes. Public patch/manifest inputs may be 0644.
5. On an authorized disposable root host with already local immutable images,
   execute root-driver.py with the separately pinned private configuration and a
   new absolute output directory as shown in README.md. Review all 84 rows,
   final-zero/provider, deployment, root-result and cleanup journal together.

The matrix stays 20 cycles × four protocol/lane pairs plus four defaults: 168
accepted effects, 248 gateway requests, 252 reserved IDs, actual waiter proofs,
1250 ms cancellation and quiet intervals, unchanged explicit-release default
drain. Healthy third recovery uses the slot-local strict native SSE grammar:
Responses creation/start, coherent item/part/text/terminal and usage; Messages
message start, text block lifecycle, end-turn usage delta and exact message stop.
The actual existing healthy fixtures remain accepted. Empty content, wrong
protocol, junk, duplicate/absent terminal, TCP end alone, bad usage/IDs and tools
in a text-only healthy case fail. Canonical historical source is unchanged.

Offline: prepare into a new owned build directory; run offline.test.mjs,
offline_test.py, recovery-contract.test.mjs, custody_contract_test.py and
build_contract_test.py. RED/GREEN receipts use the same contracts against frozen
W1 and repaired boundaries. Supplied review reproductions are copied byte-for-byte
under review/reproductions; old accepts and new rejects are retained separately.
