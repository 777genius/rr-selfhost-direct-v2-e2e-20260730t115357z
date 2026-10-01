import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { templatePlan, validateTemplate } from '../sub2api-spike/operator/live-setup.mjs';
import { observedEffects } from '../sub2api-spike/operator/admin-roundtrip.mjs';
const owner = 'd'.repeat(32);
// No effects => unknown, even on early setup failure (original receipt invented 0).
test('BR05 unavailable telemetry stays unknown in actual roundtrip failure receipt', async () => {
  const key = randomUUID(), output = [];
  const path = process.env.CONSUMER_ROUNDTRIP_SOURCE ?? new URL('../sub2api-spike/operator/admin-roundtrip.mjs', import.meta.url);
  const source = await readFile(path, 'utf8');
  globalThis[key] = {
    process: { argv: [], version: 'v24.21.0' },
    readFile: async () => '{}', writeFile: async (path, value) => { if (path === '/receipts/admin-roundtrip.json') output.push(JSON.parse(value)); },
    AdminAPI: class {}, customerAdapter: () => { throw Error('DO_NOT_EXECUTE'); },
    loadFixtureConfiguration: async () => { throw Error('OBSERVATION_UNAVAILABLE'); },
    privateFile: async () => { throw Error('DO_NOT_READ'); }, templatePlan, validateTemplate,
    fetch: async () => { throw Error('OBSERVATION_UNAVAILABLE'); }
  };
  let code = `const {${Object.keys(globalThis[key]).join(',')}} = globalThis[${JSON.stringify(key)}];\n`;
  for (const line of source.split('\n')) {
    if (/^import /.test(line) && !/from 'node:(path|url)'/.test(line)) continue;
    code += line + '\n';
  }
  try {
    const module = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
    if (module.main) await module.main();
  } finally { delete globalThis[key]; }
  assert.equal(output.length, 1); assert.equal(output[0].status, 'FAIL');
  assert.equal(output[0].upstream_requests, null);
  assert.equal(output[0].capability_metadata_writes, null);
  assert.equal(output[0].telemetry, 'NOT_RUN');
  assert.deepEqual(output[0].results, []);
});
test('BR05 counters require observed cumulative effects and real drain acknowledgement', () => {
  const before = { captureID: owner, engineDigest: 'sha256:' + 'a'.repeat(64), requests: 10, capabilityMetadataWrites: 3 };
  const after = { ...before, requests: 13, capabilityMetadataWrites: 5, drained: true };
  assert.deepEqual(observedEffects(before, after), { requests: 3, writes: 2 });
  assert.deepEqual(observedEffects(before, { ...before, drained: true }), { requests: 0, writes: 0 });
  for (const bad of [{}, { ...after, requests: null }, { ...after, requests: 9 }, { ...after, capabilityMetadataWrites: 2 }, { ...after, drained: false }, { ...after, captureID: 'e'.repeat(32) }, { ...after, engineDigest: 'sha256:' + 'f'.repeat(64) }]) assert.throws(() => observedEffects(before, bad));
  assert.throws(() => observedEffects(undefined, after));
});
test('BR05 independent full DTO gate rejects active grouped foreign or lite templates', async () => {
  const stock = JSON.parse(await readFile(new URL('../sub2api-boundary/fixtures/stock-empty-account.json', import.meta.url), 'utf8'));
  const plan = templatePlan(owner), t = plan.templates[0], full = { ...stock, ...t, id: 101 };
  assert.equal(validateTemplate(full, t, owner), 101);
  for (const change of [a => { a.status = 'active'; }, a => { a.schedulable = true; }, a => { a.group_ids = [1]; }, a => { a.groups = null; }, a => { a.extra.rr_quarantine_template.fixtureOwner = 'e'.repeat(32); }, a => { delete a.credentials; }, a => { a.extra.openai_disable_capability_probe = false; }]) {
    const a = structuredClone(full); change(a); assert.throws(() => validateTemplate(a, t, owner));
  }
  assert.equal(new Set(plan.templates.map(t => t.name)).size, 6);
  assert.ok(plan.templates.every(t => t.status === 'inactive' && t.schedulable === false && t.group_ids.length === 0 && t.credentials.api_key.startsWith('inert-') && t.credentials.base_url === 'https://fixture.invalid/v1'));
});
