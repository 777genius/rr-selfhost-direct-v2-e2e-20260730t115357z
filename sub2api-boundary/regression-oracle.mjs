// Independent reviewer-style red/green observations. No sockets, UID changes,
// real credentials or inference. Optional module path selects the prior bytes.
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
const { AdminAPI, customerAdapter } = await import(process.argv[2] ? pathToFileURL(resolve(process.argv[2])).href : '../sub2api-spike/customer.mjs');
const fixture = JSON.parse(await readFile(new URL('./fixtures/stock-empty-account.json', import.meta.url), 'utf8'));
const observations = {};
const admin = new AdminAPI({ baseURL: 'https://unused.invalid', adminKey: 'synthetic-only' });
let duplicateCalls = 0;
admin.call = async (method, path, body) => {
  if (method === 'GET') return structuredClone(fixture);
  if (method === 'PUT') {
    const dto = { ...structuredClone(fixture), ...body }; delete dto.group_ids; return dto;
  }
  duplicateCalls++; return { ...fixture, id: 1, name: 'rr-sub2-spike-20260930-owned (Copy)', status: 'active' };
};
try {
  await admin.createQuarantined({ name: 'rr-sub2-spike-20260930-owned', platform: 'openai', type: 'apikey', extra: { rr_quarantine: { binding: 'synthetic-intent' } } },
    { templateID: 101, workspace: 'a', provider: 'mimo', protocol: 'responses', intentID: 'synthetic-intent' });
  observations.stock_empty_template = { PASS: true, duplicate_calls: duplicateCalls };
} catch (e) { observations.stock_empty_template = { PASS: false, error: e.code, duplicate_calls: duplicateCalls }; }
const directory = await mkdtemp(join(tmpdir(), 'rr-sub2-independent-oracle-'));
try {
  let record, remapped = false;
  const workspaces = { a: { members: { owner: 'owner' }, groups: { 'mimo:responses': 11 } } };
  const controlledAdmin = {
    async createQuarantined(body) { record = { ...body, id: 1, name: body.name + ' (Copy)', status: 'active', schedulable: false, group_ids: [] }; return structuredClone(record); },
    async call(method, path, body) {
      if (body) Object.assign(record, body);
      if (body?.group_ids?.length && !remapped) { workspaces.a.groups['mimo:responses'] = 22; remapped = true; }
      return structuredClone(record);
    }
  };
  const adapter = await customerAdapter({ statePath: join(directory, 'routing.json'), admin: controlledAdmin, workspaces,
    credentialProfiles: { a: { 'mimo:responses': 'synthetic-only' } } });
  let result, error;
  try { result = await adapter.operate({ workspace: 'a', user: 'owner' }, 'connect', null, { provider: 'mimo', protocol: 'responses' }); }
  catch (e) { error = e.code; }
  observations.inflight_routing_remap = { PASS: error === 'authority_changed' && record.schedulable === false && record.group_ids.length === 0,
    result: result?.status ?? null, error: error ?? null, schedulable: record.schedulable,
    engine_group_ids: record.group_ids, current_workspace_group: workspaces.a.groups['mimo:responses'] };
} finally { await rm(directory, { recursive: true, force: true }); }
const PASS = Object.values(observations).every(x => x.PASS);
console.log(JSON.stringify({ schema: 1, PASS, observations, limits: 'Offline adapter control flow only; no engine/DB/scheduler/kernel/inference claim.' }, null, 2));
process.exitCode = PASS ? 0 : 1;
