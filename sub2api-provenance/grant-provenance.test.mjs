import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { rig, token, verifier, workflowSHA } from '../sub2api-spike/test-support.mjs';
import { bindGrantedRun } from '../sub2api-spike/granted-run.mjs';

// BR04: real signed OIDC -> HTTP grant -> receipt, without provider inference.
test('BR04 signed grant binds exact run and selection, cached identity and replay', async t => {
  const r = await rig(t);
  const expected = { runID: '123', attempt: '1', workflowSHA, provider: 'mimo', protocol: 'responses' };
  const runtime = { runID: '123', attempt: '1', workflowSHA, provider: 'mimo', agent: 'codex' };
  for (const body of [{ runID: '999' }, { attempt: '9' }, { workflowSHA: 'b'.repeat(40) }, { run_id: '999' }]) assert.equal((await r.grant('responses', {}, body)).status, 400);
  for (const claims of [{ workflow_sha: null }, { workflow_sha: 'b'.repeat(40) }, { run_id: null }, { run_attempt: null }]) assert.equal((await r.grant('responses', claims)).status, 401);
  assert.deepEqual(JSON.parse(await readFile(r.config.ledgerPath)).runs, {});
  const g = await (await r.grant()).json(); assert.deepEqual(bindGrantedRun(g, runtime), expected);
  for (const change of [{ runID: '999' }, { attempt: '2' }, { workflowSHA: 'b'.repeat(40) }, { provider: 'openrouter' }, { agent: 'claude' }]) assert.throws(() => bindGrantedRun(g, { ...runtime, ...change }));
  const cached = await (await r.grant('responses', { exp: Math.floor(Date.now() / 1000) + 1200 })).json();
  assert.deepEqual(cached, g); // New token expiry cannot extend cached authority.
  assert.equal((await r.grant('responses', { run_attempt: '2' })).status, 409);
  assert.equal((await r.grant('messages')).status, 409);
  await fetch(`${r.url}/grant`, { method: 'DELETE', headers: { authorization: `Bearer ${g.capability}` } });
  assert.equal((await r.grant()).status, 409); assert.equal(r.upstream.metrics.requests, 0);
});
test('BR04 incomplete verifier contract has no resolver or ledger admission effects', async t => {
  const valid = await verifier()(token()); let claims, resolved = 0;
  const r = await rig(t, { broker: { verifyOIDC: async () => claims, resolveWorkspace: () => { resolved++; return 'a'; } } });
  for (const change of [{ runID: undefined }, { runID: 123 }, { attempt: undefined }, { attempt: 1 }, { workflowSHA: undefined }, { workflowSHA: 'bad' }, { expires: undefined }]) {
    claims = { ...valid, ...change }; assert.equal((await r.grant()).status, 401);
  }
  assert.equal(resolved, 0); assert.deepEqual(JSON.parse(await readFile(r.config.ledgerPath)).runs, {});
  claims = valid; const g = await (await r.grant()).json();
  claims = { ...valid, workflowSHA: 'b'.repeat(40) };
  assert.deepEqual(await (await r.grant()).json(), g); // Cached identity is the original authorization.
  assert.equal(g.workflowSHA, workflowSHA); assert.equal(r.upstream.metrics.requests, 0);
});
