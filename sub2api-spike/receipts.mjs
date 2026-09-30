import { readFile } from 'node:fs/promises';
const kinds = ['contract', 'synthetic-upstream', 'synthetic-container', 'real-Actions', 'source-audit'];
export async function normalizedReceipt(path, expectedTree) {
  const text = await readFile(path, 'utf8'); if (text.length > 2 * 1024 * 1024) throw Error('Receipt limit');
  const r = JSON.parse(text), v = r.versions;
  if (r.schema !== 1 || r.operator_reviewed !== true || !kinds.includes(r.evidence_kind) || !Array.isArray(r.results) || !v || !/^[a-f0-9]{40}$/.test(v.harness_git_sha ?? '') || v.harness_tree_sha256 !== expectedTree || v.sub2api_source_sha !== '96f4c115c9749078f90cbf210a01d39baf3f53b6' || !/^v24\./.test(v.node ?? '')) throw Error('Unbound receipt');
  if (['synthetic-container', 'real-Actions'].includes(r.evidence_kind) && (v.source_pin_verified !== true || !['sub2api', 'postgres', 'redis', 'node'].every(k => /@sha256:[a-f0-9]{64}$/.test(v.images?.[k] ?? '')))) throw Error('Unproven engine provenance');
  const seen = new Set();
  for (const e of r.results) {
    if (!/^[A-H]\d{2}$/.test(e.id) || seen.has(e.id) || !['PASS', 'FAIL', 'NOT RUN'].includes(e.status) || typeof e.expected !== 'string' || !Object.hasOwn(e, 'actual') || !Number.isFinite(e.duration_ms) || e.duration_ms < 0 || !(e.upstream_requests === null || Number.isSafeInteger(e.upstream_requests) && e.upstream_requests >= 0) || typeof e.limitation !== 'string' || typeof e.covers_requirement !== 'boolean') throw Error('Invalid scenario receipt');
    seen.add(e.id);
    if (['A01', 'A02', 'A03'].includes(e.id) && e.status === 'PASS' && (r.evidence_kind !== 'real-Actions' || !e.actual?.tool_read_verified || !e.actual?.rules_read_verified || !e.actual?.terminal_verified || !e.actual?.independent_numeric_reproduction || !/^[1-9]\d*$/.test(String(e.actual?.run_id ?? '')) || !['0.159.2', '2.1.285'].includes(e.actual?.client_version))) throw Error('Client proof missing');
  }
  // No raw transcripts, credential-bearing exports or arbitrary headers allowed.
  if (/"(?:authorization|credentials|refresh_token|access_token|admin_key|prompt|transcript|raw_body)"\s*:/i.test(text)) throw Error('Unsanitized receipt');
  return r;
}
