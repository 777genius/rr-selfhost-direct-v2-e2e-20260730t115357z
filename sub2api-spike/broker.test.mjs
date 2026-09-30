import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, rename } from 'node:fs/promises';
import { join } from 'node:path';
import { rig, token } from './test-support.mjs';
import { createBroker } from './broker.mjs';
import { nativeEvents } from './evidence.mjs';
import { listen, stop } from './util.mjs';
// Regression: concurrent exchanges issue two capabilities or server access keys.
test('B06 concurrent grants idempotent before upstream effects', async t => {
  const r = await rig(t); const responses = await Promise.all(Array.from({ length: 12 }, () => r.grant()));
  const grants = await Promise.all(responses.map(x => x.json())); assert.equal(new Set(grants.map(g => g.capability)).size, 1); assert.equal(r.upstream.metrics.requests, 0);
});
// Regression: revoked/closed run can replay or select a new native protocol.
test('B07 revoked grant denies replay and provider rescope', async t => {
  const r = await rig(t); const g = await (await r.grant()).json();
  assert.equal((await fetch(`${r.url}/grant`, { method: 'DELETE', headers: { authorization: `Bearer ${g.capability}` } })).status, 200);
  assert.equal((await r.grant()).status, 409); assert.equal((await r.grant('messages')).status, 409); assert.equal((await r.request(g.capability)).status, 401); assert.equal(r.upstream.metrics.requests, 0);
});
// Regression: caller URL/model/group/header steers another identity or admin route.
test('A07 A08 B08 B12 pinned model routes headers and unsupported scopes', async t => {
  const r = await rig(t); const g = await (await r.grant()).json();
  for (const body of [{ model: 'wrong' }, { group_id: 2 }, { baseURL: 'http://169.254.169.254' }, { account_id: 2 }]) assert.equal((await r.request(g.capability, body)).status, 400);
  for (const path of ['/admin/accounts', '/v1/chat/completions', '/v1/responses?group=2', '/v1/messages', '/debug']) assert.equal((await r.request(g.capability, {}, path)).status, 404);
  assert.equal((await r.grant('responses', { run_id: '124' }, { provider: 'unknown' })).status, 400);
  assert.equal(r.upstream.metrics.requests, 0);
  await nativeEvents(await r.request(g.capability, {}, '/v1/responses', { 'x-api-key': 'synthetic-caller', 'x-group-id': '2', 'x-forwarded-for': '127.0.0.1' }), 'responses');
  const o = r.upstream.observations[0]; assert.equal(o.body.model, 'mimo-v2.6-pro'); assert.equal(o.headers.authorization, 'Bearer synthetic-private-a'); for (const k of ['x-api-key', 'x-group-id', 'x-forwarded-for']) assert.equal(o.headers[k], undefined);
});
// Regression: Claude SDK's feature query is blocked or arbitrary queries gain access.
test('A03 A09 exact Claude beta query preserves native Messages', async t => {
  const r = await rig(t); const g = await (await r.grant('messages')).json();
  await nativeEvents(await r.request(g.capability, {}, '/anthropic/v1/messages?beta=true'), 'messages');
  assert.equal(r.upstream.observations[0].path, '/v1/messages?beta=true');
  for (const path of ['/anthropic/v1/messages?beta=true&group=2', '/anthropic/v1/messages?beta=false', '/v1/responses?beta=true']) assert.equal((await r.request(g.capability, {}, path)).status, 404);
  assert.equal(r.upstream.metrics.requests, 1);
});
// Regression: business data and tool schema property names are mistaken for routing.
test('A04 native structured content cannot change server-pinned identity', async t => {
  const r = await rig(t); const g = await (await r.grant()).json();
  const input = [{ role: 'user', content: [{ type: 'input_text', text: 'account data' }], account: { group_id: 9, workspace: 'b' } }];
  await nativeEvents(await r.request(g.capability, { input, metadata: { account: 'customer' } }), 'responses');
  const observed = r.upstream.observations[0];
  assert.deepEqual(observed.body.input, input); assert.deepEqual(observed.body.metadata, { account: 'customer' });
  assert.equal(observed.headers.authorization, 'Bearer synthetic-private-a'); assert.equal(observed.body.model, 'mimo-v2.6-pro');
});
// Regression: upstream diagnostic in an HTTP200 failed terminal exposes its credential.
for (const protocol of ['responses', 'messages']) test(`D05 native ${protocol} failed SSE removes upstream diagnostics`, async t => {
  const r = await rig(t, { mock: { mode: 'terminal-error' } }); const g = await (await r.grant(protocol)).json();
  const response = await r.request(g.capability, {}, `/v1/${protocol}`); const text = await response.text();
  assert.equal(response.status, 200); assert.ok(text.includes('Upstream request failed')); assert.ok(!text.includes('synthetic_failure'));
  assert.ok(!text.includes('synthetic-provider-credential-sentinel'));
  await assert.rejects(nativeEvents(new Response(text, { headers: { 'content-type': 'text/event-stream' } }), protocol));
  assert.equal(r.upstream.metrics.requests, 1);
});
test('D05 capability denies an unfiltered nonstream response mode before upstream effects', async t => {
  const r = await rig(t); const g = await (await r.grant()).json();
  assert.equal((await r.request(g.capability, { stream: false })).status, 400); assert.equal(r.upstream.metrics.requests, 0);
  await nativeEvents(await r.request(g.capability), 'responses'); assert.equal(r.upstream.observations[0].body.stream, true);
});
// Regression: body cap or request/concurrent reservation occurs after provider effects.
test('B09 body request and concurrency limits before effects', async t => {
  const r = await rig(t, { mock: { mode: 'slow-body', delayMs: 250 }, broker: { maxRequests: 2 } }); const g = await (await r.grant()).json();
  const tooBig = await r.request(g.capability, { input: 'x'.repeat(2 * 1024 * 1024) }); assert.equal(tooBig.status, 413); assert.equal(r.upstream.metrics.requests, 0);
  const a = await r.request(g.capability); const b = await r.request(g.capability); assert.equal((await r.request(g.capability)).status, 429);
  await Promise.all([a.text(), b.text()]); assert.equal((await r.request(g.capability)).status, 429); assert.equal(r.upstream.metrics.requests, 2);
});
// Regression: restart loses replay denial, or disk errors allow fresh grants.
test('B10 G03 restart denies stale capabilities replay and ledger failure', async t => {
  const r = await rig(t); const g = await (await r.grant()).json(); await stop(r.broker);
  const next = await createBroker(r.config); const url = await listen(next); t.after(() => stop(next));
  assert.equal((await fetch(`${url}/v1/responses`, { method: 'POST', headers: { authorization: `Bearer ${g.capability}` }, body: '{}' })).status, 401);
  assert.equal((await fetch(`${url}/grant`, { method: 'POST', headers: { authorization: `Bearer ${token()}` }, body: '{"provider":"mimo","protocol":"responses"}' })).status, 409);
  await rename(join(r.dir, 'ledger.json'), join(r.dir, 'old.json')); await mkdir(join(r.dir, 'ledger.json'));
  const failed = await fetch(`${url}/grant`, { method: 'POST', headers: { authorization: `Bearer ${token({ run_id: '125' })}` }, body: '{"provider":"mimo","protocol":"responses"}' }); assert.equal(failed.status, 503);
  assert.equal((await fetch(`${url}/grant`, { method: 'POST', headers: { authorization: `Bearer ${token({ run_id: '126' })}` }, body: '{}' })).status, 503); assert.equal(r.upstream.metrics.requests, 0);
});
// Regression: revoked/expired stream stays alive and consumes concurrency forever.
for (const reason of ['expiry', 'revoke']) test(`B11 E06 active stream ${reason} aborts upstream releases capacity`, async t => {
  const r = await rig(t, { mock: { mode: 'slow-body', delayMs: 1000 }, broker: { ttlMs: reason === 'expiry' ? 150 : 3000 } }); const g = await (await r.grant()).json();
  const stream = await r.request(g.capability); const pending = stream.text();
  if (reason === 'revoke') await fetch(`${r.url}/grant`, { method: 'DELETE', headers: { authorization: `Bearer ${g.capability}` } });
  await assert.rejects(pending); await new Promise(resolve => setTimeout(resolve, 50));
  assert.equal(r.upstream.metrics.active, 0); assert.equal(r.upstream.metrics.aborted, 1); assert.equal((await r.request(g.capability)).status, 401);
});
// Regression: removing membership leaves bearer authority valid for new work.
test('C04 membership removal blocks new grants and work', async t => {
  let enabled = true; const r = await rig(t, { broker: { isWorkspaceActive: () => enabled } }); const g = await (await r.grant()).json(); enabled = false;
  assert.equal((await r.request(g.capability)).status, 403); assert.equal((await r.grant('responses', { run_id: '124' })).status, 403); assert.equal(r.upstream.metrics.requests, 0);
});
// Regression: responses tool IDs or Messages content order/beta are rewritten.
for (const protocol of ['responses', 'messages']) test(`${protocol === 'responses' ? 'A04' : 'A05'} A09 native ${protocol} two-turn wire preservation`, async t => {
  const r = await rig(t); const g = await (await r.grant(protocol)).json(); const path = `/v1/${protocol}`;
  const first = await nativeEvents(await r.request(g.capability, {}, path, { 'anthropic-version': '2023-06-01', 'anthropic-beta': 'synthetic-beta' }), protocol);
  const id = protocol === 'responses' ? first.find(e => e.type === 'response.output_item.added').item.call_id : first.find(e => e.type === 'content_block_start').content_block.id;
  const body = protocol === 'responses' ? { input: [{ type: 'function_call_output', call_id: id, output: '金🙂 tool result' }] } : { messages: [{ role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: '金🙂 tool result' }] }] };
  const second = await nativeEvents(await r.request(g.capability, body, path), protocol);
  assert.ok(JSON.stringify(second).includes('金🙂 tool result')); assert.ok(JSON.stringify(second).includes(id)); assert.deepEqual(r.upstream.observations[1].body, { ...body, stream: true, model: 'mimo-v2.6-pro' });
  assert.equal(r.upstream.observations[0].path, path); assert.equal(r.upstream.observations[0].headers['anthropic-version'], '2023-06-01'); assert.equal(r.upstream.observations[0].headers['anthropic-beta'], 'synthetic-beta'); assert.equal(r.upstream.metrics.requests, 2);
});
// Regression: UTF-8/SSE chunk boundaries corrupt large tool/final payloads.
test('A10 E07 large unicode chunks retain bounded transport integrity', async t => {
  const r = await rig(t, { mock: { mode: 'large' } }); const g = await (await r.grant()).json(); const e = await nativeEvents(await r.request(g.capability, { input: [{ type: 'function_call_output', call_id: 'large', output: '金🙂'.repeat(10000) }] }), 'responses');
  const result = JSON.parse(e.find(x => x.type === 'response.output_text.delta').delta); assert.equal(result.padding, '金🙂'.repeat(50000)); assert.equal(result.toolResult.output, '金🙂'.repeat(10000)); assert.equal(r.upstream.metrics.active, 0);
});
// Regression: error codes become HTTP200; echoed provider credentials enter logs/UI.
test('E01 E09 E12 D02 D08 HTTP errors sanitized with status and count intact', async t => {
  const logs = []; const r = await rig(t, { mock: { mode: body => `http-${body.test_status}` }, broker: { log: x => logs.push(x) } }); const g = await (await r.grant()).json();
  for (const status of [400, 401, 403, 404, 429, 500, 502, 503]) { const response = await r.request(g.capability, { test_status: status }); assert.equal(response.status, status); const text = await response.text(); assert.ok(!text.includes('synthetic-provider-credential-sentinel')); assert.ok(text.includes('upstream_http_error')); }
  assert.equal(r.upstream.metrics.requests, 8); assert.ok(!JSON.stringify(logs).includes('sentinel')); assert.ok(!JSON.stringify(logs).includes('test_status')); assert.ok(!JSON.stringify(logs).includes('synthetic-private'));
});
// Regression: failed/truncated/malformed SSE is counted as successful native work.
for (const [id, mode, protocol] of [['E02', 'terminal-error', 'responses'], ['E03', 'terminal-error', 'messages'], ['E04', 'truncate', 'responses'], ['E04', 'malformed', 'messages']]) test(`${id} ${mode} ${protocol} fails terminal validator`, async t => {
  const r = await rig(t, { mock: { mode } }); const g = await (await r.grant(protocol)).json(); await assert.rejects(async () => nativeEvents(await r.request(g.capability, {}, `/v1/${protocol}`), protocol)); assert.equal(r.upstream.metrics.requests, 1);
});
// Regression: uncertain/reset/timeout triggers duplicate paid request or hangs.
for (const mode of ['reset', 'slow-headers', 'slow-body', 'partial-reset']) test(`E05 E11 ${mode} bounded failure zero automatic retries`, async t => {
  const r = await rig(t, { mock: { mode, delayMs: 500 }, broker: { timeoutMs: 100 } }); const g = await (await r.grant()).json(); const before = Date.now();
  let failed = false; try { await nativeEvents(await r.request(g.capability), 'responses'); } catch { failed = true; }
  assert.equal(failed, true); assert.ok(Date.now() - before < 1000); assert.equal(r.upstream.metrics.requests, 1);
});
// Regression: cross-tenant runs use shared permanent key, response/account crossover.
test('G06 two concurrent tenant identities select distinct private keys', async t => {
  const r = await rig(t); const ga = await (await r.grant()).json(); const gb = await (await r.grant('responses', { run_id: '223' })).json();
  await Promise.all([nativeEvents(await r.request(ga.capability), 'responses'), nativeEvents(await r.request(gb.capability), 'responses')]);
  assert.deepEqual(new Set(r.upstream.observations.map(o => o.headers.authorization)), new Set(['Bearer synthetic-private-a', 'Bearer synthetic-private-b']));
});
// Regression: native client cancellation leaves upstream worker/capacity occupied.
test('E06 client stream cancellation aborts upstream and allows next request', async t => {
  const r = await rig(t, { mock: { mode: 'slow-body', delayMs: 500 }, broker: { maxConcurrent: 1 } }); const g = await (await r.grant()).json();
  const response = await r.request(g.capability); await response.body.cancel(); await new Promise(resolve => setTimeout(resolve, 50));
  assert.equal(r.upstream.metrics.active, 0); assert.equal(r.upstream.metrics.aborted, 1);
  await nativeEvents(await r.request(g.capability), 'responses'); assert.equal(r.upstream.metrics.requests, 2);
});
// Regression: server-owned run session changes across tool turns or caller overrides it.
test('F02 server session stable per grant and isolated across tenants', async t => {
  const r = await rig(t); const a = await (await r.grant()).json(); const b = await (await r.grant('responses', { run_id: '223' })).json();
  for (const c of [a.capability, a.capability, b.capability]) await nativeEvents(await r.request(c, {}, '/v1/responses', { session_id: 'caller-steering', 'openai-beta': 'responses=v1', 'x-codex-beta-features': 'synthetic-native-feature' }), 'responses');
  const o = r.upstream.observations; assert.equal(o[0].headers.session_id, o[1].headers.session_id); assert.notEqual(o[0].headers.session_id, o[2].headers.session_id); assert.notEqual(o[0].headers.session_id, 'caller-steering'); assert.equal(o[0].headers['x-codex-beta-features'], 'synthetic-native-feature');
});
// Regression: account authority change fails to abort already issued workspace grant.
test('C08 F06 server account-authority revocation cancels only owned workspace', async t => {
  const r = await rig(t); const a = await (await r.grant()).json(); const b = await (await r.grant('responses', { run_id: '223' })).json(); r.broker.revokeWorkspace('a');
  assert.equal((await r.request(a.capability)).status, 401); await nativeEvents(await r.request(b.capability), 'responses'); assert.equal(r.upstream.metrics.requests, 1);
});
