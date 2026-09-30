// TRUSTED operator control lane; only prefixed synthetic accounts and mock hosts.
import { readFile, writeFile } from 'node:fs/promises';
import { AdminAPI } from '../customer.mjs';
import { nativeEvents } from '../evidence.mjs';
const admin = new AdminAPI({ baseURL: 'http://sub2api:8080', adminKey: (await readFile('/private/admin.key', 'utf8')).trim() });
const metadata = JSON.parse(await readFile('/private/roundtrip-workspaces.json', 'utf8'));
const receipt = { schema: 1, evidence_kind: 'synthetic-container', started_at: new Date().toISOString(), node: process.version, results: [], limitation: 'Actual private Sub2API gateway with synthetic upstream. No real agent or OAuth identity.' };
const accounts = []; const keys = {};
async function control(host, action, body) { const r = await fetch(`http://${host}:8081/__synthetic/${action}`, { method: body === undefined ? 'GET' : 'POST', headers: { 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(6000) }); if (!r.ok) throw Error('SYNTHETIC_CONTROL_ERROR'); return r.json(); }
async function measure(id, expected, task) {
  const start = Date.now(); const before = await control('mock-a', 'metrics'); const beforeB = await control('mock-b', 'metrics'); let status = 'PASS', actual;
  try { actual = await task(); } catch (e) { status = 'FAIL'; actual = { code: /^[A-Z_0-9]+$/.test(e.message) ? e.message : 'CONTAINER_SCENARIO_FAILURE' }; }
  const after = await control('mock-a', 'metrics'), afterB = await control('mock-b', 'metrics');
  receipt.results.push({ id, status, expected, actual, duration_ms: Date.now() - start, upstream_requests: after.requests + afterB.requests - before.requests - beforeB.requests, active_connections: after.active + afterB.active, limitation: receipt.limitation });
  await writeFile('/receipts/container-native.json', JSON.stringify(receipt, null, 2) + '\n');
  return status;
}
async function request(workspace, protocol, body = {}) {
  const key = keys[`${workspace}:${protocol}`];
  return fetch(`http://sub2api:8080/v1/${protocol}`, { method: 'POST', headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json', 'anthropic-version': '2023-06-01' }, body: JSON.stringify({ model: 'mimo-v2.6-pro', stream: true, max_tokens: 256, ...body }), redirect: 'error', signal: AbortSignal.timeout(8000) });
}
try {
  await writeFile('/private/container-native-started.json', '{}', { flag: 'wx', mode: 0o600 });
  for (const workspace of ['a', 'b']) {
    keys[`${workspace}:responses`] = (await readFile(`/private/workspace-${workspace}.key`, 'utf8')).trim();
    const a = await admin.call('POST', '/accounts', { name: `rr-sub2-spike-20260930-native-${workspace}`, platform: 'openai', type: 'apikey', credentials: { api_key: `synthetic-upstream-${workspace}`, base_url: `http://mock-${workspace}:8081/v1`, pool_mode: true, pool_mode_retry_count: 0 }, extra: { openai_responses_mode: 'force_responses', openai_passthrough: true }, group_ids: [metadata[workspace].groups['mimo:responses']], concurrency: 2, priority: 1 }); accounts.push(a.id);
  }
  // Create a private native Messages group, user and group-bound access key.
  const group = await admin.call('POST', '/groups', { name: 'rr-sub2-spike-20260930-messages', platform: 'anthropic', rate_multiplier: 1, is_exclusive: true });
  const password = 'synthetic-messages-password-20260930';
  await admin.call('POST', '/users', { email: 'rr-sub2-spike-20260930-messages@example.invalid', password, role: 'user', balance: 100, concurrency: 2, allowed_groups: [group.id], restrict_public_groups: true });
  const loginResponse = await fetch('http://sub2api:8080/api/v1/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: 'rr-sub2-spike-20260930-messages@example.invalid', password }), signal: AbortSignal.timeout(10000) });
  const login = (await loginResponse.json()).data; if (!login?.access_token) throw Error('SYNTHETIC_LOGIN_FAILED');
  const keyResponse = await fetch('http://sub2api:8080/api/v1/keys', { method: 'POST', headers: { authorization: `Bearer ${login.access_token}`, 'content-type': 'application/json' }, body: JSON.stringify({ name: 'rr-sub2-spike-20260930-messages', group_id: group.id, custom_key: 'synthetic-private-messages-key-20260930' }), signal: AbortSignal.timeout(10000) });
  keys['a:messages'] = (await keyResponse.json()).data?.key; if (!keys['a:messages']) throw Error('SYNTHETIC_KEY_FAILED');
  const msg = await admin.call('POST', '/accounts', { name: 'rr-sub2-spike-20260930-native-messages', platform: 'anthropic', type: 'apikey', credentials: { api_key: 'synthetic-upstream-a', base_url: 'http://mock-a:8081', pool_mode: true, pool_mode_retry_count: 0 }, extra: { anthropic_passthrough: true }, group_ids: [group.id], concurrency: 2, priority: 1 }); accounts.push(msg.id);
  for (const protocol of ['responses', 'messages']) {
    await measure(protocol === 'responses' ? 'A04' : 'A05', 'Native tool ID association survives two turns', async () => {
      const first = await nativeEvents(await request('a', protocol, protocol === 'messages' ? { messages: [{ role: 'user', content: 'Read wallet' }] } : { input: 'Read wallet' }), protocol);
      const id = protocol === 'responses' ? first.find(e => e.type === 'response.output_item.added')?.item?.call_id : first.find(e => e.type === 'content_block_start')?.content_block?.id;
      if (!id) throw Error('TOOL_CALL_MISSING');
      const second = await nativeEvents(await request('a', protocol, protocol === 'responses' ? { input: [{ type: 'function_call_output', call_id: id, output: '金🙂 actual synthetic tool result' }] } : { messages: [{ role: 'user', content: [{ type: 'tool_result', tool_use_id: id, content: '金🙂 actual synthetic tool result' }] }] }), protocol);
      if (!JSON.stringify(second).includes(id) || !JSON.stringify(second).includes('金🙂 actual synthetic tool result')) throw Error('TOOL_ASSOCIATION_LOST'); return { association_verified: true };
    });
  }
  const isolation = await measure('C05', 'Two private group keys reach distinct sentinel upstream identities', async () => {
    await Promise.all(['a', 'b'].map(async w => nativeEvents(await requestResponse(w), 'responses')));
    const a = await control('mock-a', 'metrics'), b = await control('mock-b', 'metrics');
    if (!a.observations.length || !b.observations.length || [...a.observations, ...b.observations].some(o => !o.identity_matches)) throw Error('CROSS_TENANT_IDENTITY');
    return { identity_matches: true, a_requests: a.requests, b_requests: b.requests };
  });
  if (isolation !== 'PASS') throw Error('ISOLATION_STOP');
  for (const [id, mode, protocol] of [['E01', 'http-429', 'responses'], ['E02', 'terminal-error', 'responses'], ['E03', 'terminal-error', 'messages'], ['E04', 'truncate', 'responses'], ['E05', 'reset', 'responses'], ['E11', 'partial-reset', 'responses']]) {
    await control('mock-a', 'config', { mode });
    const status = await measure(id, 'Failure remains observable with exactly one upstream effect', async () => {
      const before = (await control('mock-a', 'metrics')).requests; let failed = false, httpStatus;
      try { const r = await request('a', protocol); httpStatus = r.status; await nativeEvents(r, protocol); } catch { failed = true; }
      const count = (await control('mock-a', 'metrics')).requests - before;
      if (!failed || count !== 1) throw Error(count > 1 ? 'DUPLICATE_UPSTREAM_EFFECT' : 'FAILURE_MASKED_OR_NO_REQUEST');
      return { observable_failure: true, http_status: httpStatus ?? null, effects: count };
    });
    if (status !== 'PASS') break; // Stop after uncertain/duplicate effects; retain all prior failures.
  }
} catch (e) { receipt.setup_failure = /^[A-Z_0-9]+$/.test(e.message) ? e.message : 'CONTAINER_SETUP_FAILURE'; process.exitCode = 1; }
finally {
  await control('mock-a', 'config', { mode: 'native' }).catch(() => {});
  receipt.cleanup_failures = 0;
  for (const id of accounts) { try { await admin.call('DELETE', `/accounts/${id}`); } catch { receipt.cleanup_failures++; } }
  if (receipt.results.some(x => x.status === 'FAIL') || receipt.cleanup_failures) process.exitCode = 1;
  await writeFile('/receipts/container-native.json', JSON.stringify(receipt, null, 2) + '\n');
}
async function requestResponse(w) { return request(w, 'responses', { input: [{ type: 'function_call_output', call_id: 'sentinel', output: 'synthetic' }] }); }
