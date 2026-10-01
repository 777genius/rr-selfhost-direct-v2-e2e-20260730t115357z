import http from 'node:http';
import { randomBytes, randomUUID } from 'node:crypto';
import { mkdir, open } from 'node:fs/promises';
import { unlinkSync } from 'node:fs';
import { dirname } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { nativeErrorFilter } from './native-errors.mjs';
import { atomicJSON, loadJSON, serial, readJSON, send, bearer, fault } from './util.mjs';
const paths = new Map([['/v1/responses', 'responses'], ['/openai/v1/responses', 'responses'], ['/v1/messages', 'messages'], ['/anthropic/v1/messages', 'messages']]);
const routing = new Set(['account_id', 'account', 'group', 'group_id', 'key', 'api_key', 'baseURL', 'base_url', 'provider', 'workspace', 'workspace_id', 'upstream_url']);
function denyRouting(x) { if (!x || typeof x !== 'object') return; for (const k of Object.keys(x)) if (routing.has(k)) throw fault(400, 'routing_denied'); }
export async function createBroker({ ledgerPath, verifyOIDC, scopes, resolveWorkspace, isWorkspaceActive = () => true, timeoutMs = 60000, ttlMs = 900000, maxRequests = 32, maxConcurrent = 2, globalConcurrent = 40, log = () => {} }) {
  if (!(ttlMs > 0 && ttlMs <= 900000 && maxRequests > 0 && maxRequests <= 32 && maxConcurrent > 0 && maxConcurrent <= 2 && timeoutMs > 0)) throw Error('Invalid limits');
  // Exclusive process lock. Crash leaves it present: fail closed until the
  // coordinator proves the old broker terminal and removes only this lock.
  await mkdir(dirname(ledgerPath), { recursive: true, mode: 0o700 });
  const ledgerLock = await open(`${ledgerPath}.lock`, 'wx', 0o600);
  await ledgerLock.writeFile(String(process.pid)); await ledgerLock.sync();
  const releaseLock = () => { try { unlinkSync(`${ledgerPath}.lock`); } catch {} };
  const disk = await loadJSON(ledgerPath, { schema: 1, runs: {} });
  if (disk.schema !== 1 || !disk.runs || Array.isArray(disk.runs)) throw Error('Invalid ledger');
  const grants = new Map(), byRun = new Map(), lock = serial(); let active = 0, poisoned = false;
  async function persist() { try { await atomicJSON(ledgerPath, disk); } catch { poisoned = true; throw fault(503, 'ledger_unavailable'); } }
  try { await persist(); } catch (e) { await ledgerLock.close(); releaseLock(); throw e; } // Before admission.
  await ledgerLock.close();
  function close(g) { g.closed = true; for (const c of g.controllers) c.abort(); clearTimeout(g.timer); }
  const server = http.createServer({ maxHeaderSize: 16384 }, async (req, res) => {
    const started = Date.now(); let code = 'ok';
    try {
      if (poisoned) throw fault(503, 'ledger_unavailable');
      const url = new URL(req.url, 'http://broker');
      // Claude's native SDK uses this exact feature query. It grants no routing authority.
      if (url.search && !(url.pathname === '/anthropic/v1/messages' && url.search === '?beta=true')) throw fault(404, 'route_denied');
      if (url.pathname === '/grant' && req.method === 'POST') {
        let claims; try { claims = await verifyOIDC(bearer(req));
          if (!claims || typeof claims.runID !== 'string' || !/^[1-9]\d*$/.test(claims.runID) || typeof claims.attempt !== 'string' || !/^[1-9]\d*$/.test(claims.attempt) || typeof claims.workflowSHA !== 'string' || !/^[a-f0-9]{40}$/.test(claims.workflowSHA) || !Number.isFinite(claims.expires)) throw Error('Invalid verified identity');
          claims = Object.freeze({ ...claims }); // Snapshot the verifier result before resolver awaits.
        } catch { throw fault(401, 'oidc_denied'); }
        const input = await readJSON(req, 4096);
        if (Object.keys(input).some(k => !['provider', 'protocol'].includes(k))) throw fault(400, 'grant_scope_denied');
        const selected = Object.entries(scopes).find(([name, scope]) => name === `${input.provider}:${input.protocol}` && name === `${input.provider}:${scope.protocol}`);
        if (!selected) throw fault(400, 'unsupported_scope');
        const [scopeName, scope] = selected;
        const identity = Object.freeze({ runID: claims.runID, attempt: claims.attempt, workflowSHA: claims.workflowSHA, provider: scopeName.split(':')[0], protocol: scope.protocol });
        const workspace = await resolveWorkspace(claims); if (!workspace || !await isWorkspaceActive(workspace)) throw fault(403, 'membership_denied');
        const binding = scope.workspaces[workspace]; if (!binding?.key || !binding.groupID) throw fault(403, 'workspace_denied');
        const g = await lock(async () => {
          const prior = byRun.get(claims.runID);
          if (prior && !prior.closed && prior.expires > Date.now() && prior.attempt === claims.attempt && prior.scope === scope && prior.workspace === workspace) return prior;
          if (disk.runs[claims.runID]) throw fault(409, 'run_replay_denied');
          const expires = Math.min(Date.now() + ttlMs, claims.expires); if (expires <= Date.now()) throw fault(401, 'expired');
          disk.runs[claims.runID] = { attempt: claims.attempt, workspace, state: 'issued' }; await persist();
          const grant = { capability: randomBytes(32).toString('base64url'), session: randomUUID(), identity, scope, binding, workspace, attempt: claims.attempt, expires, requests: 0, active: 0, closed: false, controllers: new Set() };
          grant.timer = setTimeout(() => close(grant), expires - Date.now()); grant.timer.unref();
          grants.set(grant.capability, grant); byRun.set(claims.runID, grant); return grant;
        });
        send(res, 200, { capability: g.capability, model: g.scope.model, expires: g.expires, ...g.identity }); return;
      }
      if (req.method !== 'POST' && req.method !== 'DELETE') throw fault(404, 'route_denied');
      const g = grants.get(bearer(req));
      if (!g || g.closed || g.expires <= Date.now()) throw fault(401, 'capability_denied');
      if (!await isWorkspaceActive(g.workspace)) { close(g); throw fault(403, 'membership_denied'); }
      if (url.pathname === '/grant' && req.method === 'DELETE') { close(g); send(res, 200, { revoked: true }); return; }
      if (req.method !== 'POST' || paths.get(url.pathname) !== g.scope.protocol) throw fault(404, 'route_denied');
      if (g.requests >= maxRequests || g.active >= maxConcurrent || active >= globalConcurrent) throw fault(429, 'request_limit');
      // Reserve capacity BEFORE reading body so concurrent uploads cannot bypass it.
      g.active++; active++;
      const controller = new AbortController(); g.controllers.add(controller);
      const timer = setTimeout(() => { controller.abort(); req.destroy(); }, Math.min(timeoutMs, g.expires - Date.now())); timer.unref();
      const cancel = () => { if (!res.writableFinished) controller.abort(); }; res.once('close', cancel);
      try {
        const body = await readJSON(req); denyRouting(body);
        // This bounded capability authorizes native streaming Responses/Messages.
        // A caller cannot switch to a different, unsanitized response mode.
        if (body.stream !== undefined && body.stream !== true) throw fault(400, 'stream_required');
        body.stream = true;
        if (body.model !== undefined && body.model !== g.scope.model) throw fault(400, 'model_denied');
        body.model = g.scope.model;
        if (controller.signal.aborted || g.closed || !await isWorkspaceActive(g.workspace)) throw fault(401, 'capability_denied');
        const headers = { 'content-type': 'application/json', authorization: `Bearer ${g.binding.key}` };
        // Native version/beta/client feature headers pass without classifier rewriting. Routing, IP,
        // caller session hints and authorization are discarded; group belongs to the key.
        for (const h of ['anthropic-version', 'anthropic-beta', 'openai-beta', 'x-codex-beta-features', 'originator', 'user-agent']) if (typeof req.headers[h] === 'string') headers[h] = req.headers[h];
        headers.session_id = g.session; headers['x-claude-code-session-id'] = g.session;
        if (g.requests >= maxRequests) throw fault(429, 'request_limit');
        g.requests++;
        const upstream = await fetch(`${g.scope.baseURL}/v1/${g.scope.protocol}${url.search}`, { method: 'POST', headers, body: JSON.stringify(body), signal: controller.signal, redirect: 'error' });
        if (!upstream.ok) {
          await upstream.body?.cancel();
          const retry = upstream.headers.get('retry-after');
          if (retry && /^\d{1,6}$/.test(retry)) res.setHeader('retry-after', retry);
          code = 'upstream_http_error'; send(res, upstream.status, { error: { type: code, status: upstream.status } }); return;
        }
        const type = upstream.headers.get('content-type') ?? 'application/octet-stream';
        if (!type.includes('text/event-stream')) { await upstream.body?.cancel(); throw fault(502, 'native_stream_required'); }
        res.writeHead(upstream.status, { 'content-type': type, 'cache-control': 'no-store' });
        const source = Readable.fromWeb(upstream.body);
        if (type.includes('text/event-stream')) await pipeline(source, nativeErrorFilter(), res, { signal: controller.signal });
        else await pipeline(source, res, { signal: controller.signal });
      } finally { clearTimeout(timer); res.off('close', cancel); controller.abort(); g.controllers.delete(controller); g.active--; active--; }
    } catch (e) {
      code = e.code && e.status ? e.code : 'transport_failure';
      if (res.headersSent) res.destroy(); else send(res, e.status ?? 502, { error: { type: code } });
    } finally { log({ event: 'request', code, duration_ms: Date.now() - started }); }
  });
  server.headersTimeout = 10000; server.requestTimeout = Math.min(timeoutMs, 60000);
  server.once('close', () => { for (const g of grants.values()) close(g); releaseLock(); });
  server.revokeWorkspace = workspace => { for (const g of grants.values()) if (g.workspace === workspace) close(g); };
  return server;
}
