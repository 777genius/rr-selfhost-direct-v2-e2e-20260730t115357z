import test from 'node:test';
import assert from 'node:assert/strict';
import { bindGrantedRun } from './granted-run.mjs';
import { token, verifier, workflowSHA } from './test-support.mjs';
const runtime = { runID: '123', attempt: '1', workflowSHA, provider: 'mimo', agent: 'codex' };
test('signed verified identity yields only a positive identity receipt', async () => {
  const claims = await verifier()(token());
  const grant = { ...claims, provider: 'mimo', protocol: 'responses', capability: 'synthetic-secret', model: 'model' };
  const receipt = bindGrantedRun(grant, runtime);
  assert.deepEqual(receipt, { runID: '123', attempt: '1', workflowSHA, provider: 'mimo', protocol: 'responses' });
  assert.equal(Object.isFrozen(receipt), true);
  assert.deepEqual(bindGrantedRun({ ...grant, protocol: 'messages' }, { ...runtime, agent: 'claude' }), { ...receipt, protocol: 'messages' });
  assert.deepEqual(bindGrantedRun({ ...grant, provider: 'openrouter' }, { ...runtime, provider: 'openrouter' }), { ...receipt, provider: 'openrouter' });
});
test('spoofed runtime and malformed grant deny before an agent can execute', async () => {
  const grant = { ...await verifier()(token()), provider: 'mimo', protocol: 'responses' };
  for (const change of [{ runID: '124' }, { attempt: '2' }, { workflowSHA: 'b'.repeat(40) }, { provider: 'openrouter' }, { agent: 'claude' }, { agent: 'other' }, { attempt: 1 }, { runID: undefined }]) {
    let executed = false;
    assert.throws(() => { bindGrantedRun(grant, { ...runtime, ...change }); executed = true; }, /identity denied/);
    assert.equal(executed, false);
  }
  for (const change of [{ runID: '0123' }, { attempt: '01' }, { workflowSHA: undefined }, { protocol: undefined }, { provider: 'unknown' }]) assert.throws(() => bindGrantedRun({ ...grant, ...change }, runtime));
  assert.throws(() => bindGrantedRun(null, runtime)); assert.throws(() => bindGrantedRun(grant, null));
  assert.throws(() => bindGrantedRun({ ...grant, provider: 'openrouter', protocol: 'messages' }, { ...runtime, provider: 'openrouter', agent: 'claude' }));
});
