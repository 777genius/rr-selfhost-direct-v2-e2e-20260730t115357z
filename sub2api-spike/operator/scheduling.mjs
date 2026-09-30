// Actual engine scheduling, all accounts and inference strictly synthetic.
import { readFile, writeFile } from 'node:fs/promises';
import { AdminAPI } from '../customer.mjs';
import { nativeEvents } from '../evidence.mjs';
const admin = new AdminAPI({ baseURL: 'http://sub2api:8080', adminKey: (await readFile('/private/admin.key', 'utf8')).trim() });
const results = [], accountIDs = []; let key;
async function api(path, body, token) {
  const r = await fetch(`http://sub2api:8080/api/v1${path}`, { method: 'POST', headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(body), signal: AbortSignal.timeout(10000) });
  if (!r.ok) throw Error('SCHEDULER_SETUP_HTTP'); const j = await r.json(); if (j.code !== 0) throw Error('SCHEDULER_SETUP_API'); return j.data;
}
async function metrics() { return Promise.all(['mock-a', 'mock-b'].map(async h => (await fetch(`http://${h}:8081/__synthetic/metrics`, { signal: AbortSignal.timeout(6000) })).json())); }
async function request(session, signal) {
  const r = await fetch('http://sub2api:8080/v1/responses', { method: 'POST', headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json', session_id: session }, body: JSON.stringify({ model: 'mimo-v2.6-pro', stream: true, input: [{ type: 'function_call_output', call_id: 'scheduler', output: 'synthetic scheduling' }] }), signal: signal ?? AbortSignal.timeout(8000) });
  const e = await nativeEvents(r, 'responses'); const delta = e.find(x => x.type === 'response.output_text.delta')?.delta; if (!delta) throw Error('SCHEDULER_OUTPUT_MISSING'); return JSON.parse(delta).identity;
}
async function scenario(id, expected, task) {
  const start = Date.now(), before = await metrics(); let status = 'PASS', actual;
  try { actual = await task(); } catch (e) { status = 'FAIL'; actual = { code: /^[A-Z_0-9]+$/.test(e.message) ? e.message : 'SCHEDULING_OBSERVATION_FAILED' }; }
  const after = await metrics(); results.push({ id, status, expected, actual, upstream_requests: after.reduce((n,m,i) => n + m.requests - before[i].requests, 0), duration_ms: Date.now() - start, limitation: 'Actual Sub2API scheduler with two synthetic-only owned accounts; no OAuth or subscription identity.' });
  await writeFile('/receipts/scheduling.json', JSON.stringify({ schema: 1, evidence_kind: 'synthetic-container', results }, null, 2) + '\n');
}
try {
  await writeFile('/private/scheduling-started.json', '{}', { flag: 'wx', mode: 0o600 });
  const g = await admin.call('POST', '/groups', { name: 'rr-sub2-spike-20260930-scheduler', platform: 'openai', rate_multiplier: 1, is_exclusive: true });
  const password = 'synthetic-scheduler-password-20260930', email = 'rr-sub2-spike-20260930-scheduler@example.invalid';
  await admin.call('POST', '/users', { email, password, role: 'user', balance: 100, concurrency: 40, allowed_groups: [g.id], restrict_public_groups: true });
  const login = await api('/auth/login', { email, password });
  key = (await api('/keys', { name: 'rr-sub2-spike-20260930-scheduler', group_id: g.id, custom_key: 'synthetic-scheduler-private-key-20260930' }, login.access_token)).key;
  for (const [i, workspace] of ['a', 'b'].entries()) {
    const a = await admin.call('POST', '/accounts', { name: `rr-sub2-spike-20260930-scheduling-${workspace}`, platform: 'openai', type: 'apikey', credentials: { api_key: `synthetic-upstream-${workspace}`, base_url: `http://mock-${workspace}:8081/v1`, pool_mode: true, pool_mode_retry_count: 0 }, extra: { openai_responses_mode: 'force_responses', openai_passthrough: true }, group_ids: [g.id], concurrency: 2, priority: i * 10 }); accountIDs.push(a.id);
  }
  await scenario('F01', 'Priority selection; disable chooses remaining account; no available account fails', async () => {
    const first = await request('synthetic-schedule-first'); if (first !== 'synthetic-upstream-a') throw Error('PRIORITY_NOT_DETERMINISTIC');
    await admin.call('PUT', `/accounts/${accountIDs[0]}`, { status: 'inactive' });
    const second = await request('synthetic-schedule-second'); if (second !== 'synthetic-upstream-b') throw Error('DISABLED_ACCOUNT_SELECTED');
    await admin.call('PUT', `/accounts/${accountIDs[1]}`, { status: 'inactive' });
    let denied = false; try { await request('synthetic-no-available'); } catch { denied = true; } if (!denied) throw Error('NO_AVAILABLE_SUCCEEDED');
    await admin.call('PUT', `/accounts/${accountIDs[0]}`, { status: 'active' }); await admin.call('PUT', `/accounts/${accountIDs[1]}`, { status: 'active' });
    return { first, second, no_available_failed: true, cooldown_recovery_tested: false };
  });
  await scenario('F02', 'Fixed server session remains on account across priority change and tool turns', async () => {
    const first = await request('synthetic-sticky-1'); await admin.call('PUT', `/accounts/${accountIDs[0]}`, { priority: 20 });
    const second = await request('synthetic-sticky-1'); if (first !== second) throw Error('STICKY_AFFINITY_LOST'); return { first, second };
  });
  await scenario('F06', 'Account disable denies new work and documents current session selection', async () => {
    await admin.call('PUT', `/accounts/${accountIDs[0]}`, { status: 'inactive' }); const actual = await request('synthetic-disable-new'); if (actual !== 'synthetic-upstream-b') throw Error('DISABLED_ACCOUNT_ROUTED'); return { selected_identity: actual, active_stream_disable_tested: false };
  });
} catch (e) { results.push({ id: 'F01', status: 'FAIL', actual: { code: /^[A-Z_0-9]+$/.test(e.message) ? e.message : 'SCHEDULING_SETUP_FAILURE' }, limitation: 'Setup failure; no lifecycle success inferred.' }); process.exitCode = 1; }
finally {
  let cleanupFailures = 0; for (const id of accountIDs) { try { await admin.call('DELETE', `/accounts/${id}`); } catch { cleanupFailures++; } }
  if (results.some(x => x.status === 'FAIL') || cleanupFailures) process.exitCode = 1;
  await writeFile('/receipts/scheduling.json', JSON.stringify({ schema: 1, evidence_kind: 'synthetic-container', results, cleanup_failures: cleanupFailures }, null, 2) + '\n');
}
