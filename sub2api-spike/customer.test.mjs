import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, rm, readFile, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { AdminAPI, customerAdapter, testCustomerServer, safeProviderURL } from './customer.mjs';
import { listen, stop, readJSON, send } from './util.mjs';
const stockEmptyAccount = JSON.parse(await readFile(new URL('../sub2api-boundary/fixtures/stock-empty-account.json', import.meta.url), 'utf8'));
// Independent stock Go omitempty serialization, not adapter normalization.
function stockWire(a) {
  const dto = structuredClone(a);
  for (const key of ['group_ids', 'groups', 'account_groups']) if (Array.isArray(dto[key]) && dto[key].length === 0) delete dto[key];
  return dto;
}
async function setup(t, { createFailure = false, inject = async () => {}, revoke = async () => {} } = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-spike-20260930-customer-'));
  const records = new Map(), observations = [], authorityChanges = []; let next = 1;
  // HTTP fault lab exercises the inspected duplicate transport contract.
  // It cannot prove the engine transaction; real-admin receipt remains required.
  const templates = new Map([['a', 101], ['b', 102]].map(([workspace, id]) => [id, { ...structuredClone(stockEmptyAccount), id, name: 'rr-sub2-spike-20260930-template', type: 'apikey', platform: 'openai', status: 'inactive', schedulable: false, group_ids: [], extra: { rr_quarantine_template: { workspace, provider: 'mimo', protocol: 'responses' } } }]));
  const adminServer = http.createServer(async (req, res) => {
    observations.push({ method: req.method, path: req.url, headers: req.headers });
    if (req.headers['x-api-key'] !== 'synthetic-shared-admin') { send(res, 401, { code: 401 }); return; }
    const u = new URL(req.url, 'http://admin'); const id = Number(u.pathname.split('/').at(-1));
    if (u.pathname.endsWith('/accounts/data')) { send(res, 200, { code: 0, data: { accounts: [...records.values()].filter(a => String(a.id) === u.searchParams.get('ids')) } }); return; }
    if (req.method === 'POST' && u.pathname.endsWith('/duplicate')) {
      const template = templates.get(Number(u.pathname.split('/').at(-2)));
      const a = { ...structuredClone(template), name: template.name + ' (Copy)', id: next++, status: 'active', schedulable: false };
      assert.match(req.headers['idempotency-key'], /^[a-f0-9]{32}$/); records.set(a.id, a);
      await inject('created', { a, dir, workspaces });
      if (createFailure) { send(res, 503, { code: 503, message: 'synthetic-credential-leak' }); return; }
      send(res, 200, { code: 0, data: stockWire(a) }); return;
    }
    if (req.method === 'GET' && u.pathname.endsWith('/accounts')) { send(res, 200, { code: 0, data: { items: [...records.values()].map(stockWire), total: records.size } }); return; }
    const accountID = u.pathname.endsWith('/schedulable') ? Number(u.pathname.split('/').at(-2)) : id;
    const a = records.get(accountID) ?? templates.get(accountID); if (!a) { send(res, 404, { code: 404 }); return; }
    if (req.method === 'DELETE') { records.delete(id); send(res, 200, { code: 0, data: {} }); return; }
    if (req.method === 'PUT' || req.method === 'POST' && u.pathname.endsWith('/schedulable')) {
      const body = await readJSON(req); Object.assign(a, body);
      if (await inject('updated', { a, body, dir, workspaces }) === '503') { send(res, 503, { code: 503 }); return; }
    }
    send(res, 200, { code: 0, data: stockWire(a) });
  });
  const adminURL = await listen(adminServer);
  const workspaces = { a: { members: { owner: 'owner', member: 'member' }, groups: { 'mimo:responses': 11 } }, b: { members: { owner: 'owner' }, groups: { 'mimo:responses': 22 } } };
  const config = { onAuthorityChange: async workspace => { authorityChanges.push(workspace); await revoke(workspaces, workspace); }, statePath: join(dir, 'customer.json'), admin: new AdminAPI({ baseURL: adminURL, adminKey: 'synthetic-shared-admin' }), workspaces, quarantineTemplates: { a: { 'mimo:responses': 101 }, b: { 'mimo:responses': 102 } }, credentialProfiles: { a: { 'mimo:responses': 'synthetic-upstream-a' }, b: { 'mimo:responses': 'synthetic-upstream-b' } } };
  const adapter = await customerAdapter(config);
  const customer = testCustomerServer({ adapter, testOnly: true, identities: { 'synthetic-owner-a': { workspace: 'a', user: 'owner' }, 'synthetic-member-a': { workspace: 'a', user: 'member' }, 'synthetic-owner-b': { workspace: 'b', user: 'owner' } } });
  const url = await listen(customer);
  t.after(async () => { await stop(customer); await stop(adminServer); await rm(dir, { force: true, recursive: true }); });
  async function call(identity, method, path = '/accounts', body) { return fetch(`${url}${path}`, { method, headers: { authorization: `Bearer synthetic-${identity}`, 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }); }
  const connect = who => call(who, 'POST', '/accounts', { provider: 'mimo', protocol: 'responses' });
  return { dir, config, records, templates, authorityChanges, observations, workspaces, adapter, call, connect };
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
  assert.equal([...r.records.values()][0].status, 'active'); assert.equal([...r.records.values()][0].schedulable, false); assert.deepEqual([...r.records.values()][0].group_ids, []);
  assert.equal((await r.connect('owner-a')).status, 409); assert.equal(r.records.size, 1);
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

// Regression: stock POST defaults silently create an active/default-group orphan.
test('stock admin create contract is denied before any remote write', async () => {
  const admin = new AdminAPI({ baseURL: 'https://unused.invalid', adminKey: 'synthetic-only' });
  await assert.rejects(admin.createQuarantined({}), { status: 503, code: 'quarantine_template_required' });
});
// Regression: ownership is not fsynced before group binding, or final save failure
// leaves an engine account routable even though the adapter never returned its ID.
test('real filesystem persistence failure quarantines acknowledged create', async t => {
  const r = await setup(t, { inject: async (event, { dir }) => {
    if (event === 'created') await mkdir(join(dir, 'customer.json.new'));
  } });
  assert.equal((await r.connect('owner-a')).status, 503);
  const a = [...r.records.values()][0]; assert.equal(a.status, 'inactive'); assert.equal(a.schedulable, false); assert.deepEqual(a.group_ids, []);
  await rm(join(r.dir, 'customer.json.new'), { recursive: true });
  const restarted = await customerAdapter(r.config); const [intent] = await restarted.recovery();
  assert.equal((await restarted.reconcile({ workspace: 'a', user: 'owner' }, intent.id)).retired, true);
  assert.equal(r.records.size, 0);
});
// Regression: promotion publishes authority after membership disappears in flight.
test('membership loss during promotion compensates engine routing', async t => {
  const r = await setup(t, { inject: async (event, { body, workspaces }) => {
    if (event === 'updated' && body.group_ids?.length) delete workspaces.a.members.owner;
  } });
  assert.equal((await r.connect('owner-a')).status, 403);
  const a = [...r.records.values()][0]; assert.equal(a.status, 'inactive'); assert.equal(a.schedulable, false); assert.deepEqual(a.group_ids, []);
});
// Regression: name-only reconciliation adopts another workspace's account or
// reissues POST after an ambiguous commit. Recovery must use durable full marker.
test('restart reconciliation completes only the exact owned quarantine', async t => {
  const r = await setup(t, { createFailure: true }); await r.connect('owner-a');
  const a = [...r.records.values()][0]; r.records.set(999, { ...a, id: 999, extra: { ...a.extra, rr_quarantine: { ...a.extra.rr_quarantine, workspace: 'b' } } });
  const restarted = await customerAdapter(r.config); const [intent] = await restarted.recovery();
  await assert.rejects(restarted.reconcile({ workspace: 'b', user: 'owner' }, intent.id, 'complete'), { status: 404 });
  const result = await restarted.reconcile({ workspace: 'a', user: 'owner' }, intent.id, 'complete');
  assert.equal(result.status, 'active'); assert.deepEqual(a.group_ids, [11]); assert.equal(a.schedulable, true);
  assert.equal(r.records.get(999).schedulable, false);
  assert.equal(r.observations.filter(x => x.method === 'POST' && x.path.endsWith('/duplicate')).length, 1);
});
// Regression: omitted financial/account limits or customer overrides widen routing.
test('MiMo native reasoning and server limits survive quarantine promotion', async t => {
  const r = await setup(t); await r.connect('owner-a'); const a = [...r.records.values()][0];
  assert.equal(a.concurrency, 2); assert.equal(a.priority, 1); assert.equal(a.rate_multiplier, 1);
  assert.equal(a.extra.openai_preserve_compatible_reasoning, true); assert.equal(a.extra.openai_responses_mode, 'force_responses'); assert.equal(a.extra.openai_passthrough, true);
  assert.equal((await r.call('owner-a', 'PUT', `/accounts/${(await r.adapter.operate({ workspace: 'a', user: 'owner' }, 'list'))[0].id}`, { concurrency: 3 })).status, 400);
});

// Regression: failed final publication leaves a promoted engine account live.
test('final ownership save failure removes active group and scheduler permission', async t => {
  const r = await setup(t, { inject: async (event, { dir, body, a }) => {
    if (event === 'updated' && body.schedulable === true) {
      const persisted = JSON.parse(await readFile(join(dir, 'customer.json'), 'utf8'));
      const b = Object.values(persisted.bindings)[0]; assert.equal(b.upstreamID, a.id); assert.equal(b.state, 'bound');
      await mkdir(join(dir, 'customer.json.new'));
    }
  } });
  assert.equal((await r.connect('owner-a')).status, 503);
  const a = [...r.records.values()][0]; assert.equal(a.status, 'inactive'); assert.equal(a.schedulable, false); assert.deepEqual(a.group_ids, []);
});
// Regression: create intents exist only in RAM when the remote transaction commits.
test('create transport sees fsynced prebind without credentials or active authority', async t => {
  const r = await setup(t, { inject: async (event, { dir, a }) => {
    if (event === 'created') {
      const bytes = await readFile(join(dir, 'customer.json'), 'utf8'); const state = JSON.parse(bytes);
      const b = Object.values(state.bindings)[0]; assert.equal(b.state, 'creating'); assert.equal(b.upstreamID, undefined);
      assert.equal(a.extra.rr_quarantine.binding, b.id); assert.equal(a.extra.rr_quarantine.owner, state.owner);
      assert.equal(bytes.includes('synthetic-upstream'), false);
    }
  } });
  assert.equal((await r.connect('owner-a')).status, 200);
});

// Regression: guessed/misconfigured template ID crosses tenants or copies an
// active/default group before local ownership is acknowledged.
test('foreign workspace and grouped templates fail before duplicate effects', async t => {
  const r = await setup(t); r.config.quarantineTemplates.a['mimo:responses'] = 102;
  assert.equal((await r.connect('owner-a')).status, 409); assert.equal(r.records.size, 0);
  assert.equal(r.observations.some(x => x.path.endsWith('/duplicate')), false);
});
// Regression: the MiMo-only flag or provider impersonation leaks into the two
// unchanged native paths. Exercise actual request configuration through HTTP.
test('OpenRouter Responses and MiMo Messages retain their native configuration', async t => {
  const r = await setup(t);
  for (const [provider, protocol, platform, templateID, group] of [['openrouter','responses','openai',103,12], ['mimo','messages','anthropic',104,13]]) {
    const key = `${provider}:${protocol}`;
    r.templates.set(templateID, { ...structuredClone(stockEmptyAccount), id: templateID, name: 'rr-sub2-spike-20260930-template', type: 'apikey', platform, status: 'inactive', schedulable: false, group_ids: [], extra: { rr_quarantine_template: { workspace: 'a', provider, protocol } } });
    r.workspaces.a.groups[key] = group; r.config.quarantineTemplates.a[key] = templateID; r.config.credentialProfiles.a[key] = 'synthetic-upstream';
    assert.equal((await r.call('owner-a', 'POST', '/accounts', { provider, protocol })).status, 200);
    const a = [...r.records.values()].at(-1); assert.equal(a.platform, platform); assert.equal(Object.hasOwn(a.extra, 'openai_preserve_compatible_reasoning'), false);
    if (platform === 'openai') { assert.equal(a.extra.openai_responses_mode, 'force_responses'); assert.equal(a.extra.openai_passthrough, true); }
    else { assert.equal(a.extra.anthropic_passthrough, true); assert.equal(Object.hasOwn(a.extra, 'openai_responses_mode'), false); }
  }
});

// Regression: failed promotion/compensation leaves other capability holders able
// to route an uncertain engine account; server-owned workspace authority fences.
test('uncertain promotion with unavailable compensation suspends workspace durably', async t => {
  let promoting = false;
  const r = await setup(t, { inject: async (event, { body }) => {
    if (event === 'updated' && body.schedulable === true) { promoting = true; return '503'; }
    if (event === 'updated' && promoting && body.schedulable === false) return '503';
  } });
  assert.equal((await r.connect('owner-a')).status, 502); assert.equal(r.workspaces.a.suspended, true);
  assert.ok(r.authorityChanges.includes('a'));
  assert.equal((await r.call('owner-a', 'GET')).status, 403);
  r.workspaces.a.suspended = false; await customerAdapter(r.config); assert.equal(r.workspaces.a.suspended, true);
});

// Regression: upgrading leaves the old active ambiguous orphan reachable while
// refusing to adopt it; legacy uncertain intents must suspend workspace routing.
test('legacy orphan intent fences workspace on startup without adoption or admin IO', async t => {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-legacy-fence-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const statePath = join(dir, 'customer.json');
  await writeFile(statePath, JSON.stringify({ schema: 1, bindings: { old: { id: 'old', workspace: 'a', state: 'recovery_required', provider: 'mimo', protocol: 'responses' } } }));
  const workspaces = { a: { members: { owner: 'owner' }, suspended: false } }, revoked = [];
  const adapter = await customerAdapter({ statePath, workspaces, admin: new AdminAPI({ baseURL: 'https://unused.invalid', adminKey: 'synthetic-only' }), onAuthorityChange: workspace => revoked.push(workspace) });
  assert.equal(workspaces.a.suspended, true); assert.deepEqual(revoked, ['a']);
  await assert.rejects(adapter.operate({ workspace: 'a', user: 'owner' }, 'list'), { status: 403 });
  workspaces.a.suspended = false;
  await assert.rejects(adapter.reconcile({ workspace: 'a', user: 'owner' }, 'old', 'complete'), { status: 404 });
});

// Regression: revocation awaits can remove membership/suspend the workspace after
// the initial check, yet the adapter still sends an administrative mutation.
test('membership changes during authority revocation stop subsequent admin mutations', async t => {
  for (const action of ['pause', 'update', 'delete', 'replace']) {
    const r = await setup(t, { revoke: async (workspaces, workspace) => { delete workspaces[workspace].members.owner; } });
    const account = await (await r.connect('owner-a')).json(); const before = r.observations.length;
    const path = `/accounts/${account.id}${['pause','replace'].includes(action) ? '/' + action : ''}`;
    const method = action === 'delete' ? 'DELETE' : action === 'update' ? 'PUT' : 'POST';
    assert.equal((await r.call('owner-a', method, path, action === 'update' ? { concurrency: 1 } : undefined)).status, 403);
    assert.ok(r.observations.slice(before).every(x => x.method === 'GET'));
    assert.equal(r.records.size, 1); const record = [...r.records.values()][0];
    assert.equal(record.status, 'active'); assert.equal(record.concurrency, 2);
  }
});

// Offline tests override only the admin transport: no sockets, UID changes or
// inference. The fixture is independent source-derived stock JSON (see REPORT).
async function offlineLab(t, { hook = async () => {}, ambiguous = false } = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-offline-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const workspaces = { a: { members: { owner: 'owner', member: 'member' }, groups: { 'mimo:responses': 11 } } };
  const records = new Map(), trace = [], revoked = []; let template = structuredClone(stockEmptyAccount), next = 1;
  const admin = new AdminAPI({ baseURL: 'https://unused.invalid', adminKey: 'synthetic-only' });
  const config = { statePath: join(dir, 'customer.json'), admin, workspaces,
    credentialProfiles: { a: { 'mimo:responses': 'synthetic-only' } }, quarantineTemplates: { a: { 'mimo:responses': 101 } },
    onAuthorityChange: async workspace => { revoked.push(workspace); await hook('revoked', { workspaces, config, records }); } };
  admin.call = async (method, path, body) => {
    trace.push({ method, path, body: structuredClone(body) }); let event, dto;
    if (path.startsWith('/accounts?page=')) { event = 'list'; dto = { items: [...records.values()].map(stockWire), total: records.size }; }
    else if (path.startsWith('/accounts/data?')) { event = 'export'; dto = { accounts: [...records.values()] }; }
    else if (path === '/accounts/101/duplicate') {
      event = 'duplicate'; const record = { ...structuredClone(template), id: next++, name: template.name + ' (Copy)', status: 'active', schedulable: false };
      records.set(record.id, record); dto = stockWire(record);
    } else if (path === '/accounts/101') {
      event = method === 'GET' ? 'template-get' : 'template-put';
      if (body) Object.assign(template, structuredClone(body)); dto = stockWire(template);
    } else {
      const id = Number(path.split('/')[2]); const record = records.get(id);
      if (!record) throw Object.assign(Error('missing'), { code: 'admin_http_404', status: 502 });
      if (method === 'DELETE') { event = 'delete'; records.delete(id); dto = {}; }
      else {
        if (body) Object.assign(record, structuredClone(body));
        event = !body ? 'account-get' : body.schedulable === true ? 'schedule' : body.schedulable === false ? 'unschedule' : body.group_ids?.length ? 'group-attach' : body.status === 'active' ? 'activate' : 'account-put';
        dto = stockWire(record);
      }
    }
    await hook(event, { dto, body, workspaces, config, records, trace });
    if (ambiguous && event === 'duplicate') throw Object.assign(Error('ambiguous'), { code: 'admin_http_503', status: 502 });
    return dto;
  };
  const adapter = await customerAdapter(config), identity = { workspace: 'a', user: 'owner' };
  return { adapter, identity, workspaces, config, records, trace, revoked,
    connect: () => adapter.operate(identity, 'connect', null, { provider: 'mimo', protocol: 'responses' }) };
}

test('offline boundary authentic omitted-group fixture completes stock roundtrip', async t => {
  // This literal fixture has no group metadata; the rejected candidate required
  // arrays and failed at template GET, before duplicate (independent red oracle).
  for (const key of ['group_ids', 'groups', 'account_groups']) assert.equal(Object.hasOwn(stockEmptyAccount, key), false);
  const r = await offlineLab(t); const account = await r.connect();
  assert.equal(account.status, 'active'); assert.equal(r.records.get(1).schedulable, true);
  assert.deepEqual(r.records.get(1).group_ids, [11]);
  assert.equal((await r.adapter.operate(r.identity, 'read', account.id)).id, account.id);
  assert.equal((await r.adapter.operate(r.identity, 'list')).length, 1);
  await r.adapter.operate(r.identity, 'pause', account.id);
  await r.adapter.operate(r.identity, 'delete', account.id); assert.equal(r.records.size, 0);
  assert.equal(r.trace.filter(x => x.path.endsWith('/duplicate')).length, 1);
});

test('offline boundary authentic omitted-group fixture reconciles full stock list and get', async t => {
  for (const decision of ['retire', 'complete']) {
    const r = await offlineLab(t, { ambiguous: true }); await assert.rejects(r.connect(), { code: 'admin_http_503' });
    assert.equal(r.records.get(1).schedulable, false);
    const restart = await customerAdapter(r.config), [intent] = await restart.recovery();
    const result = await restart.reconcile(r.identity, intent.id, decision);
    if (decision === 'retire') { assert.equal(result.retired, true); assert.equal(r.records.size, 0); }
    else { assert.equal(result.status, 'active'); assert.equal(r.records.get(1).schedulable, true); }
    assert.equal(r.trace.filter(x => x.path.endsWith('/duplicate')).length, 1);
    assert.ok(r.trace.some(x => x.path.includes('lite=false')));
  }
});

test('offline boundary actual in-flight group remap compensates at every promotion await', async t => {
  for (const stage of ['duplicate', 'group-attach', 'activate', 'schedule']) {
    let changed = false;
    const r = await offlineLab(t, { hook: async (event, { workspaces }) => {
      if (event === stage && !changed) { workspaces.a.groups['mimo:responses'] = 22; changed = true; }
    } });
    await assert.rejects(r.connect(), { code: 'authority_changed' }); assert.equal(changed, true);
    const record = r.records.get(1); assert.equal(record.schedulable, false); assert.equal(record.status, 'inactive'); assert.deepEqual(record.group_ids, []);
    assert.deepEqual(await r.adapter.operate(r.identity, 'list'), []);
    assert.equal((await r.adapter.recovery())[0].state, 'recovery_required');
  }
});

test('offline boundary replaced deleted credentials templates and membership authority stop promotion', async t => {
  for (const change of ['replace-workspace', 'delete-workspace', 'role', 'replace-groups', 'credential', 'credential-scope', 'template', 'workspace-template', 'suspension']) {
    let changed = false;
    const r = await offlineLab(t, { hook: async (event, { workspaces, config }) => {
      if (event !== 'schedule' || changed) return; changed = true;
      if (change === 'replace-workspace') workspaces.a = structuredClone(workspaces.a);
      if (change === 'delete-workspace') delete workspaces.a;
      if (change === 'role') workspaces.a.members.owner = 'member';
      if (change === 'replace-groups') workspaces.a.groups = { ...workspaces.a.groups };
      if (change === 'credential') config.credentialProfiles.a['mimo:responses'] = 'synthetic-rotated';
      if (change === 'credential-scope') config.credentialProfiles.a = { ...config.credentialProfiles.a };
      if (change === 'template') config.quarantineTemplates.a['mimo:responses'] = 102;
      if (change === 'workspace-template') workspaces.a.quarantineTemplates = { 'mimo:responses': 102 };
      if (change === 'suspension') workspaces.a.suspended = true;
    } });
    await assert.rejects(r.connect(), e => ['authority_changed', 'membership_denied'].includes(e.code));
    assert.equal(r.records.get(1).schedulable, false); assert.deepEqual(r.records.get(1).group_ids, []);
  }
});

test('offline boundary authority changes during template and credential awaits prevent duplicate', async t => {
  for (const stage of ['credential', 'template-get', 'template-put']) {
    const r = await offlineLab(t, { hook: async (event, { config }) => {
      if (event === stage) config.quarantineTemplates.a['mimo:responses'] = 102;
    } });
    if (stage === 'credential') r.config.credentialProfiles.a['mimo:responses'] = async () => {
      r.workspaces.a.groups['mimo:responses'] = 22; return 'synthetic-only';
    };
    await assert.rejects(r.connect(), { code: 'authority_changed' });
    assert.equal(r.records.size, 0); assert.equal(r.trace.some(x => x.path.endsWith('/duplicate')), false);
  }
});

test('offline boundary remapped existing reads exports and mutations compensate before publication', async t => {
  for (const stage of ['account-get', 'export', 'revoked', 'account-put']) {
    let armed = false, changed = false;
    const r = await offlineLab(t, { hook: async (event, { workspaces }) => {
      if (armed && event === stage && !changed) { changed = true; workspaces.a.groups['mimo:responses'] = 22; }
    } });
    const account = await r.connect(); armed = true;
    const action = stage === 'export' ? 'export' : ['revoked', 'account-put'].includes(stage) ? 'update' : 'read';
    await assert.rejects(r.adapter.operate(r.identity, action, account.id, { concurrency: 1 }), { code: 'authority_changed' });
    assert.equal(r.records.get(1).schedulable, false); assert.deepEqual(r.records.get(1).group_ids, []);
  }
});

test('offline boundary contradictory null malformed or lite group authority never publishes', async t => {
  const changes = [a => { a.group_ids = null; }, a => { a.groups = null; }, a => { a.group_ids = 'bad'; },
    a => { a.group_ids = [11]; a.groups = [{ id: 22 }]; }, a => { a.group_ids = [11, 11]; },
    a => { a.account_groups = [{ account_id: a.id, group_id: 22 }]; },
    a => { a.group_ids = [11]; a.account_groups = [{ account_id: 999, group_id: 11 }]; },
    a => { delete a.credentials; delete a.extra; }, a => { a.groups = [null]; },
    a => { a.group_ids = [11]; a.account_groups = [{ account_id: a.id, group_id: 11, group: { id: 22 } }]; },
    a => { a.account_groups = [{ account_id: a.id, group_id: 11, account: { id: 999 } }]; },
    a => { a.account_groups = [{ account_id: a.id, group_id: 11, account: null }]; }];
  for (const stage of ['template-get', 'template-put', 'duplicate', 'schedule']) for (const change of changes) {
    let altered = false;
    const r = await offlineLab(t, { hook: async (event, { dto }) => { if (event === stage && !altered) { altered = true; change(dto); } } });
    await assert.rejects(r.connect()); assert.equal(altered, true);
    assert.equal([...r.records.values()].some(a => a.schedulable), false);
    if (stage.startsWith('template')) assert.equal(r.records.size, 0);
  }
});

test('offline boundary malformed lite recovery list and contradictory fetchOwned are refused', async t => {
  let corruptList = true;
  const r = await offlineLab(t, { ambiguous: true, hook: async (event, { dto }) => {
    if (event === 'list' && corruptList) { delete dto.items[0].credentials; delete dto.items[0].extra; }
  } });
  await assert.rejects(r.connect()); const [intent] = await r.adapter.recovery();
  await assert.rejects(r.adapter.reconcile(r.identity, intent.id, 'complete'), { code: 'account_dto_invalid' });
  assert.equal(r.records.get(1).schedulable, false); corruptList = false;
  const account = await r.adapter.reconcile(r.identity, intent.id, 'complete');
  r.records.get(1).account_groups = [{ account_id: 1, group_id: 22 }];
  await assert.rejects(r.adapter.operate(r.identity, 'read', account.id), { code: 'account_groups_conflict' });
  assert.equal(r.records.get(1).schedulable, false); assert.equal(r.workspaces.a.suspended, true); assert.ok(r.revoked.includes('a'));
});

test('offline boundary uncertain compensation fences current replaced authority durably', async t => {
  let changed = false;
  const r = await offlineLab(t, { hook: async (event, { workspaces }) => {
    if (event === 'schedule' && !changed) { changed = true; workspaces.a = { ...structuredClone(workspaces.a), groups: { 'mimo:responses': 22 } }; }
    if (changed && event === 'unschedule') throw Error('synthetic unreachable compensation');
  } });
  await assert.rejects(r.connect(), { code: 'authority_changed' });
  assert.equal(r.workspaces.a.suspended, true); assert.ok(r.revoked.includes('a'));
  r.workspaces.a.suspended = false; await customerAdapter(r.config); assert.equal(r.workspaces.a.suspended, true);
});

test('offline boundary recovery rechecks remaps during list get and promotion', async t => {
  for (const stage of ['list', 'account-get', 'group-attach', 'schedule']) {
    let armed = false, changed = false;
    const r = await offlineLab(t, { ambiguous: true, hook: async (event, { workspaces }) => {
      if (armed && event === stage && !changed) { changed = true; workspaces.a.groups['mimo:responses'] = 22; }
    } });
    await assert.rejects(r.connect()); const [intent] = await r.adapter.recovery(); armed = true;
    await assert.rejects(r.adapter.reconcile(r.identity, intent.id, 'complete'), { code: 'authority_changed' });
    assert.equal(changed, true); assert.equal(r.records.get(1).schedulable, false);
    assert.equal(r.trace.filter(x => x.path.endsWith('/duplicate')).length, 1);
  }
});

test('offline boundary replacement remap during old retirement compensates new account', async t => {
  let armed = false;
  const r = await offlineLab(t, { hook: async (event, { config }) => {
    if (armed && event === 'delete') config.credentialProfiles.a['mimo:responses'] = 'synthetic-rotated-again';
  } });
  const old = await r.connect(); r.config.credentialProfiles.a['mimo:responses'] = 'synthetic-rotated'; armed = true;
  await assert.rejects(r.adapter.operate(r.identity, 'replace', old.id), { code: 'authority_changed' });
  assert.equal(r.records.size, 1); assert.equal(r.records.get(2).schedulable, false); assert.deepEqual(r.records.get(2).group_ids, []);
  assert.equal(r.workspaces.a.suspended, true); assert.ok(r.revoked.includes('a'));
});

test('offline boundary replaced authority during failed compensation revocation remains fenced', async t => {
  let changed = false;
  const r = await offlineLab(t, { hook: async (event, { workspaces }) => {
    if (event === 'schedule') { changed = true; workspaces.a.groups['mimo:responses'] = 22; }
    if (changed && event === 'unschedule') throw Error('synthetic compensation failure');
    if (changed && event === 'revoked') workspaces.a = { ...structuredClone(workspaces.a), suspended: false };
  } });
  await assert.rejects(r.connect(), { code: 'authority_changed' }); assert.equal(r.workspaces.a.suspended, true);
});

test('offline boundary matching group representations and null redacted credentials are valid full DTOs', async t => {
  const r = await offlineLab(t, { hook: async (event, { dto }) => {
    if (event === 'template-get') dto.credentials = null;
    if (event === 'schedule') {
      dto.groups = [{ id: 11 }]; dto.account_groups = [{ account_id: dto.id, group_id: 11, group: { id: 11 } }];
    }
  } });
  assert.equal((await r.connect()).status, 'active');
});

test('offline boundary prepared template identity and scope mutation cannot duplicate', async t => {
  for (const change of [a => { a.id = 102; }, a => { a.type = 'oauth'; }, a => { a.platform = 'anthropic'; },
    a => { a.extra.rr_quarantine_template.workspace = 'b'; }, a => { a.extra.rr_quarantine.owner = 'foreign'; }]) {
    const r = await offlineLab(t, { hook: async (event, { dto }) => { if (event === 'template-put') change(dto); } });
    await assert.rejects(r.connect(), { code: 'quarantine_template_drift' });
    assert.equal(r.trace.some(x => x.path.endsWith('/duplicate')), false); assert.equal(r.records.size, 0);
  }
});

test('offline boundary acknowledged interrupted promotion retains explicit retire and complete recovery', async t => {
  for (const decision of ['retire', 'complete']) {
    const r = await offlineLab(t); const account = await r.connect();
    const state = JSON.parse(await readFile(r.config.statePath, 'utf8')); state.bindings[account.id].state = 'bound';
    await writeFile(r.config.statePath, JSON.stringify(state));
    const restart = await customerAdapter(r.config); assert.equal(r.workspaces.a.suspended, true);
    // Trusted operator clears the fence with routing stopped before recovery.
    r.workspaces.a.suspended = false; const result = await restart.reconcile(r.identity, account.id, decision);
    if (decision === 'retire') { assert.equal(result.retired, true); assert.equal(r.records.size, 0); }
    else { assert.equal(result.status, 'active'); assert.equal(r.records.get(1).schedulable, true); assert.deepEqual(r.records.get(1).group_ids, [11]); }
    assert.equal(r.trace.filter(x => x.path.endsWith('/duplicate')).length, 1);
  }
});
