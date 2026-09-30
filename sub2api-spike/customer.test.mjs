import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { AdminAPI, customerAdapter, testCustomerServer, safeProviderURL } from './customer.mjs';
import { listen, stop, readJSON, send } from './util.mjs';
async function setup(t, { createFailure = false } = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-spike-20260930-customer-'));
  const records = new Map(), observations = []; let next = 1;
  // Faithful SOURCE API transport fake, explicitly NOT a live Sub2API instance.
  const adminServer = http.createServer(async (req, res) => {
    observations.push({ method: req.method, path: req.url, headers: req.headers });
    if (req.headers['x-api-key'] !== 'synthetic-shared-admin') { send(res, 401, { code: 401 }); return; }
    const u = new URL(req.url, 'http://admin'); const id = Number(u.pathname.split('/').at(-1));
    if (u.pathname.endsWith('/accounts/data')) { send(res, 200, { code: 0, data: { accounts: [...records.values()].filter(a => String(a.id) === u.searchParams.get('ids')) } }); return; }
    if (req.method === 'POST' && u.pathname.endsWith('/accounts')) {
      const b = await readJSON(req); const a = { ...b, id: next++, status: 'active', name: 'synthetic-credential-in-name', extra: { nested: 'synthetic-refresh-in-extra' } }; records.set(a.id, a);
      if (createFailure) { send(res, 503, { code: 503, message: 'synthetic-credential-leak' }); return; }
      send(res, 200, { code: 0, data: a }); return;
    }
    const a = records.get(id); if (!a) { send(res, 404, { code: 404 }); return; }
    if (req.method === 'DELETE') { records.delete(id); send(res, 200, { code: 0, data: {} }); return; }
    if (req.method === 'PUT') Object.assign(a, await readJSON(req));
    send(res, 200, { code: 0, data: a });
  });
  const adminURL = await listen(adminServer);
  const workspaces = { a: { members: { owner: 'owner', member: 'member' }, groups: { 'mimo:responses': 11 } }, b: { members: { owner: 'owner' }, groups: { 'mimo:responses': 22 } } };
  const config = { statePath: join(dir, 'customer.json'), admin: new AdminAPI({ baseURL: adminURL, adminKey: 'synthetic-shared-admin' }), workspaces, credentialProfiles: { a: { 'mimo:responses': 'synthetic-upstream-a' }, b: { 'mimo:responses': 'synthetic-upstream-b' } } };
  const adapter = await customerAdapter(config);
  const customer = testCustomerServer({ adapter, testOnly: true, identities: { 'synthetic-owner-a': { workspace: 'a', user: 'owner' }, 'synthetic-member-a': { workspace: 'a', user: 'member' }, 'synthetic-owner-b': { workspace: 'b', user: 'owner' } } });
  const url = await listen(customer);
  t.after(async () => { await stop(customer); await stop(adminServer); await rm(dir, { force: true, recursive: true }); });
  async function call(identity, method, path = '/accounts', body) { return fetch(`${url}${path}`, { method, headers: { authorization: `Bearer synthetic-${identity}`, 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }); }
  const connect = who => call(who, 'POST', '/accounts', { provider: 'mimo', protocol: 'responses' });
  return { dir, config, records, observations, workspaces, adapter, call, connect };
}
// Regression: customer changes group/URL or admin credential fields escape UI.
test('C01 C07 D05 account CRUD roundtrip with sanitized responses', async t => {
  const r = await setup(t); const a = await (await r.connect('owner-a')).json(); assert.match(a.id, /^[a-f0-9]{32}$/);
  assert.equal((await (await r.call('owner-a', 'GET')).json()).length, 1);
  const update = await r.call('owner-a', 'PUT', `/accounts/${a.id}`, { concurrency: 1 }); assert.equal((await update.json()).concurrency, 1);
  assert.equal((await (await r.call('owner-a', 'POST', `/accounts/${a.id}/pause`)).json()).status, 'inactive');
  const exported = await (await r.call('owner-a', 'POST', `/accounts/${a.id}/export`)).json(); assert.equal(exported.restorable, false);
  assert.ok(!JSON.stringify(exported).includes('synthetic-')); assert.ok(!Object.hasOwn(exported.account, 'credentials'));
  assert.equal((await r.call('owner-a', 'DELETE', `/accounts/${a.id}`)).status, 200); assert.equal(r.records.size, 0); assert.equal((await r.call('owner-a', 'GET', `/accounts/${a.id}`)).status, 404);
  assert.ok(r.observations.some(x => x.path.includes('/accounts/data?ids='))); assert.ok(r.observations.every(x => x.headers['x-api-key'] === 'synthetic-shared-admin'));
});
// Regression: guessed valid ID allows cross-tenant read/mutation/export/refresh.
test('C02 C03 two tenant guessed IDs and member management denied before admin effects', async t => {
  const r = await setup(t); const a = await (await r.connect('owner-a')).json(); const before = r.observations.length;
  for (const [method, suffix] of [['GET', ''], ['PUT', ''], ['DELETE', ''], ['POST', '/pause'], ['POST', '/refresh'], ['POST', '/export']]) assert.equal((await r.call('owner-b', method, `/accounts/${a.id}${suffix}`, method === 'PUT' ? { concurrency: 1 } : undefined)).status, 404);
  for (const [method, suffix] of [['PUT', ''], ['DELETE', ''], ['POST', '/pause'], ['POST', '/refresh'], ['POST', '/export']]) assert.equal((await r.call('member-a', method, `/accounts/${a.id}${suffix}`, method === 'PUT' ? { concurrency: 1 } : undefined)).status, 403);
  assert.equal((await r.connect('member-a')).status, 403); assert.equal(r.observations.length, before); assert.deepEqual(await (await r.call('owner-b', 'GET')).json(), []);
});
// Regression: server membership removal/suspension is ignored by mutation path.
test('C04 account membership removal and suspension fail closed', async t => {
  const r = await setup(t); delete r.workspaces.a.members.owner; assert.equal((await r.connect('owner-a')).status, 403); r.workspaces.b.suspended = true; assert.equal((await r.connect('owner-b')).status, 403); assert.equal(r.observations.length, 0);
});
// Regression: stale IDs or concurrent mutation revive deleted ownership after restart.
test('C06 concurrent update delete stale IDs and durable ownership', async t => {
  const r = await setup(t); const a = await (await r.connect('owner-a')).json(); const b = await (await r.connect('owner-b')).json();
  const results = await Promise.all([r.call('owner-a', 'DELETE', `/accounts/${a.id}`), r.call('owner-a', 'PUT', `/accounts/${a.id}`, { concurrency: 1 })]); assert.equal(results[0].status, 200); assert.ok([200, 404].includes(results[1].status));
  const restarted = await customerAdapter(r.config); await assert.rejects(restarted.operate({ workspace: 'a', user: 'owner' }, 'read', a.id), { status: 404 }); await assert.rejects(restarted.operate({ workspace: 'a', user: 'owner' }, 'delete', b.id), { status: 404 }); assert.equal(r.records.size, 1);
});
// Regression: group drift/multi-group account silently permits another tenant engine route.
test('C09 groups routing restriction drift is observable', async t => {
  const r = await setup(t); const a = await (await r.connect('owner-a')).json(); const record = [...r.records.values()][0]; assert.deepEqual(record.group_ids, [11]); assert.equal(record.credentials.api_key, 'synthetic-upstream-a'); record.group_ids = [11, 22]; assert.equal((await r.call('owner-a', 'GET', `/accounts/${a.id}`)).status, 409);
});
// Regression: ambiguous create publishes account authority or silently recreates it.
test('C10 partial create failure persists recovery_required with no public binding', async t => {
  const r = await setup(t, { createFailure: true }); assert.equal((await r.connect('owner-a')).status, 502); assert.equal(r.records.size, 1);
  assert.deepEqual(await (await r.call('owner-a', 'GET')).json(), []); assert.equal((await r.adapter.recovery())[0].state, 'recovery_required');
  const state = JSON.parse(await readFile(join(r.dir, 'customer.json'), 'utf8')); assert.ok(!JSON.stringify(state).includes('synthetic-upstream-a')); assert.equal((await (await customerAdapter(r.config)).recovery()).length, 1);
});
// Regression: arbitrary URL/proxy/account field bypasses server metadata and SSRF policy.
test('D07 customer unsafe URLs and routing input denied', async t => {
  const r = await setup(t);
  for (const url of ['http://127.0.0.1', 'https://169.254.169.254/', 'https://token-plan-sgp.xiaomimimo.com@evil.example/v1', 'https://token-plan-sgp.xiaomimimo.com/v1?redirect=x', 'https://openrouter.ai:444/api/v1']) assert.throws(() => safeProviderURL(url));
  for (const extra of [{ baseURL: 'http://localhost' }, { group_id: 22 }, { account_id: 1 }, { key: 'synthetic-caller' }]) assert.equal((await r.call('owner-a', 'POST', '/accounts', { provider: 'mimo', protocol: 'responses', ...extra })).status, 400);
  assert.equal(r.records.size, 0);
});
// Regression: API-key account invents an OAuth success result.
test('F05 API-key refresh honestly requires OAuth identity', async t => {
  const r = await setup(t); const a = await (await r.connect('owner-a')).json(); const result = await r.call('owner-a', 'POST', `/accounts/${a.id}/refresh`); assert.equal(result.status, 409); assert.equal((await result.json()).error.type, 'refresh_requires_oauth');
});
// Regression: server credential rotation keeps stale binding authorized or old
// account schedulable; replacement must retire old ID and revoke workspace grants.
test('C08 account replacement retires old identity and uses rotated server credential', async t => {
  const r = await setup(t); const a = await (await r.connect('owner-a')).json();
  r.config.credentialProfiles.a['mimo:responses'] = 'synthetic-rotated-upstream-a';
  const changed = await r.call('owner-a', 'POST', `/accounts/${a.id}/replace`); assert.equal(changed.status, 200); const replacement = await changed.json(); assert.notEqual(replacement.id, a.id);
  assert.equal((await r.call('owner-a', 'GET', `/accounts/${a.id}`)).status, 404); assert.equal(r.records.size, 1); assert.equal([...r.records.values()][0].credentials.api_key, 'synthetic-rotated-upstream-a');
});
