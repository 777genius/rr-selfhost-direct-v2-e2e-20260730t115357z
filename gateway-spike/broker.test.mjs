import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, sign } from 'node:crypto';
import http from 'node:http';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createBroker } from './broker.mjs';
import { oidcVerifier, issuer, audience, repository, workflowRef } from './oidc.mjs';
const pair = generateKeyPairSync('rsa', { modulusLength: 2048 });
const forged = generateKeyPairSync('rsa', { modulusLength: 2048 });
const sha = 'a'.repeat(40), now = 1800000000000;
const keys = { keys: [{ ...pair.publicKey.export({ format: 'jwk' }), kid: 'fixture', alg: 'RS256', use: 'sig' }] };
const claims = { iss: issuer, aud: audience, repository_id: '1317214237', repository, repository_owner_id: '13103045', workflow_ref: workflowRef, workflow_sha: sha, ref: 'refs/heads/main', event_name: 'workflow_dispatch', run_id: '100', run_attempt: '1', iat: now / 1000 - 10, nbf: now / 1000 - 10, exp: now / 1000 + 600 };
function jwt(change = {}, privateKey = pair.privateKey, header = {}) { const s = [ { alg: 'RS256', kid: 'fixture', ...header }, { ...claims, ...change } ].map(v => Buffer.from(JSON.stringify(v)).toString('base64url')).join('.'); return `${s}.${sign('RSA-SHA256', Buffer.from(s), privateKey).toString('base64url')}`; }
const listen = async server => { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return `http://127.0.0.1:${server.address().port}`; };
const close = server => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
const invalid = [ { iss: 'https://evil.example' }, { aud: ['review-router-gateway-spike'] }, { repository_id: '1' }, { repository: 'other/repo' }, { repository_owner_id: '1' }, { workflow_ref: 'wrong' }, { workflow_sha: 'b'.repeat(40) }, { ref: 'refs/heads/dev' }, { event_name: 'push' }, { exp: now / 1000 }, { nbf: now / 1000 + 1 }, { iat: now / 1000 + 1 }, { exp: 'later' }, { run_id: '' }, { run_id: 100 }, { run_attempt: '0' }, { run_attempt: -1 } ];
test('RS256 signature and every pinned claim/time/run boundary', async () => {
  const verify = oidcVerifier({ ownerID: '13103045', workflowSHA: sha, clock: () => now, jwks: async () => keys });
  assert.equal((await verify(jwt())).runID, '100');
  for (const change of invalid) await assert.rejects(verify(jwt(change)));
  await assert.rejects(verify(jwt({}, forged.privateKey)));
  await assert.rejects(verify(jwt({}, pair.privateKey, { alg: 'HS256' })));
});
async function rig(t) {
  let time = now; const adminRequests = [], inferenceRequests = [], held = new Set(), scopedKeys = new Map();
  const dir = await mkdtemp(join(tmpdir(), 'gateway-spike-test-'));
  const admin = http.createServer(async (req, res) => {
    let s = ''; for await (const c of req) s += c;
    adminRequests.push({ method: req.method, path: req.url, body: s && JSON.parse(s) });
    res.setHeader('content-type', 'application/json');
    if (req.method === 'POST') { const value = `fixture-vk-${adminRequests.length}`; scopedKeys.set(value, JSON.parse(s).provider_configs[0]); res.end(JSON.stringify({ virtual_key: { id: `vk-${adminRequests.length}`, value } })); } else res.end('{}');
  });
  const upstream = http.createServer(async (req, res) => {
    let s = ''; for await (const c of req) s += c;
    const b = JSON.parse(s); inferenceRequests.push({ path: req.url, headers: req.headers, body: b });
    const scope = scopedKeys.get(req.headers['x-bf-vk']);
    if (!scope || b.model !== `${scope.provider}/${scope.allowed_models[0]}`) { res.writeHead(401).end('wrong key'); return; }
    if ((b.input ?? b.metadata?.test_mode) === 'http-error') { res.writeHead(422, { 'content-type': 'application/json' }).end('{"error":"rejected"}'); return; }
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    if (b.input === 'hold') { held.add(res); res.write(': waiting\n\n'); res.on('close', () => held.delete(res)); return; }
    if ((b.input ?? b.metadata?.test_mode) === 'truncate') { res.write('event: response.created\ndata: {}\n\n'); setTimeout(() => res.destroy(), 40); return; }
    const bytes = req.url === '/anthropic/v1/messages' ? messages : responses;
    res.write(bytes.slice(0, 29)); setTimeout(() => res.end(bytes.slice(29)), 5);
  });
  const adminURL = await listen(admin), inferenceURL = await listen(upstream);
  const p = (alias, model) => ({ alias, model, keyID: '00000000-0000-4000-8000-000000000001' });
  const config = { ownerID: '13103045', workflowSHA: sha, ledgerPath: join(dir, 'ledger'), adminURL, inferenceURL, ttlSeconds: 60, providers: { 'mimo:responses': p('mimo-responses', 'mimo-v2.6-pro'), 'openrouter:responses': p('openrouter-responses', 'openai/gpt-4.1-mini'), 'mimo:messages': p('mimo-messages', 'mimo-v2.6-pro') } };
  const options = { clock: () => time, jwks: async () => keys };
  const broker = await createBroker(config, options), url = await listen(broker.server);
  t.after(async () => { await broker.close(); await close(upstream); await close(admin); await rm(dir, { recursive: true }); });
  const post = (path, token, b, headers = {}, signal) => fetch(url + path, { method: 'POST', headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', ...headers }, body: typeof b === 'string' ? b : JSON.stringify(b), signal });
  const grant = async (provider = 'mimo', protocol = 'responses', run = '100') => { const r = await post('/grant', jwt({ run_id: run }), { provider, protocol }); assert.equal(r.status, 200); return r.json(); };
  const infer = (g, b = {}, headers, signal) => post(g.model.startsWith('mimo-messages') ? '/anthropic/v1/messages' : '/openai/v1/responses', g.capability, { model: g.model, ...(g.model.startsWith('mimo-messages') ? { max_tokens: 64, messages: [{ role: 'user', content: 'review' }] } : { input: 'normal' }), stream: true, ...b }, headers, signal);
  return { broker, url, post, grant, infer, config, options, adminRequests, inferenceRequests, held, advance: n => { time += n; } };
}
const responses = Buffer.from('event: response.output_item.added\ndata: {"item":{"type":"function_call","name":"read_file","arguments":"{}"}}\n\nevent: response.failed\ndata: {"type":"response.failed","response":{"status":"failed","error":{"code":"upstream_failure"}}}\n\n');
const messages = Buffer.from('event: message_start\ndata: {"type":"message_start","message":{"role":"assistant"}}\n\nevent: content_block_start\ndata: {"type":"content_block_start","content_block":{"type":"tool_use","id":"call-1","name":"Read","input":{}}}\n\nevent: content_block_delta\ndata: {"type":"input_json_delta","partial_json":"{}"}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n');
test('bad grants and arbitrary/admin routes have no upstream effects', async t => {
  const r = await rig(t);
  for (const c of invalid) assert.equal((await r.post('/grant', jwt(c), { provider: 'mimo', protocol: 'responses' })).status, 401);
  assert.equal((await r.post('/grant', jwt({}, forged.privateKey), {})).status, 401);
  for (const b of [{ provider: 'unknown', protocol: 'responses' }, { provider: 'mimo', protocol: 'responses', keyID: 'chosen' }, { provider: 'mimo', protocol: 'responses', baseURL: 'http://evil' }]) assert.equal((await r.post('/grant', jwt(), b)).status, 403);
  for (const p of ['/api/governance/virtual-keys', '/openai/v1/chat/completions', '/anthropic/v1/messages/count_tokens', '/grant?x=1']) assert.equal((await r.post(p, 'bad', {})).status, 404);
  assert.equal((await fetch(r.url + '/openai/v1/responses', { method: 'POST', body: '{}' })).status, 401);
  assert.equal(r.adminRequests.length + r.inferenceRequests.length, 0);
});
test('idempotent grant, exact provider/key/model scope and header isolation over HTTP', async t => {
  const r = await rig(t); const [g, again] = await Promise.all([r.grant(), r.grant()]);
  assert.equal(g.capability, again.capability); assert.notEqual(g.capability, 'fixture-vk-1');
  assert.equal(r.adminRequests.length, 1);
  assert.deepEqual(r.adminRequests[0].body.provider_configs, [{ provider: 'mimo-responses', key_ids: [r.config.providers['mimo:responses'].keyID], allowed_models: ['mimo-v2.6-pro'] }]);
  assert.equal(r.adminRequests[0].body.allow_all_providers, false); assert.equal(Date.parse(r.adminRequests[0].body.expires_at), now + 60000);
  for (const b of [{ model: 'openrouter-responses/openai/gpt-4.1-mini' }, { provider: 'openrouter' }, { key_id: 'other' }, { api_key: 'caller' }, { extra_body: { provider: 'other' } }, { base_url: 'http://evil' }]) assert.equal((await r.infer(g, b)).status, 403);
  assert.equal((await r.post('/anthropic/v1/messages', g.capability, { model: g.model })).status, 403);
  const response = await r.infer(g, {}, { 'x-bf-vk': 'caller', 'x-bf-provider': 'openrouter', 'x-api-key': 'caller', 'anthropic-beta': 'unneeded' });
  assert.equal(response.status, 200); assert.deepEqual(Buffer.from(await response.arrayBuffer()), responses);
  const h = r.inferenceRequests[0].headers; assert.equal(h['x-bf-vk'], 'fixture-vk-1');
  for (const k of ['authorization', 'x-bf-provider', 'x-api-key', 'anthropic-beta']) assert.equal(h[k], undefined);
  const open = await r.grant('openrouter'); assert.deepEqual(Buffer.from(await (await r.infer(open)).arrayBuffer()), responses);
  assert.equal(r.inferenceRequests.at(-1).body.model, 'openrouter-responses/openai/gpt-4.1-mini');
});
test('native Messages tool-use bytes and required headers, HTTP errors and truncation', async t => {
  const r = await rig(t), g = await r.grant('mimo', 'messages');
  const response = await r.infer(g, { max_tokens: 64, messages: [{ role: 'user', content: 'review' }] }, { 'anthropic-version': '2023-06-01', 'anthropic-beta': 'fixture-beta' });
  assert.deepEqual(Buffer.from(await response.arrayBuffer()), messages);
  assert.equal(r.inferenceRequests[0].path, '/anthropic/v1/messages');
  assert.equal(r.inferenceRequests[0].headers['anthropic-version'], '2023-06-01');
  assert.equal(r.inferenceRequests[0].headers['anthropic-beta'], 'fixture-beta');
  const e = await r.infer(g, { metadata: { test_mode: 'http-error' } }); assert.equal(e.status, 422); assert.equal(await e.text(), '{"error":"rejected"}');
  const truncated = await r.infer(g, { metadata: { test_mode: 'truncate' } }); await assert.rejects(truncated.text());
});
// Red on the real CLI's client_metadata extension, or if it can change upstream routing.
test('Codex client metadata is accepted and discarded before upstream dispatch', async t => {
  const r = await rig(t), g = await r.grant();
  const response = await r.infer(g, { client_metadata: { client: 'codex', provider: 'other', base_url: 'http://evil', key_id: 'other' } });
  assert.equal(response.status, 200); await response.text();
  assert.equal(r.inferenceRequests.length, 1);
  assert.equal(r.inferenceRequests[0].body.model, g.model);
  assert.equal(r.inferenceRequests[0].body.client_metadata, undefined);
  assert.equal((await r.infer(g, { base_url: 'http://evil' })).status, 403);
  assert.equal(r.inferenceRequests.length, 1);
});
test('expiry, explicit revoke and durable replay denial', async t => {
  const r = await rig(t), g = await r.grant(); await r.broker.revoke(g.capability);
  assert.equal((await r.infer(g)).status, 401); assert.equal((await r.post('/grant', jwt(), { provider: 'mimo', protocol: 'responses' })).status, 403);
  const other = await r.grant('mimo', 'responses', '101'); r.advance(61000);
  assert.equal((await r.infer(other)).status, 401);
  assert.equal((await r.post('/grant', jwt({ run_id: '101' }), { provider: 'mimo', protocol: 'responses' })).status, 403);
  const restarted = await createBroker(r.config, r.options); const url = await listen(restarted.server);
  try { const denied = await fetch(url + '/grant', { method: 'POST', headers: { authorization: `Bearer ${jwt()}` }, body: JSON.stringify({ provider: 'mimo', protocol: 'responses' }) }); assert.equal(denied.status, 403); } finally { await restarted.close(); }
  assert.equal(r.adminRequests.filter(x => x.method === 'POST').length, 2);
});
test('2 MiB body bound, 32 dispatch bound, two concurrent streams and cancellation', async t => {
  const r = await rig(t), g = await r.grant();
  assert.equal((await r.infer(g, { input: 'x'.repeat(2 * 1024 * 1024) })).status, 413);
  assert.equal(r.inferenceRequests.length, 0);
  for (let i = 0; i < 31; i++) await (await r.infer(g)).text();
  assert.equal((await r.infer(g)).status, 429); assert.equal(r.inferenceRequests.length, 31);
  const live = await r.grant('mimo', 'responses', '102'); const a = new AbortController(), b = new AbortController();
  const first = await r.infer(live, { input: 'hold' }, {}, a.signal), second = await r.infer(live, { input: 'hold' }, {}, b.signal);
  assert.equal(r.held.size, 2); assert.equal((await r.infer(live)).status, 429);
  a.abort(); b.abort(); await assert.rejects(first.text()); await assert.rejects(second.text());
  await waitUntil(() => r.held.size === 0);
  assert.equal((await r.infer(live)).status, 200);
});
async function waitUntil(check) { const deadline = Date.now() + 2000; while (!check()) { if (Date.now() > deadline) assert.fail('Upstream stayed active'); await new Promise(r => setTimeout(r, 10)); } }
test('revocation aborts an active upstream generation, and unknown body routes never dispatch', async t => {
  const r = await rig(t), g = await r.grant();
  const stream = await r.infer(g, { input: 'hold' }); assert.equal(r.held.size, 1);
  await r.broker.revoke(g.capability); await assert.rejects(stream.text()); await waitUntil(() => r.held.size === 0);
  assert.equal((await r.infer(g)).status, 401);
});
test('invalid provider config and excessive TTL fail before network activity', async () => {
  const base = { ownerID: '13103045', workflowSHA: sha, ledgerPath: '/unused', providers: {}, ttlSeconds: 901 };
  await assert.rejects(createBroker(base), /TTL/);
  await assert.rejects(createBroker({ ...base, ttlSeconds: 60, providers: { 'mimo:responses': { alias: 'mimo', model: 'mimo-v2.6-pro', keyID: '00000000-0000-4000-8000-000000000001', apiKey: 'forbidden' } } }), /provider configuration/);
});
test('chunked body exceeding 2 MiB is rejected before inference', async t => {
  const r = await rig(t), g = await r.grant();
  const payload = Buffer.from(JSON.stringify({ model: g.model, input: 'x'.repeat(2 * 1024 * 1024) }));
  const stream = new ReadableStream({ start(controller) { controller.enqueue(payload.subarray(0, 1048576)); controller.enqueue(payload.subarray(1048576)); controller.close(); } });
  const rejected = await fetch(r.url + '/openai/v1/responses', { method: 'POST', headers: { authorization: `Bearer ${g.capability}`, 'content-type': 'application/json' }, body: stream, duplex: 'half' });
  assert.equal(rejected.status, 413); assert.equal(r.inferenceRequests.length, 0);
});
