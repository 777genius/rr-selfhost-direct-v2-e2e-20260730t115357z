import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { normalizedReceipt } from './receipts.mjs';
// Regression: local green claims real Actions without client proof/provenance,
// wrong harness receipt is promoted, or raw credentials enter report artifacts.
test('receipt provenance false green and secret field rejection at file boundary', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-spike-20260930-receipt-')); const path = join(dir,'receipt.json');
  const receipt = { schema: 1, evidence_kind: 'contract', operator_reviewed: true, versions: { harness_git_sha: 'a'.repeat(40), harness_tree_sha256: 'b'.repeat(64), sub2api_source_sha: '96f4c115c9749078f90cbf210a01d39baf3f53b6', source_pin_verified: false, node: process.version }, results: [{ id: 'B02', status: 'PASS', expected: 'Forged signed OIDC rejected', actual: { rejected: true }, duration_ms: 1, upstream_requests: 0, limitation: 'Contract only', covers_requirement: true }] };
  try {
    await writeFile(path, JSON.stringify(receipt)); assert.equal((await normalizedReceipt(path, 'b'.repeat(64))).results[0].id, 'B02'); await assert.rejects(normalizedReceipt(path, 'c'.repeat(64)));
    receipt.results[0].id = 'A01'; await writeFile(path, JSON.stringify(receipt)); await assert.rejects(normalizedReceipt(path, 'b'.repeat(64)));
    receipt.results[0].id = 'B02'; receipt.results[0].actual = { credentials: 'synthetic-secret' }; await writeFile(path, JSON.stringify(receipt)); await assert.rejects(normalizedReceipt(path, 'b'.repeat(64)));
  } finally { await rm(dir, { recursive: true, force: true }); }
});
