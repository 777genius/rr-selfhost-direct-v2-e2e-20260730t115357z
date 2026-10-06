// Independent adapter observations only. No sockets, credentials, CLI, or UID changes.
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { AdminAPI, customerAdapter } from '../.spike-inputs/candidate/sub2api-spike/customer.mjs';
const directory = await mkdtemp(new URL('./scratch-', import.meta.url).pathname);
const observations = {};
try {
  let calls = 0;
  const admin = new AdminAPI({ baseURL: 'https://unused.invalid', adminKey: 'synthetic-only' });
  admin.call = async () => { calls++; throw Error('Unexpected remote call'); };
  const workspaces = { a: { members: { owner: 'owner' }, groups: { 'mimo:responses': 11 } } };
  const adapter = await customerAdapter({ statePath: join(directory, 'missing.json'), admin, workspaces,
    credentialProfiles: { a: { 'mimo:responses': 'synthetic-only' } } });
  await assert.rejects(adapter.operate({ workspace: 'a', user: 'owner' }, 'connect', null,
    { provider: 'mimo', protocol: 'responses' }), { code: 'quarantine_template_required' });
  assert.equal(calls, 0);
  observations.roundtrip_configuration_without_templates = { result: 'quarantine_template_required', admin_calls: calls };

  // These wire shapes follow the inspected standard-mode Go DTO's omitempty
  // fields. Transport overrides isolate each check; they do not implement a DB.
  observations.stock_omitempty = {};
  for (const stage of ['get', 'prepared', 'duplicate']) {
    const trace = []; let prepared, duplicate;
    const omitGroups = a => { const copy = structuredClone(a); delete copy.group_ids; delete copy.groups; return copy; };
    const dtoAdmin = new AdminAPI({ baseURL: 'https://unused.invalid', adminKey: 'synthetic-only' });
    dtoAdmin.call = async (method, path, body) => {
      trace.push({ method, path });
      if (method === 'GET' && path === '/accounts/101') {
        const a = { id: 101, name: 'rr-sub2-spike-20260930-template', type: 'apikey', platform: 'openai', status: 'inactive', schedulable: false,
          group_ids: [], extra: { rr_quarantine_template: { workspace: 'a', provider: 'mimo', protocol: 'responses' } } };
        return stage === 'get' ? omitGroups(a) : a;
      }
      if (method === 'PUT' && path === '/accounts/101') {
        prepared = { ...structuredClone(body), id: 101, schedulable: false };
        return stage === 'prepared' ? omitGroups(prepared) : structuredClone(prepared);
      }
      if (method === 'POST' && path === '/accounts/101/duplicate') {
        duplicate = omitGroups({ ...prepared, id: 1, name: prepared.name + ' (Copy)', status: 'active' });
        return structuredClone(duplicate);
      }
      if (method === 'GET' && path.startsWith('/accounts?page=')) return { items: [structuredClone(duplicate)], total: 1 };
      throw Error('Unexpected transport invocation');
    };
    const dtoAdapter = await customerAdapter({ statePath: join(directory, `dto-${stage}.json`), admin: dtoAdmin,
      workspaces: { a: { members: { owner: 'owner' }, groups: { 'mimo:responses': 11 }, quarantineTemplates: { 'mimo:responses': 101 } } },
      credentialProfiles: { a: { 'mimo:responses': 'synthetic-only' } } });
    const error = { get: 'quarantine_template_denied', prepared: 'quarantine_template_drift', duplicate: 'quarantine_invalid' }[stage];
    await assert.rejects(dtoAdapter.operate({ workspace: 'a', user: 'owner' }, 'connect', null, { provider: 'mimo', protocol: 'responses' }), { code: error });
    const recovery = await dtoAdapter.recovery();
    assert.equal(recovery.length, 1); assert.equal(recovery[0].upstreamID, null);
    observations.stock_omitempty[stage] = { error, duplicate_calls: trace.filter(x => x.path.endsWith('/duplicate')).length, recovery_state: recovery[0].state, upstream_id: recovery[0].upstreamID };
    if (stage === 'duplicate') {
      await assert.rejects(dtoAdapter.reconcile({ workspace: 'a', user: 'owner' }, recovery[0].id, 'retire'), { code: 'recovery_quarantine_denied' });
      observations.stock_omitempty.reconcile = { error: 'recovery_quarantine_denied', duplicate_calls: trace.filter(x => x.path.endsWith('/duplicate')).length };
    }
  }

  let record, remapped = false;
  const routingWorkspaces = { a: { members: { owner: 'owner' }, groups: { 'mimo:responses': 11 } } };
  const controlledAdmin = {
    async createQuarantined(body) { record = { ...body, id: 1, name: body.name + ' (Copy)', status: 'active', schedulable: false, group_ids: [] }; return structuredClone(record); },
    async call(method, path, body) {
      if (body) Object.assign(record, body);
      if (body?.group_ids?.length && !remapped) {
        routingWorkspaces.a.groups['mimo:responses'] = 22;
        remapped = true;
      }
      return structuredClone(record);
    }
  };
  const routingAdapter = await customerAdapter({ statePath: join(directory, 'routing.json'), admin: controlledAdmin,
    workspaces: routingWorkspaces, credentialProfiles: { a: { 'mimo:responses': 'synthetic-only' } } });
  const result = await routingAdapter.operate({ workspace: 'a', user: 'owner' }, 'connect', null,
    { provider: 'mimo', protocol: 'responses' });
  assert.equal(result.status, 'active'); assert.equal(record.schedulable, true);
  assert.deepEqual(record.group_ids, [11]); assert.equal(routingWorkspaces.a.groups['mimo:responses'], 22);
  await assert.rejects(routingAdapter.operate({ workspace: 'a', user: 'owner' }, 'read', result.id), { code: 'group_drift' });
  observations.routing_remap_during_promotion = { connect_status: result.status, schedulable: record.schedulable,
    engine_group_ids: record.group_ids, current_workspace_group: 22, subsequent_read: 'group_drift' };
  console.log(JSON.stringify({ schema: 1, observations, limits: 'Offline doubles observe adapter control flow only; no engine/DB/scheduler/kernel claim.' }, null, 2));
} finally { await rm(directory, { recursive: true, force: true }); }
