// TRUSTED CONTROL CONTAINER ONLY. Actual Sub2API API roundtrip, zero model requests.
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { AdminAPI, customerAdapter } from '../customer.mjs';
const privateDir = '/private', baseURL = 'http://sub2api:8080';
const receipt = { schema: 1, evidence_kind: 'synthetic-container', status: 'FAIL', stage: 'login', node: process.version, upstream_requests: 0, duration_ms: 0, results: [], exposed_fields: [], limitation: 'Actual admin API only; not native gateway, real Actions, OAuth or membership/SSO proof.' };
const started = Date.now();
const privateJSON = async (name, value) => writeFile(join(privateDir, name), JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
async function api(method, path, body, auth) {
  const r = await fetch(`${baseURL}/api/v1${path}`, { method, headers: { 'content-type': 'application/json', ...(auth ? { authorization: `Bearer ${auth}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(10000) });
  if (!r.ok) throw Error(`HTTP_${r.status}`); const j = await r.json(); if (j.code !== 0) throw Error('API_ERROR'); return j.data;
}
try {
  // Journal refuses ambiguous/rerun setup; inspect private state before a new run.
  await writeFile(join(privateDir, 'roundtrip-started.json'), JSON.stringify({ started }), { flag: 'wx', mode: 0o600 });
  const login = await api('POST', '/auth/login', JSON.parse(await readFile(join(privateDir, 'login.json'), 'utf8')));
  if (typeof login.access_token !== 'string') throw Error('LOGIN_TOKEN_MISSING');
  receipt.stage = 'admin_key'; const key = await api('POST', '/admin/settings/admin-api-key/regenerate', {}, login.access_token);
  if (typeof key.key !== 'string') throw Error('ADMIN_KEY_MISSING');
  await writeFile(join(privateDir, 'admin.key'), key.key, { mode: 0o600 });
  const admin = new AdminAPI({ baseURL, adminKey: key.key }); const workspaces = {};
  receipt.stage = 'groups_users_keys';
  for (const [i, workspace] of ['a', 'b'].entries()) {
    const group = await admin.call('POST', '/groups', { name: `rr-sub2-spike-20260930-${workspace}-responses`, platform: 'openai', rate_multiplier: 1, is_exclusive: true, subscription_type: 'standard', fallback_group_id: null, fallback_group_id_on_invalid_request: null });
    workspaces[workspace] = { members: { owner: 'owner', member: 'member' }, groups: { 'mimo:responses': group.id } };
    await privateJSON('roundtrip-workspaces.json', workspaces);
    const password = `synthetic-user-password-${workspace}-20260930`;
    const user = await admin.call('POST', '/users', { email: `rr-sub2-spike-20260930-${workspace}@example.invalid`, password, role: 'user', balance: 100, concurrency: 2, allowed_groups: [group.id], restrict_public_groups: true });
    const userLogin = await api('POST', '/auth/login', { email: user.email, password });
    const access = await api('POST', '/keys', { name: `rr-sub2-spike-20260930-${workspace}`, group_id: group.id, custom_key: `synthetic-private-gateway-key-${workspace}-20260930` }, userLogin.access_token);
    await writeFile(join(privateDir, `workspace-${workspace}.key`), access.key, { mode: 0o600 });
    workspaces[workspace].userID = user.id; workspaces[workspace].keyID = access.id;
    await privateJSON('roundtrip-workspaces.json', workspaces);
  }
  receipt.stage = 'customer_adapter';
  const adapter = await customerAdapter({ statePath: '/state/customer-roundtrip.json', admin, workspaces, credentialProfiles: { a: { 'mimo:responses': 'synthetic-upstream-a' }, b: { 'mimo:responses': 'synthetic-upstream-b' } } });
  const a = await adapter.operate({ workspace: 'a', user: 'owner' }, 'connect', null, { provider: 'mimo', protocol: 'responses' });
  const b = await adapter.operate({ workspace: 'b', user: 'owner' }, 'connect', null, { provider: 'mimo', protocol: 'responses' });
  const listA = await adapter.operate({ workspace: 'a', user: 'owner' }, 'list');
  const listB = await adapter.operate({ workspace: 'b', user: 'owner' }, 'list');
  if (listA.length !== 1 || listA[0].id !== a.id || listB.length !== 1 || listB[0].id !== b.id) throw Error('TENANT_LIST_FAILURE');
  const state = JSON.parse(await readFile('/state/customer-roundtrip.json', 'utf8'));
  // Inspect exposed credential FIELD NAMES only; no values/raw API exports escape.
  const raw = await admin.call('GET', `/accounts/${state.bindings[a.id].upstreamID}`);
  receipt.exposed_fields = Object.keys(raw.credentials ?? {}).sort();
  await adapter.operate({ workspace: 'a', user: 'owner' }, 'update', a.id, { concurrency: 1 });
  await adapter.operate({ workspace: 'a', user: 'owner' }, 'pause', a.id);
  const exported = await adapter.operate({ workspace: 'a', user: 'owner' }, 'export', a.id);
  if (JSON.stringify(exported).includes('synthetic-upstream') || JSON.stringify(exported).includes(key.key)) throw Error('CUSTODY_FAILURE');
  for (const action of ['read', 'update', 'pause', 'delete', 'refresh', 'export']) {
    let denied = false; try { await adapter.operate({ workspace: 'b', user: 'owner' }, action, a.id, { concurrency: 1 }); } catch (e) { denied = e.status === 404; }
    if (!denied) throw Error('TENANT_FAILURE');
  }
  for (const action of ['update', 'pause', 'delete', 'refresh', 'export']) {
    let denied = false; try { await adapter.operate({ workspace: 'a', user: 'member' }, action, a.id, { concurrency: 1 }); } catch (e) { denied = e.status === 403; }
    if (!denied) throw Error('ROLE_FAILURE');
  }
  await adapter.operate({ workspace: 'a', user: 'owner' }, 'delete', a.id); await adapter.operate({ workspace: 'b', user: 'owner' }, 'delete', b.id);
  receipt.status = 'PASS'; receipt.stage = 'done';
  for (const id of ['C01', 'C02', 'C03', 'C07', 'D05']) receipt.results.push({ id, status: 'PASS', upstream_requests: 0, limitation: receipt.limitation });
} catch (e) { receipt.failure_code = /^[A-Z_0-9]+$/.test(e.message) ? e.message : 'ADMIN_ROUNDTRIP_FAILURE'; process.exitCode = 1; }
finally { receipt.duration_ms = Date.now() - started; await writeFile('/receipts/admin-roundtrip.json', JSON.stringify(receipt, null, 2) + '\n'); }
