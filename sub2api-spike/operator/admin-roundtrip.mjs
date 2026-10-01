// COORDINATOR ONLY. Actual admin lifecycle; effects must be independently observed.
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { AdminAPI, customerAdapter } from '../customer.mjs';
import { loadFixtureConfiguration, privateFile, templatePlan, validateTemplate } from './live-setup.mjs';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const privateDir = '/private', baseURL = 'http://sub2api:8080';
export async function main() {
  const receipt = { schema: 1, evidence_kind: 'synthetic-container', status: 'FAIL', stage: 'trusted_fixtures', node: process.version, upstream_requests: null, capability_metadata_writes: null, telemetry: 'NOT_RUN', duration_ms: 0, results: [], exposed_fields: [], limitation: 'Actual admin API only; not native gateway, real Actions, OAuth or membership/SSO proof.' };
  const started = Date.now();
  let baseline, observation;
  const privateJSON = async (name, value) => writeFile(join(privateDir, name), JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  async function api(method, path, body, auth) {
    const r = await fetch(`${baseURL}/api/v1${path}`, { method, headers: { 'content-type': 'application/json', ...(auth ? { authorization: `Bearer ${auth}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(10000) });
    if (!r.ok) throw Error(`HTTP_${r.status}`); const j = await r.json(); if (j.code !== 0) throw Error('API_ERROR'); return j.data;
  }
  try {
    // Journal refuses ambiguous/rerun setup; inspect private state before a new run.
    await writeFile(join(privateDir, 'roundtrip-started.json'), JSON.stringify({ started }), { flag: 'wx', mode: 0o600 });
    receipt.stage = 'trusted_fixtures';
    const fixtures = await loadFixtureConfiguration(privateDir);
    const key = { key: (await privateFile(privateDir, 'admin.key')).trim() };
    if (!key.key) throw Error('ADMIN_KEY_MISSING');
    const admin = new AdminAPI({ baseURL, adminKey: key.key, installation: fixtures.installation }); const workspaces = {};
    observation = JSON.parse(await privateFile(privateDir, 'observation.json'));
    if (!/^[a-f0-9]{32}$/.test(observation.captureID) || observation.endpoint !== 'http://probe-observer:8791') throw Error('OBSERVATION_CONFIG_DENIED');
    baseline = await observe('snapshot');
    if (baseline.engineDigest !== fixtures.installation.engineDigest) throw Error('OBSERVED_ENGINE_MISMATCH');
    for (const t of templatePlan(fixtures.owner).templates) {
      const id = fixtures.quarantineTemplates[t.workspace][t.key];
      if (validateTemplate(await admin.call('GET', `/accounts/${id}`), t, fixtures.owner) !== id) throw Error('FIXTURE_ID_DRIFT');
    }
    receipt.stage = 'groups_users_keys';
    for (const workspace of ['a', 'b']) {
      const group = await admin.call('POST', '/groups', { name: `rr-sub2-spike-20260930-${fixtures.owner}-${workspace}-responses`, platform: 'openai', rate_multiplier: 1, is_exclusive: true, subscription_type: 'standard', fallback_group_id: null, fallback_group_id_on_invalid_request: null });
      if (!Number.isSafeInteger(group?.id) || group.id < 1) throw Error('GROUP_ACK_UNKNOWN');
      workspaces[workspace] = { fixtureOwner: fixtures.owner, groupName: group.name, members: { owner: 'owner', member: 'member' }, groups: { 'mimo:responses': group.id } };
      await privateJSON('roundtrip-workspaces.json', workspaces);
      const password = `synthetic-user-password-${fixtures.owner}-${workspace}`;
      const user = await admin.call('POST', '/users', { email: `rr-sub2-spike-20260930-${fixtures.owner}-${workspace}@example.invalid`, password, role: 'user', balance: 100, concurrency: 2, allowed_groups: [group.id], restrict_public_groups: true });
      if (!Number.isSafeInteger(user?.id) || user.id < 1) throw Error('USER_ACK_UNKNOWN');
      workspaces[workspace].userID = user.id; workspaces[workspace].email = user.email;
      await privateJSON('roundtrip-workspaces.json', workspaces);
      const userLogin = await api('POST', '/auth/login', { email: user.email, password });
      const access = await api('POST', '/keys', { name: `rr-sub2-spike-20260930-${fixtures.owner}-${workspace}`, group_id: group.id, custom_key: `synthetic-private-gateway-key-${fixtures.owner}-${workspace}` }, userLogin.access_token);
      if (!Number.isSafeInteger(access?.id) || access.id < 1 || typeof access.key !== 'string') throw Error('KEY_ACK_UNKNOWN');
      workspaces[workspace].keyID = access.id; workspaces[workspace].keyName = `rr-sub2-spike-20260930-${fixtures.owner}-${workspace}`;
      await privateJSON('roundtrip-workspaces.json', workspaces);
      await writeFile(join(privateDir, `workspace-${workspace}.key`), access.key, { mode: 0o600 });
      await privateJSON('roundtrip-workspaces.json', workspaces);
    }
    receipt.stage = 'customer_adapter';
    const adapter = await customerAdapter({ statePath: '/state/customer-roundtrip.json', admin, workspaces, quarantineTemplates: fixtures.quarantineTemplates, credentialProfiles: { a: { 'mimo:responses': 'synthetic-upstream-a' }, b: { 'mimo:responses': 'synthetic-upstream-b' } } });
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
    receipt.stage = 'observed_effects';
    const final = await observe('drain');
    const effects = observedEffects(baseline, final);
    receipt.upstream_requests = effects.requests; receipt.capability_metadata_writes = effects.writes; receipt.telemetry = 'OBSERVED';
    if (effects.requests !== 0 || effects.writes !== 0) throw Error('UNEXPECTED_PROBE_EFFECTS');
    receipt.status = 'PASS'; receipt.stage = 'done';
    for (const id of ['C01', 'C02', 'C03', 'C07', 'D05']) receipt.results.push({ id, status: 'PASS', upstream_requests: receipt.upstream_requests, capability_metadata_writes: receipt.capability_metadata_writes, limitation: receipt.limitation });
  } catch (e) { receipt.failure_code = /^[A-Z_0-9]+$/.test(e.message) ? e.message : 'ADMIN_ROUNDTRIP_FAILURE'; process.exitCode = 1; }
  finally {
    // On lifecycle failure still attempt a measured drain, retaining FAIL. Missing
    // telemetry stays unknown, never zero; no timer is a delayed-work drain proof.
    if (baseline && receipt.telemetry !== 'OBSERVED') {
      try { const effects = observedEffects(baseline, await observe('drain')); receipt.upstream_requests = effects.requests; receipt.capability_metadata_writes = effects.writes; receipt.telemetry = 'OBSERVED'; } catch { receipt.telemetry = 'NOT_RUN'; }
    }
    receipt.duration_ms = Date.now() - started; await writeFile('/receipts/admin-roundtrip.json', JSON.stringify(receipt, null, 2) + '\n'); }

  async function observe(operation) {
    const r = await fetch(`${observation.endpoint}/${operation}`, { method: operation === 'drain' ? 'POST' : 'GET', headers: { 'content-type': 'application/json' }, ...(operation === 'drain' ? { body: JSON.stringify({ captureID: observation.captureID }) } : {}), redirect: 'error', signal: AbortSignal.timeout(30000) });
    if (!r.ok) throw Error('OBSERVATION_UNAVAILABLE');
    const data = await r.json();
    if (data.captureID !== observation.captureID) throw Error('OBSERVATION_CAPTURE_MISMATCH');
    return data;
  }
}
// Counters are cumulative instrumented transport and DB-write observations.
// Independent boundary must drain queued work and acknowledge completion.
export function observedEffects(before, after) {
  const valid = c => c && typeof c.captureID === 'string' && /^[a-f0-9]{32}$/.test(c.captureID) &&
    /^sha256:[a-f0-9]{64}$/.test(c.engineDigest ?? '') &&
    ['requests', 'capabilityMetadataWrites'].every(k => Number.isSafeInteger(c[k]) && c[k] >= 0);
  if (!valid(before) || !valid(after) || after.drained !== true || after.captureID !== before.captureID || after.engineDigest !== before.engineDigest ||
      after.requests < before.requests || after.capabilityMetadataWrites < before.capabilityMetadataWrites) throw Error('OBSERVATION_INVALID');
  return { requests: after.requests - before.requests, writes: after.capabilityMetadataWrites - before.capabilityMetadataWrites };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) await main();
