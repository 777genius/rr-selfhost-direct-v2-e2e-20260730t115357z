import test from 'node:test';
import assert from 'node:assert/strict';
import { templatePlan } from '../.spike-inputs/consumer/sub2api-spike/operator/live-setup.mjs';
import { bindGrantedRun } from '../.spike-inputs/consumer/sub2api-spike/granted-run.mjs';
import { AdminAPI, requireProbeInstallation, probePatchSHA256 } from '../.spike-inputs/consumer/sub2api-spike/customer.mjs';
const runtime = { runID: '123', attempt: '2', workflowSHA: 'a'.repeat(40), provider: 'mimo', agent: 'codex' };
const grant = { ...runtime, protocol: 'responses' };
test('grant identity rejects independent mismatches and remains immutable after source mutation', () => {
  for (const [key, value] of Object.entries({ runID: '124', attempt: '3', workflowSHA: 'b'.repeat(40), provider: 'openrouter', protocol: 'messages' })) {
    assert.throws(() => bindGrantedRun({ ...grant, [key]: value }, runtime));
  }
  const source = { ...grant }, identity = bindGrantedRun(source, runtime);
  source.runID = '124'; source.protocol = 'messages';
  assert.equal(identity.runID, '123'); assert.equal(identity.protocol, 'responses');
  assert.throws(() => { identity.runID = '124'; });
  assert.throws(() => bindGrantedRun({ ...grant, protocol: 'messages' }, { ...runtime, provider: 'openrouter', agent: 'claude' }));
});
test('server installation strictly validates and snapshots capability policy', () => {
  const installation = { standardMode: true, openaiDisableCapabilityProbe: true, engineDigest: 'sha256:' + 'a'.repeat(64), probePatchSHA256 };
  const admin = new AdminAPI({ baseURL: 'http://unused.invalid', adminKey: 'synthetic', installation });
  installation.openaiDisableCapabilityProbe = false;
  requireProbeInstallation(admin.installation);
  assert.throws(() => { admin.installation.openaiDisableCapabilityProbe = false; });
  for (const key of Object.keys(installation)) assert.throws(() => requireProbeInstallation({ ...admin.installation, [key]: key.includes('Mode') || key.includes('Probe') ? 'true' : 'bad' }));
});
test('generated psql script starts with the ON_ERROR_STOP meta-command', () => {
  const sql = templatePlan('a'.repeat(32)).sql;
  // Checks generated operator output, not the source text. A psql meta-command
  // uses one backslash; two backslashes mean the end-of-meta-command separator.
  assert.equal(sql.split('\n')[0], '\\set ON_ERROR_STOP on');
});
