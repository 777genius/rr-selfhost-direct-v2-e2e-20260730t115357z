import test from 'node:test';
import assert from 'node:assert/strict';

test('server import exposes boot without reading CLI config or opening listeners', async () => {
  const { boot } = await import('./serve.mjs');
  assert.equal(typeof boot, 'function');
});

import http from 'node:http';
import { mkdtemp, writeFile, readFile, rm, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { probePatchSHA256 } from './customer.mjs';
import { listen, stop, readJSON, send } from './util.mjs';

async function fixture(t) {
  const dir = await mkdtemp(join(tmpdir(), 'rr-server-wiring-w1-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  for (const name of ['admin', 'credential', 'broker']) await writeFile(join(dir, name), `synthetic-${name}`);
  const config = {
    ledgerPath: join(dir, 'ledger.json'),
    oidc: { ownerID: '13103045', workflowSHA: 'a'.repeat(40) },
    workspaces: { a: { members: { owner: 'owner' }, groups: { 'mimo:responses': 11 } } },
    scopes: { 'mimo:responses': { model: 'mimo-v2.6-pro', protocol: 'responses', baseURL: 'http://sub2api:8080', workspaces: { a: { groupID: 11, keyFile: join(dir, 'broker') } } } },
    customer: { listenHost: '127.0.0.1', baseURL: 'http://127.0.0.1:1', adminKeyFile: join(dir, 'admin'),
      credentialFiles: { a: { 'mimo:responses': join(dir, 'credential') } }, statePath: join(dir, 'customer.json'),
      quarantineTemplates: { a: { 'mimo:responses': 101 } },
      installation: { standardMode: true, openaiDisableCapabilityProbe: true, engineDigest: 'sha256:' + 'a'.repeat(64), probePatchSHA256 },
      testOnly: true, identities: { 'synthetic-owner': { workspace: 'a', user: 'owner' } } }
  };
  return { config, dir };
}
const ports = { brokerPort: 0, customerPort: 0 };
async function absent(path) { await assert.rejects(access(path), { code: 'ENOENT' }); }

// Observe the actual HTTP listen boundary, not a substitute broker factory.
test('invalid installation denies before any listener, customer state or broker ledger effect', async t => {
  const { boot } = await import('./serve.mjs');
  for (const mutate of [c => { delete c.installation; }, c => { c.installation.standardMode = false; },
    c => { c.installation.openaiDisableCapabilityProbe = false; }, c => { c.installation.engineDigest = 'unverified'; },
    c => { c.installation.probePatchSHA256 = 'b'.repeat(64); }]) {
    const { config } = await fixture(t); mutate(config.customer);
    const original = http.Server.prototype.listen; let calls = 0;
    http.Server.prototype.listen = function (...args) { calls++; return original.apply(this, args); };
    try { await assert.rejects(boot(config, ports), { code: 'probe_contract_unverified' }); }
    finally { http.Server.prototype.listen = original; }
    assert.equal(calls, 0);
    await absent(config.ledgerPath); await absent(config.ledgerPath + '.lock'); await absent(config.customer.statePath);
  }
});

test('malformed templates and failed complete customer initialization precede broker effects', async t => {
  const { boot } = await import('./serve.mjs');
  for (const mutate of [c => { c.customer.quarantineTemplates = []; }, c => { c.customer.quarantineTemplates = null; }, c => { c.customer.quarantineTemplates.a = null; },
    c => { c.customer.quarantineTemplates.a['mimo:responses'] = '101'; }, c => { c.customer.quarantineTemplates.a.unknown = 101; },
    c => { c.customer.quarantineTemplates.foreign = {}; }, c => { c.workspaces.a.quarantineTemplates = []; }, c => { c.customer.testOnly = false; },
    c => { c.customer.identities = { owner: { workspace: 'a', user: 'owner' } }; },
    c => { c.customer.listenHost = '0.0.0.0'; }, c => { c.customer.listenHost = '::'; },
    async c => { await writeFile(c.customer.statePath, '{"schema":0,"bindings":{}}'); }]) {
    const { config } = await fixture(t); await mutate(config);
    const original = http.Server.prototype.listen; let calls = 0;
    http.Server.prototype.listen = function (...args) { calls++; return original.apply(this, args); };
    try { await assert.rejects(boot(config, ports)); }
    finally { http.Server.prototype.listen = original; }
    assert.equal(calls, 0); await absent(config.ledgerPath); await absent(config.ledgerPath + '.lock');
  }
});

test('actual startup uses AdminAPI template transport, retains private flags and closes both listeners', async t => {
  const { boot } = await import('./serve.mjs');
  const { config } = await fixture(t);
  let template = { id: 101, name: 'rr-sub2-spike-20260930-template', platform: 'openai', type: 'apikey', status: 'inactive', schedulable: false,
    credentials: {}, extra: { openai_disable_capability_probe: true, rr_quarantine_template: { workspace: 'a', provider: 'mimo', protocol: 'responses' } } };
  let account; const trace = [];
  const admin = http.createServer(async (req, res) => {
    try {
      assert.equal(req.headers['x-api-key'], 'synthetic-admin');
      const body = ['PUT', 'POST'].includes(req.method) ? await readJSON(req) : undefined;
      trace.push({ method: req.method, path: req.url, body });
      let data;
      if (req.url === '/api/v1/admin/accounts/101') {
        if (body) Object.assign(template, body); data = template;
      } else if (req.url === '/api/v1/admin/accounts/101/duplicate') {
        account = { ...structuredClone(template), id: 1, name: template.name + ' (Copy)', status: 'active', schedulable: false }; data = account;
      } else if (req.url === '/api/v1/admin/accounts/1' || req.url === '/api/v1/admin/accounts/1/schedulable') {
        if (body) Object.assign(account, body); data = account;
      } else if (req.url.startsWith('/api/v1/admin/accounts/data?')) data = { accounts: [account] };
      else throw Error('unexpected admin path');
      send(res, 200, { code: 0, data });
    } catch { send(res, 500, { code: 500 }); }
  });
  config.customer.baseURL = await listen(admin); t.after(() => stop(admin));
  const runtime = await boot(config, ports); t.after(runtime.shutdown);
  assert.equal(runtime.control.address().address, '127.0.0.1');
  const url = `http://127.0.0.1:${runtime.control.address().port}`;
  const request = async (path, method = 'GET', body) => {
    const response = await fetch(url + path, { method, headers: { authorization: 'Bearer synthetic-owner', 'content-type': 'application/json' }, body: body && JSON.stringify(body) });
    assert.equal(response.status, 200); return response.json();
  };
  const created = await request('/accounts', 'POST', { provider: 'mimo', protocol: 'responses' });
  assert.equal(created.status, 'active');
  assert.equal(trace[0].path, '/api/v1/admin/accounts/101');
  assert.equal(trace.filter(x => x.path.endsWith('/duplicate')).length, 1);
  assert.equal(account.credentials.api_key, 'synthetic-credential');
  assert.equal(account.credentials.base_url, 'https://token-plan-sgp.xiaomimimo.com/v1');
  assert.deepEqual(account.group_ids, [11]); assert.equal(account.schedulable, true);
  for (const flag of ['openai_disable_capability_probe', 'openai_passthrough', 'openai_preserve_compatible_reasoning']) assert.equal(account.extra[flag], true);
  assert.equal(account.extra.openai_responses_mode, 'force_responses');
  assert.equal(account.extra.rr_quarantine.workspace, 'a');
  const read = await request(`/accounts/${created.id}`);
  const exported = await request(`/accounts/${created.id}/export`, 'POST');
  assert.deepEqual(Object.keys(read).sort(), ['concurrency', 'id', 'protocol', 'provider', 'status']);
  assert.deepEqual(exported, { schema: 1, restorable: false, account: read });
  assert.equal(JSON.stringify([created, read, exported]).includes('synthetic-'), false);
  await request(`/accounts/${created.id}`, 'PUT', { concurrency: 1 });
  assert.equal(account.extra.openai_disable_capability_probe, true);
  const brokerPort = runtime.server.address().port, customerPort = runtime.control.address().port;
  await runtime.shutdown(); await runtime.shutdown();
  assert.equal(runtime.server.listening, false); assert.equal(runtime.control.listening, false);
  await absent(config.ledgerPath + '.lock');
  for (const port of [brokerPort, customerPort]) {
    const probe = http.createServer(); await new Promise((resolve, reject) => { probe.once('error', reject); probe.listen(port, '127.0.0.1', resolve); }); await stop(probe);
  }
});

test('customer listen failure rolls back broker listener and ledger lock', async t => {
  const { boot } = await import('./serve.mjs');
  const { config } = await fixture(t);
  const occupied = http.createServer(); await listen(occupied); t.after(() => stop(occupied));
  await assert.rejects(boot(config, { brokerPort: 0, customerPort: occupied.address().port }), { code: 'EADDRINUSE' });
  await absent(config.ledgerPath + '.lock');
  // Reopening the same ledger proves its exclusive process lock was released.
  const runtime = await boot(config, ports); await runtime.shutdown();
});
