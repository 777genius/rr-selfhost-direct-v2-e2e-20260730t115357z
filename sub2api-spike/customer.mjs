import http from 'node:http';
import { randomBytes } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { atomicJSON, loadJSON, serial, fault, send, readJSON, bearer } from './util.mjs';
export const providerProfiles = Object.freeze({
  'mimo:responses': Object.freeze({ platform: 'openai', baseURL: 'https://token-plan-sgp.xiaomimimo.com/v1', model: 'mimo-v2.6-pro' }),
  'mimo:messages': Object.freeze({ platform: 'anthropic', baseURL: 'https://token-plan-sgp.xiaomimimo.com/anthropic', model: 'mimo-v2.6-pro' }),
  'openrouter:responses': Object.freeze({ platform: 'openai', baseURL: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4.1' })
});
export function safeProviderURL(value) {
  let u; try { u = new URL(value); } catch { throw fault(400, 'unsafe_url'); }
  if (u.username || u.password || u.hash || u.search || !Object.values(providerProfiles).some(p => p.baseURL === u.href.replace(/\/$/, ''))) throw fault(400, 'unsafe_url');
  return u.href.replace(/\/$/, '');
}
// Only trusted stock full account DTOs have these non-omitempty authority
// fields. Missing group slices mean empty in this DTO, never in arbitrary/lite
// projections. Present null/malformed/conflicting slices are always rejected.
function stockGroups(a) {
  const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  if (!object(a) || !Number.isSafeInteger(a.id) || a.id < 1 ||
      !['name', 'platform', 'type', 'status'].every(k => typeof a[k] === 'string') || typeof a.schedulable !== 'boolean' ||
      !Object.hasOwn(a, 'credentials') || !(a.credentials === null || object(a.credentials)) ||
      !Object.hasOwn(a, 'extra') || !(a.extra === null || object(a.extra))) throw fault(502, 'account_dto_invalid');
  const validID = x => Number.isSafeInteger(x) && x > 0;
  const slices = [];
  for (const key of ['group_ids', 'groups', 'account_groups']) if (Object.hasOwn(a, key)) {
    if (!Array.isArray(a[key])) throw fault(502, 'account_groups_invalid');
    const ids = a[key].map(x => {
      if (key === 'group_ids') return x;
      if (!object(x)) throw fault(502, 'account_groups_invalid');
      if (key === 'groups') return x.id;
      if (x.account_id !== a.id || Object.hasOwn(x, 'group') && (!object(x.group) || x.group.id !== x.group_id) ||
          Object.hasOwn(x, 'account') && (!object(x.account) || x.account.id !== a.id)) throw fault(502, 'account_groups_invalid');
      return x.group_id;
    });
    if (!ids.every(validID) || new Set(ids).size !== ids.length) throw fault(502, 'account_groups_invalid');
    slices.push(ids.sort((x, y) => x - y));
  }
  // group_ids is canonical in stock. A nonempty secondary representation cannot
  // coexist with its omission: that contradicts the full DTO's empty slice.
  const ids = Object.hasOwn(a, 'group_ids') ? slices[0] : [];
  if (slices.some(x => !isDeepStrictEqual(x, ids))) throw fault(502, 'account_groups_conflict');
  return ids;
}
// Installation input is supplied only by sealed server/operator configuration.
// It is not proof by itself: coordinator binds it to observed patched-image gates.
export const probePatchSHA256 = '7d894dacf09a356992dfed1fb4b351c50b375a666b3e8625ae4fa2678748ff45';
export function requireProbeInstallation(installation) {
  if (installation?.standardMode !== true || installation?.openaiDisableCapabilityProbe !== true ||
      typeof installation?.engineDigest !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(installation.engineDigest) || installation?.probePatchSHA256 !== probePatchSHA256)
    throw fault(503, 'probe_contract_unverified');
}
const probeFlagValid = a => a.platform !== 'openai' || a.extra?.openai_disable_capability_probe === true;
export class AdminAPI {
  constructor({ baseURL, adminKey, timeoutMs = 10000, installation }) {
    this.baseURL = baseURL; this.adminKey = adminKey; this.timeoutMs = timeoutMs;
    Object.defineProperty(this, 'installation', { value: Object.freeze({ ...installation }), enumerable: true });
  }
  async createQuarantined(body, { templateID, workspace, provider, protocol, intentID, checkpoint = () => {} } = {}) {
    // Stock POST /accounts ignores status/schedulable and auto-binds defaults.
    // Duplicate instead persists an unschedulable copy and its group set in one
    // transaction. Only a trusted, per-workspace ungrouped template is eligible.
    if (!Number.isSafeInteger(templateID) || templateID < 1) throw fault(503, 'quarantine_template_required');
    requireProbeInstallation(this.installation);
    // Trusted policy wins even for direct server callers passing a false flag.
    body = { ...body, extra: { ...body.extra, ...(body.platform === 'openai' ? { openai_disable_capability_probe: true } : {}) } };
    const path = `/accounts/${templateID}`;
    checkpoint(); const template = await this.call('GET', path); checkpoint();
    const groups = stockGroups(template);
    const marker = template.extra?.rr_quarantine_template;
    if (marker?.workspace !== workspace || marker?.provider !== provider || marker?.protocol !== protocol ||
        template.type !== 'apikey' || template.platform !== body.platform || template.status !== 'inactive' || template.schedulable !== false ||
        template.id !== templateID || !probeFlagValid(template) || groups.length || !template.name?.startsWith('rr-sub2-spike-20260930-')) throw fault(409, 'quarantine_template_denied');
    const prepared = await this.call('PUT', path, { ...body, extra: { ...body.extra, rr_quarantine_template: marker }, status: 'inactive', group_ids: [] });
    checkpoint(); const preparedGroups = stockGroups(prepared);
    if (prepared.id !== templateID || prepared.type !== body.type || prepared.platform !== body.platform ||
        prepared.status !== 'inactive' || prepared.schedulable !== false || !probeFlagValid(prepared) || preparedGroups.length || prepared.name !== body.name ||
        !isDeepStrictEqual(prepared.extra?.rr_quarantine_template, marker) || !isDeepStrictEqual(prepared.extra?.rr_quarantine, body.extra.rr_quarantine)) throw fault(409, 'quarantine_template_drift');
    // Intentionally exactly one create attempt, even with an idempotency key.
    return this.call('POST', `${path}/duplicate`, {}, { 'Idempotency-Key': intentID });
  }
  async call(method, path, body, headers = {}) {
    const r = await fetch(`${this.baseURL}/api/v1/admin${path}`, { method, headers: { 'x-api-key': this.adminKey, 'content-type': 'application/json', ...headers }, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(this.timeoutMs) });
    if (!r.ok) { await r.body?.cancel(); throw fault(502, `admin_http_${r.status}`); }
    let n = 0; const chunks = []; for await (const b of r.body) { n += b.length; if (n > 2 * 1024 * 1024) throw fault(502, 'admin_response_limit'); chunks.push(b); }
    let data; try { data = JSON.parse(Buffer.concat(chunks)); } catch { throw fault(502, 'admin_invalid_json'); }
    if (data.code !== 0 || !Object.hasOwn(data, 'data')) throw fault(502, 'admin_api_error');
    return data.data;
  }
}
// Positive projection: untrusted name/notes/extra/credentials are never reflected.
export function publicAccount(a, binding) {
  return { id: binding.id, provider: binding.provider, protocol: binding.protocol, status: ['active', 'inactive', 'error'].includes(a.status) ? a.status : 'unknown', concurrency: Number.isSafeInteger(a.concurrency) ? a.concurrency : null };
}
export async function customerAdapter({ statePath, admin, workspaces, credentialProfiles, quarantineTemplates = {}, onAuthorityChange = async () => {} }) {
  const state = await loadJSON(statePath, { schema: 1, owner: randomBytes(16).toString('hex'), bindings: {} });
  if (state.schema !== 1 || !state.bindings || Array.isArray(state.bindings)) throw Error('Invalid account state');
  // Legacy intents have no ownership marker and cannot be adopted by name.
  state.owner ??= randomBytes(16).toString('hex');
  const lock = serial(); let poisoned = false;
  async function save() { try { await atomicJSON(statePath, state); } catch { poisoned = true; throw fault(503, 'metadata_unavailable'); } }
  await save();
  // Interrupted promotion may already have enabled engine scheduling. Fence the
  // server-owned workspace authority before serving any subsequent requests.
  for (const b of Object.values(state.bindings)) if (!['active', 'deleted'].includes(b.state) && (['bound', 'replacing', 'deleting'].includes(b.state) || b.fenced || !b.quarantineOwner)) {
    if (workspaces[b.workspace]) workspaces[b.workspace].suspended = true;
    await onAuthorityChange(b.workspace);
  }
  function membership(identity, manage = false) {
    const w = workspaces[identity?.workspace];
    const role = w?.members?.[identity?.user];
    if (!w || w.suspended || !['owner', 'manager', 'member'].includes(role) || manage && !['owner', 'manager'].includes(role)) throw fault(403, 'membership_denied');
    if (poisoned) throw fault(503, 'metadata_unavailable'); return w;
  }
  function authority(identity, manage) {
    const w = membership(identity, manage), workspace = identity.workspace;
    const snapshot = structuredClone(w), members = w.members, groups = w.groups, workspaceTemplates = w.quarantineTemplates;
    const credentials = credentialProfiles?.[workspace], templates = quarantineTemplates[workspace];
    const credentialSnapshot = { ...credentials }, templateSnapshot = structuredClone(templates);
    return { w, group: key => snapshot.groups?.[key], template: key => templateSnapshot?.[key] ?? snapshot.quarantineTemplates?.[key],
      credential: key => credentialSnapshot[key], check() {
        const current = membership(identity, manage);
        if (current !== w || current.members !== members || current.groups !== groups || current.quarantineTemplates !== workspaceTemplates ||
            !isDeepStrictEqual(current, snapshot) || credentialProfiles?.[workspace] !== credentials ||
            !isDeepStrictEqual(credentialProfiles?.[workspace] ?? {}, credentialSnapshot) || quarantineTemplates[workspace] !== templates ||
            !isDeepStrictEqual(quarantineTemplates[workspace], templateSnapshot)) throw fault(409, 'authority_changed');
      } };
  }
  async function checked(guard, fn) { guard.check(); const value = await fn(); guard.check(); return value; }
  function owned(identity, id) {
    const b = state.bindings[id]; if (!b || b.workspace !== identity.workspace || b.state !== 'active') throw fault(404, 'account_not_found'); return b;
  }
  async function fetchOwned(identity, id, guard) {
    const b = owned(identity, id);
    try {
      const a = await checked(guard, () => admin.call('GET', `/accounts/${b.upstreamID}`));
      const expected = guard.group(`${b.provider}:${b.protocol}`);
      // Sub2API groups restrict routing, not upstream credential ownership.
      const groups = stockGroups(a);
      if (a.id !== b.upstreamID || a.platform !== providerProfiles[`${b.provider}:${b.protocol}`]?.platform ||
          a.type !== 'apikey' || !probeFlagValid(a) || b.quarantineOwner && !matches(a, b) || groups.length !== 1 || groups[0] !== expected) throw fault(409, 'group_drift');
      return { a, b };
    } catch (e) { return failClosed(b, e); }
  }
  const baseNameOf = b => `rr-sub2-spike-20260930-${state.owner}-${b.id}`;
  const nameOf = b => `${baseNameOf(b)} (Copy)`;
  const markerOf = b => ({ owner: state.owner, binding: b.id, workspace: b.workspace });
  function matches(a, b) {
    const m = a.extra?.rr_quarantine;
    return a.name === nameOf(b) && m?.owner === state.owner && m?.binding === b.id && m?.workspace === b.workspace &&
      a.platform === providerProfiles[`${b.provider}:${b.protocol}`]?.platform && a.type === 'apikey';
  }
  const groupsOf = stockGroups;
  function quarantined(a) { return ['active', 'inactive'].includes(a.status) && a.schedulable === false && groupsOf(a).length === 0; }
  async function quarantine(b, guard) {
    // No publication even when compensation is unreachable. Retain intent for
    // explicit operator recovery; never create a second account automatically.
    if (!b.upstreamID) return;
    const call = (method, path, body) => guard ? checked(guard, () => admin.call(method, path, body)) : admin.call(method, path, body);
    const before = await call('GET', `/accounts/${b.upstreamID}`);
    // Never compensate a different/foreign account even if the stored ID is reused.
    if (before?.id !== b.upstreamID || b.quarantineOwner && !matches(before, b)) throw fault(409, 'compensation_ownership_denied');
    await call('POST', `/accounts/${b.upstreamID}/schedulable`, { schedulable: false });
    await call('PUT', `/accounts/${b.upstreamID}`, { status: 'inactive', group_ids: [] });
    const a = await call('GET', `/accounts/${b.upstreamID}`);
    if (a.id !== b.upstreamID || a.status !== 'inactive' || !quarantined(a) || b.quarantineOwner && !matches(a, b)) throw fault(502, 'compensation_unconfirmed');
  }
  async function promote(identity, b, guard) {
    requireProbeInstallation(admin.installation);
    // Re-read before even group attachment; recovery cannot revive a lost flag.
    const before = await checked(guard, () => admin.call('GET', `/accounts/${b.upstreamID}`));
    if (before.id !== b.upstreamID || !matches(before, b) || !quarantined(before) || !probeFlagValid(before)) throw fault(409, 'probe_policy_drift');
    guard.check(); const group = guard.group(`${b.provider}:${b.protocol}`);
    if (!Number.isSafeInteger(group) || group < 1) throw fault(403, 'routing_denied');
    // Ownership is durable before any active workspace group is attached.
    b.state = 'bound'; await checked(guard, save);
    const validate = (a, status, schedulable) => {
      if (a.id !== b.upstreamID || !probeFlagValid(a) || !matches(a, b) || a.status !== status || a.schedulable !== schedulable ||
          !isDeepStrictEqual(groupsOf(a), [group])) throw fault(502, 'promotion_invalid');
    };
    validate(await checked(guard, () => admin.call('PUT', `/accounts/${b.upstreamID}`, { group_ids: [group], status: 'inactive' })), 'inactive', false);
    validate(await checked(guard, () => admin.call('PUT', `/accounts/${b.upstreamID}`, { status: 'active' })), 'active', false);
    const a = await checked(guard, () => admin.call('POST', `/accounts/${b.upstreamID}/schedulable`, { schedulable: true }));
    validate(a, 'active', true);
    b.state = 'active'; b.fenced = false; await checked(guard, save); return publicAccount(a, b);
  }
  async function failClosed(b, error) {
    b.state = 'recovery_required';
    try { await quarantine(b); } catch {
      b.fenced = true;
      if (workspaces[b.workspace]) workspaces[b.workspace].suspended = true;
      try { await onAuthorityChange(b.workspace); } catch { poisoned = true; }
    }
    try { await save(); } finally {
      // Revocation/persistence can themselves replace the server-owned object.
      if (b.fenced && workspaces[b.workspace]) workspaces[b.workspace].suspended = true;
    }
    throw error;
  }
  async function connectOwned(guard, identity, input, replacingID) {
    if (Object.keys(input).some(k => !['provider', 'protocol'].includes(k))) throw fault(400, 'customer_routing_denied');
    const profile = providerProfiles[`${input.provider}:${input.protocol}`];
    const group = guard.group(`${input.provider}:${input.protocol}`);
    const credentialRef = guard.credential(`${input.provider}:${input.protocol}`);
    const credential = await checked(guard, () => typeof credentialRef === 'function' ? credentialRef() : credentialRef);
    if (!profile || !Number.isSafeInteger(group) || group < 1 || typeof credential !== 'string' || !credential) throw fault(400, 'unsupported_account');
    safeProviderURL(profile.baseURL);
    if (Object.values(state.bindings).some(b => b.workspace === identity.workspace && b.provider === input.provider && b.protocol === input.protocol && b.id !== replacingID && !['active', 'deleted'].includes(b.state))) throw fault(409, 'recovery_required');
    const id = randomBytes(16).toString('hex');
    const b = { id, workspace: identity.workspace, provider: input.provider, protocol: input.protocol, state: 'creating', quarantineOwner: state.owner };
    state.bindings[id] = b;
    try {
      await checked(guard, save);
      const extra = profile.platform === 'openai' ? { openai_disable_capability_probe: true, openai_responses_mode: 'force_responses', openai_passthrough: true } : { anthropic_passthrough: true };
      if (input.provider === 'mimo' && input.protocol === 'responses') extra.openai_preserve_compatible_reasoning = true;
      extra.rr_quarantine = markerOf(b);
      const a = await admin.createQuarantined({ name: baseNameOf(b), platform: profile.platform, type: 'apikey', credentials: { api_key: credential, base_url: profile.baseURL, model_mapping: { [profile.model]: profile.model } }, extra, concurrency: 2, priority: 1, rate_multiplier: 1 }, { templateID: guard.template(`${input.provider}:${input.protocol}`), workspace: identity.workspace, provider: input.provider, protocol: input.protocol, intentID: id, checkpoint: guard.check });
      if (!Number.isSafeInteger(a?.id) || a.id < 1 || !matches(a, b)) throw fault(502, 'quarantine_invalid');
      b.upstreamID = a.id;
      guard.check(); if (!probeFlagValid(a) || !quarantined(a)) throw fault(502, 'quarantine_invalid');
      await checked(guard, save);
      await checked(guard, () => quarantine(b, guard));
      const result = await promote(identity, b, guard); guard.check(); return result;
    } catch (e) { return failClosed(b, e); }
  }
  const api = {
    membership,
    async operate(identity, action, id, input = {}) { return lock(async () => {
      const manage = !['list', 'read'].includes(action), guard = authority(identity, manage);
      let b, mutated = false; const readBindings = [];
      try {
        let result;
        if (action === 'connect') {
          result = await connectOwned(guard, identity, input); b = state.bindings[result.id];
        } else if (action === 'list') {
          result = [];
          for (const binding of Object.values(state.bindings)) if (binding.workspace === identity.workspace && binding.state === 'active') {
            const { a } = await fetchOwned(identity, binding.id, guard); readBindings.push(binding); result.push(publicAccount(a, binding));
          }
        } else {
          const fetched = await fetchOwned(identity, id, guard); b = fetched.b; const a = fetched.a; guard.check();
          if (action === 'read') result = publicAccount(a, b);
          else if (action === 'export') {
            // Credential-bearing stock export is read privately; never reflected.
            await checked(guard, () => admin.call('GET', `/accounts/data?ids=${b.upstreamID}&include_proxies=false`));
            result = { schema: 1, restorable: false, account: publicAccount(a, b) };
          } else if (action === 'delete' || action === 'replace') {
            if (action === 'replace' && Object.keys(input).length) throw fault(400, 'customer_routing_denied');
            b.state = action === 'delete' ? 'deleting' : 'replacing'; await checked(guard, save);
            await checked(guard, () => onAuthorityChange(identity.workspace));
            mutated = true;
            if (action === 'replace') {
              await checked(guard, () => quarantine(b, guard));
              result = await connectOwned(guard, identity, { provider: b.provider, protocol: b.protocol }, b.id);
              // Until old retirement is confirmed, a replacement cannot escape
              // compensation if authority changes while the final delete awaits.
              readBindings.push(state.bindings[result.id]); guard.check();
            }
            await checked(guard, () => admin.call('DELETE', `/accounts/${b.upstreamID}`));
            b.state = 'deleted'; await checked(guard, save);
            if (action === 'delete') result = { deleted: true };
          } else if (action === 'refresh' || action === 'pause' || action === 'update') {
            if (action === 'refresh' && a.type !== 'oauth') throw fault(409, 'refresh_requires_oauth');
            if (action === 'update' && (Object.keys(input).some(k => k !== 'concurrency') || !Number.isSafeInteger(input.concurrency) || input.concurrency < 1 || input.concurrency > 2)) throw fault(400, 'customer_routing_denied');
            await checked(guard, () => onAuthorityChange(identity.workspace)); mutated = true;
            const updated = await checked(guard, () => admin.call(action === 'refresh' ? 'POST' : 'PUT', `/accounts/${b.upstreamID}${action === 'refresh' ? '/refresh' : ''}`, action === 'refresh' ? {} : action === 'pause' ? { status: 'inactive' } : { concurrency: input.concurrency }));
            if (!probeFlagValid(updated) || !isDeepStrictEqual(stockGroups(updated), [guard.group(`${b.provider}:${b.protocol}`)]) || updated.id !== b.upstreamID || b.quarantineOwner && !matches(updated, b)) throw fault(409, 'group_drift');
            result = publicAccount(updated, b);
          } else throw fault(404, 'action_denied');
        }
        guard.check(); return result;
      } catch (e) {
        if (e.code === 'authority_changed' || mutated) {
          for (const binding of readBindings) if (binding.state !== 'deleted') {
            try { await failClosed(binding, e); } catch { /* continue compensation */ }
          }
          if (b && b.state !== 'deleted') return failClosed(b, e);
        }
        throw e;
      }
    }); },
    // Trusted operator API, deliberately absent from customer HTTP routes.
    async reconcile(identity, id, decision = 'retire') { return lock(async () => {
      const guard = authority(identity, true);
      if (!['retire', 'complete'].includes(decision)) throw fault(400, 'recovery_decision_denied');
      const b = state.bindings[id];
      if (!b || b.workspace !== identity.workspace || ['active', 'deleted'].includes(b.state) || b.quarantineOwner !== state.owner) throw fault(404, 'recovery_not_found');
      try {
        let a;
        if (b.upstreamID) {
          a = await checked(guard, () => admin.call('GET', `/accounts/${b.upstreamID}`));
          stockGroups(a);
          if (a.id !== b.upstreamID || !matches(a, b)) throw fault(409, 'recovery_ownership_denied');
        } else {
          const found = [];
          for (let page = 1; ; page++) {
            if (page > 100) throw fault(503, 'recovery_scan_limit');
            const data = await checked(guard, () => admin.call('GET', `/accounts?page=${page}&page_size=100&lite=false&search=${encodeURIComponent(nameOf(b))}`));
            if (!Array.isArray(data?.items) || !Number.isSafeInteger(data.total) || data.total < 0) throw fault(502, 'recovery_list_invalid');
            for (const item of data.items) { stockGroups(item); if (matches(item, b)) found.push(item); }
            if (page * 100 >= data.total) break;
          }
          if (found.length !== 1 || !quarantined(found[0])) throw fault(409, 'recovery_quarantine_denied');
          a = found[0]; b.upstreamID = a.id; await checked(guard, save);
          // Re-fetch full authority before adopting the list observation.
          a = await checked(guard, () => admin.call('GET', `/accounts/${b.upstreamID}`));
          if (!matches(a, b) || a.id !== b.upstreamID || !quarantined(a)) throw fault(409, 'recovery_quarantine_denied');
        }
        await checked(guard, () => quarantine(b, guard));
        if (decision === 'complete') {
          const result = await promote(identity, b, guard); guard.check(); return result;
        }
        await checked(guard, () => admin.call('DELETE', `/accounts/${b.upstreamID}`));
        b.state = 'deleted'; b.fenced = false; await checked(guard, save); return { retired: true };
      } catch (e) { return failClosed(b, e); }
    }); },
    async recovery() { return Object.values(state.bindings).filter(b => b.state !== 'active' && b.state !== 'deleted').map(b => ({ id: b.id, workspace: b.workspace, state: b.state, upstreamID: b.upstreamID ?? null })); }
  };
  return api;
}
export function testCustomerServer({ adapter, identities, testOnly }) {
  if (testOnly !== true || Object.keys(identities).some(k => !k.startsWith('synthetic-'))) throw Error('Synthetic auth required; this is not production membership/SSO');
  return http.createServer(async (req, res) => {
    try {
      const identity = identities[bearer(req)]; if (!identity) throw fault(401, 'test_auth_denied');
      const u = new URL(req.url, 'http://customer'); if (u.search) throw fault(404, 'route_denied');
      const m = /^\/accounts(?:\/([a-f0-9]{32})(?:\/(pause|refresh|export|replace))?)?$/.exec(u.pathname); if (!m) throw fault(404, 'route_denied');
      const action = !m[1] ? (req.method === 'GET' ? 'list' : req.method === 'POST' ? 'connect' : null) : m[2] ? (req.method === 'POST' ? m[2] : null) : ({ GET: 'read', PUT: 'update', DELETE: 'delete' })[req.method];
      if (!action) throw fault(404, 'route_denied');
      const input = ['connect', 'update'].includes(action) ? await readJSON(req, 16384) : {};
      send(res, 200, await adapter.operate(identity, action, m[1], input));
    } catch (e) { send(res, e.status ?? 502, { error: { type: e.status ? e.code : 'customer_failure' } }); }
  });
}
