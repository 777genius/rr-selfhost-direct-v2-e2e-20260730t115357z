import http from 'node:http';
import { randomBytes } from 'node:crypto';
import { readFile, appendFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { oidcVerifier } from './oidc.mjs';
const MAX_BODY = 2 * 1024 * 1024;
const routes = { '/openai/v1/responses': 'responses', '/anthropic/v1/messages': 'messages' };
const allowed = new Set(['mimo:responses', 'openrouter:responses', 'mimo:messages']);
const fields = {
  responses: new Set('model input instructions tools tool_choice parallel_tool_calls max_output_tokens temperature top_p stream stream_options reasoning text include previous_response_id store truncation metadata service_tier prompt_cache_key prompt_cache_retention safety_identifier context_management'.split(' ')),
  messages: new Set('model messages max_tokens system tools tool_choice temperature top_p top_k stream stop_sequences metadata thinking context_management output_config service_tier'.split(' ')),
};
const error = (status, message) => Object.assign(Error(message), { status });
export async function createBroker(config, { clock = Date.now, jwks, fetcher = fetch, log = () => {} } = {}) {
  if (!config.ledgerPath) throw Error('Durable ledger required');
  const verify = oidcVerifier({ ownerID: config.ownerID, workflowSHA: config.workflowSHA, clock, jwks });
  const ttl = config.ttlSeconds ?? 900;
  if (!Number.isInteger(ttl) || ttl < 1 || ttl > 900) throw Error('Invalid TTL');
  for (const [name, p] of Object.entries(config.providers)) {
    if (Object.keys(p).some(k => !['alias', 'model', 'keyID'].includes(k)) || !allowed.has(name) || !/^[a-z0-9-]+$/.test(p.alias) || typeof p.model !== 'string' || !p.model || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(p.keyID)) throw Error('Invalid provider configuration');
  }
  const adminBase = new URL(config.adminURL), inferenceBase = new URL(config.inferenceURL);
  for (const u of [adminBase, inferenceBase]) if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password || u.search || u.hash || u.pathname !== '/') throw Error('Invalid Bifrost URL');
  const grants = new Map(), caps = new Map(), runs = new Map(), closedRuns = new Set(); let closing = false;
  try { for (const line of (await readFile(config.ledgerPath, 'utf8')).split('\n').filter(Boolean)) {
    const { scope } = JSON.parse(line);
    if (typeof scope !== 'string' || !/^[1-9]\d*:[1-9]\d*:(mimo:responses|openrouter:responses|mimo:messages)$/.test(scope)) throw Error('Invalid grant ledger');
    grants.set(scope, { revoked: true }); closedRuns.add(scope.split(':').slice(0, 2).join(':'));
  } }
  catch (e) { if (e.code !== 'ENOENT') throw e; }
  async function admin(path, method, body) {
    const r = await fetcher(new URL(path, adminBase), { method, redirect: 'error', headers: { 'content-type': 'application/json', ...(config.adminAuth ? { authorization: `Bearer ${config.adminAuth}` } : {}) }, body: body && JSON.stringify(body), signal: AbortSignal.timeout(10000) });
    if (!r.ok) throw error(502, 'Gateway administration failed');
    return method === 'DELETE' ? null : r.json();
  }
  async function revoke(g) {
    if (!g || g.revoked) return;
    g.revoked = true;
    for (const c of g.controllers ?? []) c.abort();
    g.value = undefined;
    if (g.id) await admin(`/api/governance/virtual-keys/${encodeURIComponent(g.id)}`, 'DELETE').catch(() => log({ event: 'revoke_pending' }));
  }
  async function body(req) {
    if (Number(req.headers['content-length']) > MAX_BODY) { req.resume(); throw error(413, 'Body too large'); }
    let n = 0; const chunks = [];
    for await (const chunk of req.iterator({ destroyOnReturn: false })) { n += chunk.length; if (n > MAX_BODY) { req.resume(); throw error(413, 'Body too large'); } chunks.push(chunk); }
    try { const b = JSON.parse(Buffer.concat(chunks).toString()); if (!b || typeof b !== 'object' || Array.isArray(b)) throw Error(); return b; } catch { throw error(400, 'Invalid JSON body'); }
  }
  function bearer(req) { const h = req.headers.authorization; if (typeof h !== 'string' || !/^Bearer [^\s]+$/.test(h)) throw error(401, 'Authorization required'); return h.slice(7); }
  async function grant(req) {
    let identity; try { identity = await verify(bearer(req)); } catch { throw error(401, 'Invalid OIDC'); }
    const b = await body(req);
    if (typeof b.provider !== 'string' || typeof b.protocol !== 'string' || Object.keys(b).some(k => !['provider', 'protocol'].includes(k))) throw error(403, 'Invalid grant scope');
    const provider = config.providers[`${b.provider}:${b.protocol}`];
    if (!allowed.has(`${b.provider}:${b.protocol}`) || !provider) throw error(403, 'Provider unavailable');
    const run = `${identity.runID}:${identity.attempt}`;
    if (closedRuns.has(run)) throw error(403, 'Run closed after restart');
    const scope = `${run}:${b.provider}:${b.protocol}`;
    let g = grants.get(scope);
    if (!g) {
      if (!runs.has(run)) runs.set(run, { count: 0, active: 0 });
      g = { budget: runs.get(run), revoked: false, expires: Math.min(clock() + ttl * 1000, identity.expires), controllers: new Set(), provider, protocol: b.protocol };
      grants.set(scope, g);
      g.pending = (async () => {
        // Reserve durably BEFORE admin effects; restart and ambiguous failure deny replay.
        await appendFile(config.ledgerPath, JSON.stringify({ scope }) + '\n', { mode: 0o600, flush: true });
        const result = await admin('/api/governance/virtual-keys', 'POST', { name: `spike-${scope}`, allow_all_providers: false, provider_configs: [{ provider: provider.alias, key_ids: [provider.keyID], allowed_models: [provider.model] }], expires_at: new Date(g.expires).toISOString() });
        const vk = result.virtual_key;
        if (typeof vk?.value !== 'string' || !vk.value || typeof vk.id !== 'string' || !vk.id) throw error(502, 'Invalid virtual key response');
        g.id = vk.id; g.value = vk.value;
        if (closing || g.revoked || clock() >= g.expires) { g.revoked = false; await revoke(g); throw error(403, 'Grant closed'); }
        g.capability = randomBytes(32).toString('base64url'); caps.set(g.capability, g);
      })().catch(e => { g.revoked = true; throw e; });
    }
    if (g.revoked || clock() >= g.expires) { await revoke(g); throw error(403, 'Grant closed'); }
    await g.pending;
    if (g.revoked || clock() >= g.expires) throw error(403, 'Grant closed');
    return { capability: g.capability, model: `${provider.alias}/${provider.model}`, expires_at: new Date(g.expires).toISOString() };
  }
  const server = http.createServer(async (req, res) => {
    let status = 500;
    try {
      if (closing) throw error(503, 'Broker closing');
      if (req.method === 'GET' && req.url === '/health') { status = 200; res.writeHead(200).end('ok'); return; }
      if (req.method !== 'POST' || (req.url !== '/grant' && !routes[req.url])) throw error(404, 'Route unavailable');
      if (req.url === '/grant') { const b = await grant(req); status = 200; res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' }).end(JSON.stringify(b)); return; }
      const g = caps.get(bearer(req));
      if (!g || g.revoked || clock() >= g.expires) { if (g) await revoke(g); throw error(401, 'Capability closed'); }
      if (g.protocol !== routes[req.url]) throw error(403, 'Protocol mismatch');
      // Reserve before body read to bound slow clients and accepted attempts.
      if (g.budget.count >= 32) throw error(429, 'Run request limit');
      if (g.budget.active >= 2) throw error(429, 'Run concurrency limit');
      g.budget.count++; g.budget.active++;
      const controller = new AbortController(); g.controllers.add(controller);
      controller.signal.addEventListener('abort', () => { if (!req.complete) req.destroy(); if (res.headersSent && !res.writableEnded) res.destroy(); }, { once: true });
      const cancel = () => { if (!res.writableEnded) controller.abort(); };
      res.on('close', cancel); req.on('aborted', cancel);
      const timer = setTimeout(() => controller.abort(), 120000); timer.unref();
      const expiryTimer = setTimeout(() => controller.abort(), Math.max(0, g.expires - clock())); expiryTimer.unref();
      try {
        const b = await body(req);
        if (g.revoked || clock() >= g.expires) throw error(401, 'Capability closed');
        if (b.model !== `${g.provider.alias}/${g.provider.model}` || Object.keys(b).some(k => !fields[g.protocol].has(k))) throw error(403, 'Routing mismatch');
        const headers = { 'content-type': 'application/json', 'x-bf-vk': g.value };
        if (g.protocol === 'messages') for (const h of ['anthropic-version', 'anthropic-beta']) if (req.headers[h]) headers[h] = req.headers[h];
        const up = await fetcher(new URL(g.protocol === 'responses' ? '/v1/responses' : '/anthropic/v1/messages', inferenceBase), { method: 'POST', headers, body: JSON.stringify(b), signal: controller.signal, redirect: 'error' });
        status = up.status;
        res.writeHead(up.status, { 'content-type': up.headers.get('content-type') ?? 'application/json', 'cache-control': 'no-store' });
        // Raw bytes, including SSE errors and terminal events; no decoding or retry.
        if (up.body) for await (const chunk of up.body) {
          if (controller.signal.aborted) throw Error('Aborted');
          if (!res.write(chunk)) await new Promise((resolve, reject) => {
            const done = () => { res.off('drain', drain); res.off('close', close); };
            const drain = () => { done(); resolve(); }; const close = () => { done(); reject(Error('Closed')); };
            res.once('drain', drain); res.once('close', close);
          });
        }
        res.end();
      } finally { clearTimeout(timer); clearTimeout(expiryTimer); g.controllers.delete(controller); g.budget.active--; res.off('close', cancel); req.off('aborted', cancel); }
    } catch (e) {
      status = e.status ?? 502;
      if (res.headersSent) res.destroy(); else res.writeHead(status, { 'content-type': 'application/json' }).end(JSON.stringify({ error: e.status ? e.message : 'Gateway unavailable' }));
    } finally { log({ event: 'request', status }); }
  });
  server.requestTimeout = 120000; server.headersTimeout = 15000;
  const sweep = setInterval(() => { for (const g of caps.values()) if (clock() >= g.expires) void revoke(g); }, 1000); sweep.unref();
  return { server, revoke: capability => revoke(caps.get(capability)), close: async () => { closing = true; clearInterval(sweep); const stopped = new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }); await Promise.allSettled([...grants.values()].map(g => g.pending)); await Promise.all([...caps.values()].map(revoke)); await stopped; } };
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const config = JSON.parse(await readFile(process.argv[2], 'utf8'));
  config.adminAuth = process.env.BIFROST_ADMIN_AUTH;
  const broker = await createBroker(config, { log: entry => console.log(JSON.stringify(entry)) });
  broker.server.listen(8787, '0.0.0.0');
  for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => void broker.close());
}
