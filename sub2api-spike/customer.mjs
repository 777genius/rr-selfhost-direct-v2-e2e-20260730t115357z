import http from 'node:http';
import { randomBytes } from 'node:crypto';
import { atomicJSON, loadJSON, serial, fault, send, readJSON, bearer } from './util.mjs';
export const providerProfiles = Object.freeze({
  'mimo:responses': { platform: 'openai', baseURL: 'https://token-plan-sgp.xiaomimimo.com/v1', model: 'mimo-v2.6-pro' },
  'mimo:messages': { platform: 'anthropic', baseURL: 'https://token-plan-sgp.xiaomimimo.com/anthropic', model: 'mimo-v2.6-pro' },
  'openrouter:responses': { platform: 'openai', baseURL: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4.1' }
});
export function safeProviderURL(value) {
  let u; try { u = new URL(value); } catch { throw fault(400, 'unsafe_url'); }
  if (u.username || u.password || u.hash || u.search || !Object.values(providerProfiles).some(p => p.baseURL === u.href.replace(/\/$/, ''))) throw fault(400, 'unsafe_url');
  return u.href.replace(/\/$/, '');
}
export class AdminAPI {
  constructor({ baseURL, adminKey, timeoutMs = 10000 }) { this.baseURL = baseURL; this.adminKey = adminKey; this.timeoutMs = timeoutMs; }
  async call(method, path, body) {
    const r = await fetch(`${this.baseURL}/api/v1/admin${path}`, { method, headers: { 'x-api-key': this.adminKey, 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(this.timeoutMs) });
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
export async function customerAdapter({ statePath, admin, workspaces, credentialProfiles, onAuthorityChange = async () => {} }) {
  const state = await loadJSON(statePath, { schema: 1, bindings: {} });
  if (state.schema !== 1 || !state.bindings || Array.isArray(state.bindings)) throw Error('Invalid account state');
  const lock = serial(); let poisoned = false;
  async function save() { try { await atomicJSON(statePath, state); } catch { poisoned = true; throw fault(503, 'metadata_unavailable'); } }
  await save();
  function membership(identity, manage = false) {
    const w = workspaces[identity?.workspace];
    const role = w?.members?.[identity?.user];
    if (!w || w.suspended || !role || manage && !['owner', 'manager'].includes(role)) throw fault(403, 'membership_denied');
    if (poisoned) throw fault(503, 'metadata_unavailable'); return w;
  }
  function owned(identity, id) {
    const b = state.bindings[id]; if (!b || b.workspace !== identity.workspace || b.state !== 'active') throw fault(404, 'account_not_found'); return b;
  }
  async function fetchOwned(identity, id) {
    const b = owned(identity, id); const a = await admin.call('GET', `/accounts/${b.upstreamID}`);
    const expected = workspaces[identity.workspace].groups[`${b.provider}:${b.protocol}`];
    // Sub2API groups restrict routing, not upstream credential ownership.
    const groups = a.group_ids ?? a.groups?.map(g => g.id);
    if (!Array.isArray(groups) || groups.length !== 1 || groups[0] !== expected) throw fault(409, 'group_drift');
    return { a, b };
  }
  async function connectOwned(w, identity, input, replacingID) {
        if (Object.keys(input).some(k => !['provider', 'protocol'].includes(k))) throw fault(400, 'customer_routing_denied');
        const profile = providerProfiles[`${input.provider}:${input.protocol}`];
        const group = w.groups?.[`${input.provider}:${input.protocol}`];
        const credentialRef = credentialProfiles?.[identity.workspace]?.[`${input.provider}:${input.protocol}`];
        const credential = typeof credentialRef === 'function' ? await credentialRef() : credentialRef;
        if (!profile || !group || !credential) throw fault(400, 'unsupported_account');
        safeProviderURL(profile.baseURL);
        if (Object.values(state.bindings).some(b => b.workspace === identity.workspace && b.provider === input.provider && b.protocol === input.protocol && b.id !== replacingID && ['creating', 'recovery_required', 'deleting', 'replacing'].includes(b.state))) throw fault(409, 'recovery_required');
        const id = randomBytes(16).toString('hex');
        const b = { id, workspace: identity.workspace, provider: input.provider, protocol: input.protocol, state: 'creating' };
        state.bindings[id] = b; await save();
        // Persist intention BEFORE remote create. An ambiguous failure remains
        // recovery_required: no automatic create retry or authority publication.
        try {
          const a = await admin.call('POST', '/accounts', { name: `rr-sub2-spike-20260930-${id}`, platform: profile.platform, type: 'apikey', credentials: { api_key: credential, base_url: profile.baseURL, model_mapping: { [profile.model]: profile.model } }, extra: profile.platform === 'openai' ? { openai_responses_mode: 'force_responses', openai_passthrough: true } : { anthropic_passthrough: true }, group_ids: [group], concurrency: 2, priority: 1, rate_multiplier: 1 });
          if (!Number.isSafeInteger(a.id) || a.id < 1) throw fault(502, 'invalid_account_id');
          b.upstreamID = a.id; b.state = 'active'; await save(); return publicAccount(a, b);
        } catch (e) { b.state = 'recovery_required'; await save(); throw e; }
  }
  const api = {
    membership,
    async operate(identity, action, id, input = {}) { return lock(async () => {
      const w = membership(identity, !['list', 'read'].includes(action));
      if (action === 'connect') return connectOwned(w, identity, input);
      if (action === 'list') {
        const out = []; for (const b of Object.values(state.bindings)) if (b.workspace === identity.workspace && b.state === 'active') { const { a } = await fetchOwned(identity, b.id); out.push(publicAccount(a, b)); } return out;
      }
      const { a, b } = await fetchOwned(identity, id);
      if (action === 'read') return publicAccount(a, b);
      if (action === 'export') {
        // Exercise credential-bearing source route privately, only publish the
        // same metadata projection. Export is deliberately non-restorable.
        await admin.call('GET', `/accounts/data?ids=${b.upstreamID}&include_proxies=false`);
        return { schema: 1, restorable: false, account: publicAccount(a, b) };
      }
      if (action === 'delete') {
        b.state = 'deleting'; await save(); await onAuthorityChange(identity.workspace);
        await admin.call('DELETE', `/accounts/${b.upstreamID}`); b.state = 'deleted'; await save(); return { deleted: true };
      }
      if (action === 'replace') {
        if (Object.keys(input).length) throw fault(400, 'customer_routing_denied');
        b.state = 'replacing'; await save(); await onAuthorityChange(identity.workspace);
        await admin.call('PUT', `/accounts/${b.upstreamID}`, { status: 'inactive' });
        const replacement = await connectOwned(w, identity, { provider: b.provider, protocol: b.protocol }, b.id);
        await admin.call('DELETE', `/accounts/${b.upstreamID}`); b.state = 'deleted'; await save(); return replacement;
      }
      if (action === 'refresh') {
        // API-key accounts have no OAuth lifecycle. Report it honestly.
        if (a.type !== 'oauth') throw fault(409, 'refresh_requires_oauth');
        await onAuthorityChange(identity.workspace);
        await admin.call('POST', `/accounts/${b.upstreamID}/refresh`, {});
        return publicAccount(await admin.call('GET', `/accounts/${b.upstreamID}`), b);
      }
      if (action === 'pause' || action === 'update') {
        if (action === 'update' && (Object.keys(input).some(k => k !== 'concurrency') || !Number.isSafeInteger(input.concurrency) || input.concurrency < 1 || input.concurrency > 2)) throw fault(400, 'customer_routing_denied');
        await onAuthorityChange(identity.workspace);
        const updated = await admin.call('PUT', `/accounts/${b.upstreamID}`, action === 'pause' ? { status: 'inactive' } : { concurrency: input.concurrency });
        return publicAccount(updated, b);
      }
      throw fault(404, 'action_denied');
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
