import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { mkdtemp, writeFile, access, rm } from 'node:fs/promises';
import { join } from 'node:path';
// Frozen consumer snapshot omits unchanged baseline gateway imports. Resolve
// only those imports to the canonical actual gateway sources; no factories mocked.
registerHooks({ resolve(specifier, context, next) {
  if (specifier.startsWith('../gateway-spike/') && context.parentURL?.includes('/.spike-inputs/consumer/sub2api-spike/'))
    return next(new URL('../gateway-spike/' + specifier.slice('../gateway-spike/'.length), import.meta.url).href, context);
  return next(specifier, context);
} });
const { boot } = await import('../.spike-inputs/consumer/sub2api-spike/serve.mjs');
test('actual frozen boot retains process lock after invalid ledger and prevents corrected restart', async t => {
  const dir = await mkdtemp(new URL('./verification/lock-probe-', import.meta.url).pathname);
  t.after(() => rm(dir, { recursive: true, force: true }));
  const ledgerPath = join(dir, 'ledger.json');
  await writeFile(ledgerPath, JSON.stringify({ schema: 0, runs: {} }));
  const config = { ledgerPath, scopes: {}, workspaces: {}, oidc: { ownerID: '13103045', workflowSHA: 'a'.repeat(40) } };
  await assert.rejects(boot(config, { brokerPort: 0 }), /Invalid ledger/);
  await access(ledgerPath + '.lock');
  await writeFile(ledgerPath, JSON.stringify({ schema: 1, runs: {} }));
  await assert.rejects(boot(config, { brokerPort: 0 }), { code: 'EEXIST' });
});
