import { readFile, writeFile, open, mkdir } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import http from 'node:http';
import { models, TEXT, CALL, TOOL, inspectSSE } from './wire.mjs';

const SOURCE = '96f4c115c9749078f90cbf210a01d39baf3f53b6';
const IMAGE = 'weishaw/sub2api@sha256:2e3b7fab1e84d2e862cde664d09c1ae84fc897093357cf200cbeb0f64b2f2390';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const stage = process.argv.includes('--recovery') ? 'recovery' : process.argv.includes('--lifecycle') ? 'lifecycle' : process.argv.includes('--faults-fixed') ? 'faults-fixed' : process.argv.includes('--faults') ? 'faults' : 'baseline';
const output = process.env.LAB_OUTPUT ?? '/evidence';
let cfg, journal, resources = [], tenants = {}, setupTotal = null;
const receipt = { schema: 'rr-sub2-real-lab/v1', evidence_kind: 'synthetic-container', source_sha: SOURCE, image: IMAGE,
  node: process.version, stage, run_mode: 'standard', model_mapping: models, started_at: new Date().toISOString(),
  real_actions_e2e: false, live_oauth: 'NOTRUN', receipt_state: 'pending', results: [], resources: [],
  limitations: ['Synthetic upstream fixtures are gateway fault evidence, not real Actions or agent-review proof.', 'Live OAuth refresh/rotation/revocation and production pool regression remain unproven.', 'Client RSS is not engine RSS. Engine RSS requires coordinator-supplied Docker stats.'] };
class LabError extends Error { constructor(code, httpStatus = null) { super(code); this.code = code; this.httpStatus = httpStatus; } }
function must(value, code) { if (!value) throw new LabError(code); }
async function api(path, method = 'GET', body, token = null) {
  const headers = { 'content-type': 'application/json' };
  if (token) headers.authorization = `Bearer ${token}`;
  else if (cfg.admin_jwt) headers.authorization = `Bearer ${cfg.admin_jwt}`;
  else headers['x-api-key'] = cfg.admin_api_key;
  let res;
  try { res = await fetch(`http://sub2api:8080/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(12000) }); }
  catch { throw new LabError('engine_admin_transport_failure'); }
  let data;
  try { data = await res.json(); } catch { throw new LabError('engine_admin_invalid_json', res.status); }
  if (!res.ok || (data.code !== undefined && data.code !== 0)) throw new LabError('engine_admin_rejected', res.status);
  return data.data ?? data;
}
async function control(path, body) {
  let res;
  try { res = await fetch(`http://mock:8099/__control/${path}`, { method: body ? 'POST' : 'GET', headers: { 'x-lab-control': cfg.control_token, 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(5000) }); }
  catch { throw new LabError('mock_control_unavailable'); }
  must(res.ok, 'mock_control_rejected');
  return res.json();
}
async function savePrivate() {
  await writeFile(`/private/${cfg.run_id}.resources.json`, JSON.stringify({ resources, tenants }), { mode: 0o600 });
  receipt.resources = resources;
}
async function create(kind, payload) {
  const data = await api(`/admin/${kind}`, 'POST', payload);
  must(Number.isSafeInteger(data.id) && data.id > 0, 'create_missing_id');
  resources.push({ kind, id: data.id });
  await savePrivate();
  return data;
}
async function setup() {
  const before = await control('records');
  setupTotal = before.total;
  // Four isolated groups: tenant A/B, native Messages, same-group scheduler pair.
  for (const [label, protocol, sentinels] of [['A', 'responses', ['A']], ['B', 'responses', ['B']], ['M', 'messages', ['M']], ['S', 'responses', ['S1', 'S2']]]) {
    const name = `rr-sub2-spike-20260930-lab-${cfg.run_id}-${label}`;
    const platform = protocol === 'responses' ? 'openai' : 'anthropic';
    const group = await create('groups', { name, platform, is_exclusive: true, subscription_type: 'standard', rate_multiplier: 1, fallback_group_id: null, fallback_group_id_on_invalid_request: null });
    const check = await api(`/admin/groups/${group.id}`);
    must(check.is_exclusive === true && !check.fallback_group_id && !check.fallback_group_id_on_invalid_request, 'group_not_exclusive_or_has_fallback');
    const accounts = [];
    for (const [i, identity] of sentinels.entries()) {
      const account = await create('accounts', { name: `${name}-${identity}`, platform, type: 'apikey', concurrency: label === 'S' ? 1 : 25, priority: i + 1, group_ids: [group.id], upstream_billing_probe_enabled: false,
        credentials: { api_key: cfg.sentinels[identity], base_url: protocol === 'responses' ? 'http://mock:8099/v1' : 'http://mock:8099', model_mapping: { [models[protocol]]: models[protocol] } },
        extra: protocol === 'responses' ? { openai_responses_mode: 'force_responses', openai_passthrough: true } : { anthropic_passthrough: true } });
      accounts.push({ id: account.id, identity });
    }
    const password = `rrlab-${randomUUID()}`;
    const email = `${name}@example.invalid`;
    const user = await create('users', { email, password, username: name, role: 'user', balance: 1000, concurrency: 25, allowed_groups: [group.id], restrict_public_groups: true });
    const auth = await api('/auth/login', 'POST', { email, password });
    must(typeof auth.access_token === 'string', 'synthetic_user_login_missing_token');
    const key = await api('/keys', 'POST', { name, group_id: group.id, expires_in_days: 1 }, auth.access_token);
    must(typeof key.key === 'string' && key.key.length > 10, 'synthetic_key_missing');
    resources.push({ kind: 'keys', id: key.id, user_id: user.id });
    tenants[label] = { key: key.key, user_token: auth.access_token, group_id: group.id, user_id: user.id, accounts, protocol };
    await savePrivate();
  }
  const after = await control('records');
  receipt.setup_upstream_requests = after.total - before.total;
  receipt.setup_background = after.records.filter(x => x.sequence > before.total).map(x => ({ identity: x.identity, protocol: x.protocol, path: x.path }));
}
function payload(protocol, id, turn = 0, large = false) {
  const text = `rrlab:${id} ${TEXT}`;
  if (protocol === 'responses') return { model: models.responses, stream: true, max_output_tokens: 64, prompt_cache_key: `rrlab-${cfg.run_id}-${id}`,
    tools: [{ type: 'function', name: 'echo', description: 'Synthetic echo', parameters: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'], additionalProperties: false } }],
    input: turn ? [{ role: 'user', content: text }, { type: 'function_call', id: 'fc_rr_lab_01', call_id: CALL, name: 'echo', arguments: JSON.stringify({ text: TEXT }) }, { type: 'function_call_output', call_id: CALL, output: text + (large ? TEXT.repeat(20000) : '') }] : [{ role: 'user', content: text }] };
  return { model: models.messages, max_tokens: 64, stream: true, tools: [{ name: 'echo', description: 'Synthetic echo', input_schema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] } }],
    messages: [{ role: 'user', content: text }, ...(turn ? [{ role: 'assistant', content: [{ type: 'tool_use', id: TOOL, name: 'echo', input: { text: TEXT } }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: TOOL, content: text + (large ? TEXT.repeat(20000) : '') }] }] : [])] };
}
// One HTTP call only. No client retries, redirects, or replays. Bounded byte collection.
function request(label, id, { turn = 0, timeout = 9000, cancel = false, slow = false, large = false } = {}) {
  const tenant = tenants[label];
  const started = performance.now();
  return new Promise(resolve => {
    let status = null, body = [], bytes = 0, transport = null, done = false, response;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      let parsed = { terminal: false, failed: false, malformed: false, success: false, calls: [], utf8: false, event_types: [] };
      try { if (status === 200) parsed = inspectSSE(Buffer.concat(body), tenant.protocol); } catch { parsed.malformed = true; }
      resolve({ http_status: status, transport, ...parsed, bytes, duration_ms: Math.round(performance.now() - started) });
    };
    const req = http.request(`http://sub2api:8080/v1/${tenant.protocol}`, { method: 'POST', headers: { authorization: `Bearer ${tenant.key}`, 'content-type': 'application/json', 'anthropic-version': '2023-06-01', 'session_id': `rrlab-${cfg.run_id}-${id}` } }, res => {
      response = res;
      status = res.statusCode;
      res.on('data', chunk => {
        bytes += chunk.length;
        if (bytes <= 12 * 1024 * 1024) body.push(chunk);
        else { transport = 'byte_limit'; req.destroy(); finish(); }
        if (cancel) { transport = 'client_cancelled'; req.destroy(); finish(); }
        if (slow) { res.pause(); setTimeout(() => res.resume(), 25); }
      });
      res.on('end', finish);
      res.on('aborted', () => { transport ??= 'response_aborted'; finish(); });
      res.on('error', () => { transport ??= 'response_error'; finish(); });
    });
    const timer = setTimeout(() => { transport = 'client_timeout'; response?.destroy(); req.destroy(); finish(); }, timeout);
    req.on('error', () => { transport ??= 'connection_error'; finish(); });
    req.end(JSON.stringify(payload(tenant.protocol, id, turn, large)));
  });
}
function normalized(rec) {
  return { sequence: rec.sequence, identity: rec.identity, protocol: rec.protocol, path: rec.path, model: rec.model, scenario: rec.scenario, finished: rec.finished, cancelled: rec.cancelled, committed: rec.committed, bytes: rec.bytes, backpressure: rec.backpressure, active_identity: rec.active_identity, tool_result_id: rec.tool_result_id, tool_result_utf8: rec.tool_result_utf8, tool_result_length: rec.tool_result_length, version_header: rec.version_header, upstream_duration_ms: rec.ended_ms === null ? null : rec.ended_ms - rec.started_ms };
}
async function test(id, observableFailure, fn) {
  if (stage.startsWith('faults') && ['A04', 'A05', 'C05', 'E01-A-400', 'E01-A-401', 'E01-M-400', 'E01-M-401', 'F02', 'F01-failover', 'F03'].includes(id)) return;
  const started = performance.now();
  const row = { id, status: 'FAIL', evidence_kind: 'synthetic-container', observable_failure: observableFailure, observations: {}, limitations: [] };
  receipt.results.push(row);
  try { await fn(row); row.status = 'PASS'; }
  catch (e) { row.failure_code = e instanceof LabError ? e.code : 'unexpected_lab_failure'; if (e instanceof LabError && e.httpStatus) row.admin_http_status = e.httpStatus; }
  row.duration_ms = Math.round(performance.now() - started);
  await flush();
  process.stdout.write(`${id} ${row.status}\n`);
}
async function sample(row, label, id, rule = {}, options = {}) {
  await control('rule', { id, ...rule });
  const before = await control('records');
  const result = await request(label, id, options);
  await sleep(options.cancel || result.transport ? 1200 : 100);
  const after = await control('records');
  must(!after.overflow, 'mock_record_overflow');
  const records = after.records.filter(x => x.sequence > before.total && x.case_id === id);
  const unrelated = after.records.filter(x => x.sequence > before.total && x.case_id !== id);
  const observations = { downstream: result, upstream_requests: records.length, engine_retries: Math.max(0, records.length - 1), upstream: records.map(normalized), background_requests: unrelated.length };
  row.observations.samples ??= [];
  row.observations.samples.push(observations);
  // Isolation and model/path invariants apply to faults as well as successes.
  const allowed = tenants[label].accounts.map(x => x.identity);
  must(records.every(x => allowed.includes(x.identity)), 'cross_group_or_unknown_account');
  must(records.every(x => x.protocol === tenants[label].protocol && x.model === models[tenants[label].protocol]), 'native_path_or_model_changed');
  return { result, records, observations };
}
function success(result) { must(result.http_status === 200 && result.success && !result.transport, 'missing_successful_native_terminal'); }
function single(records) { must(records.length === 1, 'unexpected_upstream_request_count'); }
async function recover(label) {
  for (const a of tenants[label].accounts) {
    await api(`/admin/accounts/${a.id}/clear-error`, 'POST', {});
    await api(`/admin/accounts/${a.id}/recover-state`, 'POST', {});
    await api(`/admin/accounts/${a.id}/clear-rate-limit`, 'POST', {});
    await api(`/admin/accounts/${a.id}/temp-unschedulable`, 'DELETE');
    await api(`/admin/accounts/${a.id}`, 'PUT', { status: 'active' });
    await api(`/admin/accounts/${a.id}/schedulable`, 'POST', { schedulable: true });
  }
  await sleep(250);
}
async function baseline() {
  for (const [id, label, call] of [['A04', 'A', CALL], ['A05', 'M', TOOL]]) {
    await test(id, 'Tool ID, result association, block order, native model or UTF-8 changes across two engine turns.', async row => {
      const first = await sample(row, label, id, { scenario: 'tool' });
      success(first.result); single(first.records);
      must(first.result.calls.includes(call), 'tool_call_id_lost');
      if (label === 'M') must(first.result.event_types.indexOf('content_block_start') < first.result.event_types.indexOf('content_block_stop'), 'message_block_order_changed');
      const second = await sample(row, label, id, { scenario: 'ok' }, { turn: 1, large: true });
      success(second.result); single(second.records);
      must(second.result.utf8 && second.records[0].tool_result_id === call && second.records[0].tool_result_utf8 && second.records[0].tool_result_length > 200000, 'tool_result_association_or_utf8_lost');
      row.limitations.push('Tool echo fixtures are synthetic native protocol tests; no actual agent or review execution.');
    });
  }
  await test('C05', 'Tenant key selects another exclusive group sentinel under concurrent requests.', async row => {
    await control('rule', { id: 'C05A', scenario: 'ok' });
    await control('rule', { id: 'C05B', scenario: 'ok' });
    const before = await control('records');
    const results = await Promise.all([request('A', 'C05A'), request('B', 'C05B')]);
    await sleep(100);
    const after = await control('records');
    const records = after.records.filter(x => x.sequence > before.total);
    row.observations = { downstream: results, upstream_requests: records.length, upstream: records.map(normalized) };
    results.forEach(success);
    must(records.filter(x => x.case_id === 'C05A').length === 1 && records.filter(x => x.case_id === 'C05B').length === 1, 'tenant_request_count_changed');
    must(records.every(x => (x.case_id === 'C05A' && x.identity === 'A') || (x.case_id === 'C05B' && x.identity === 'B')), 'tenant_crossover_or_background');
  });
  for (const label of ['A', 'M']) {
    for (const status of [400, 401, 403, 404, 429, 500, 502, 503]) {
      const id = `E01-${label}-${status}`;
      await test(id, 'Upstream HTTP error becomes successful terminal or crosses tenant/model; engine retries are measured.', async row => {
        await recover(label);
        const { result, records, observations } = await sample(row, label, id, { scenario: `http-${status}` });
        must(records.length > 0, 'no_upstream_fault_exercised');
        must(!result.success && (result.http_status >= 400 || result.failed || result.transport), 'http_error_hidden_as_success');
        observations.duplicate_effect_warning = records.length > 1;
        row.limitations.push('HTTP remapping is recorded; retry count is not inferred from client exceptions.');
      });
    }
    for (const scenario of ['failed', 'error', 'truncated', 'malformed', 'reset-before', 'reset-after', 'slow-headers', 'slow-body']) {
      const id = `E-${label}-${scenario}`;
      await test(id, 'Failed/error/missing terminal stream is accepted, or partial-stream outcome creates duplicate upstream effects.', async row => {
        await recover(label);
        const { result, records } = await sample(row, label, id, { scenario, delay_ms: 6000 }, { timeout: 2200 });
        must(records.length > 0, 'no_upstream_fault_exercised');
        must(!result.success, 'failed_stream_declared_success');
        if (scenario === 'failed' || scenario === 'error') must(result.failed || result.http_status >= 400, 'terminal_failure_signal_lost');
        if (scenario === 'reset-after') must(records.length === 1, 'duplicate_after_committed_stream');
        row.limitations.push('Client timeout bounds own connection; engine cancellation is assessed separately at mock.');
      });
    }
    await test(`E06-${label}`, 'Client disconnect leaves upstream alive or capacity unreleased.', async row => {
      await recover(label);
      const { records } = await sample(row, label, `E06-${label}`, { scenario: 'hold', delay_ms: 6000 }, { cancel: true });
      single(records);
      must(records[0].cancelled && records[0].ended_ms !== null && records[0].ended_ms - records[0].started_ms < 2500, 'engine_did_not_abort_upstream_promptly');
      const after = await sample(row, label, `E06-${label}-release`, { scenario: 'ok' });
      success(after.result); single(after.records);
    });
  }
  await test('E08', '429 routes outside exclusive group or produces a successful terminal.', async row => {
    await recover('A');
    const fault = await sample(row, 'A', 'E08', { scenario: 'http-429' });
    must(fault.records.length > 0 && !fault.result.success, '429_not_exercised_or_hidden');
    const state = await api(`/admin/accounts/${tenants.A.accounts[0].id}`);
    row.observations.cooldown = { rate_limited_at_present: !!state.rate_limited_at, rate_limit_reset_at_present: !!state.rate_limit_reset_at, status: ['active', 'inactive', 'error'].includes(state.status) ? state.status : 'OTHER' };
    const retry = await sample(row, 'A', 'E08-cooldown', { scenario: 'ok' });
    must(!retry.result.success && retry.records.length === 0, 'cooldown_not_enforced');
    await sleep(2300);
    const recovered = await sample(row, 'A', 'E08-recovery', { scenario: 'ok' });
    success(recovered.result); single(recovered.records);
  });
  await test('F02', 'Same-group sticky tool turns switch sentinel or duplicate effects.', async row => {
    await recover('S');
    const a = await sample(row, 'S', 'F02', { scenario: 'tool' });
    const b = await sample(row, 'S', 'F02', { scenario: 'ok' }, { turn: 1 });
    success(a.result); success(b.result); single(a.records); single(b.records);
    must(a.records[0].identity === b.records[0].identity, 'sticky_account_changed');
  });
  await test('E10-E11', 'Failover after committed partial stream duplicates side effects.', async row => {
    await recover('S');
    const { result, records } = await sample(row, 'S', 'E10-E11', { scenario: 'reset-after' });
    single(records); must(records[0].committed && !result.success, 'partial_stream_not_exercised_or_hidden');
  });
  await test('F01-failover', 'Pre-stream failure cannot use the other explicitly allowed account.', async row => {
    await recover('S');
    const { result, records } = await sample(row, 'S', 'F01-failover', { accounts: { S1: 'http-503', S2: 'ok' } });
    success(result);
    must(records.some(x => x.identity === 'S1') && records.some(x => x.identity === 'S2'), 'allowed_precommit_failover_not_observed');
    row.observations.duplicate_effect_warning = records.length > 1;
    row.limitations.push('Synthetic 503 has no paid effect; precommit retry remains a duplicate-attempt warning.');
  });
  await test('F03', 'Per-account concurrency exceeds one, queue does not drain, or cancellation leaves capacity stuck.', async row => {
    await recover('S');
    await control('rule', { id: 'F03', scenario: 'hold', delay_ms: 350 });
    const before = await control('records');
    const results = await Promise.all(Array.from({ length: 5 }, () => request('S', 'F03')));
    await sleep(100);
    const after = await control('records');
    const records = after.records.filter(x => x.sequence > before.total && x.case_id === 'F03');
    row.observations = { downstream: results, upstream_requests: records.length, upstream: records.map(normalized) };
    results.forEach(success);
    must(records.length === 5 && records.every(x => x.active_identity <= 1 && x.finished && ['S1', 'S2'].includes(x.identity)), 'account_concurrency_or_drain_failed');
    row.limitations.push('Global concurrency configuration and crash release require operator lifecycle receipt.');
  });
  await test('E07', 'Slow consumer loses terminal, duplicates effects, or upstream remains stuck after bounded pressure.', async row => {
    await recover('A');
    const rssBefore = process.memoryUsage().rss;
    const { result, records } = await sample(row, 'A', 'E07', { scenario: 'backpressure' }, { slow: true, timeout: 12000 });
    row.observations.control_rss_delta_bytes = process.memoryUsage().rss - rssBefore;
    success(result); single(records); must(records[0].finished, 'backpressure_worker_stuck');
    row.limitations.push('8 MiB comment stream; engine RSS unavailable unless coordinator stats supplied. No engine-memory bound claimed.');
  });
  await load();
}
async function load() {
  await recover('A');
  for (const concurrency of [1, 5, 20]) {
    await test(`G05-${concurrency}`, 'Concurrent native requests fail, duplicate, cross sentinel, or remain open.', async row => {
      const id = `G05-${concurrency}`;
      await control('rule', { id, scenario: 'ok' });
      const before = await control('records');
      const results = await Promise.all(Array.from({ length: concurrency }, () => request('A', id)));
      await sleep(100);
      const after = await control('records');
      const records = after.records.filter(x => x.sequence > before.total && x.case_id === id);
      row.observations = { ...metrics(results), upstream_requests: records.length, engine_retries: Math.max(0, records.length - concurrency), identities: [...new Set(records.map(x => x.identity))], stuck_upstream: records.filter(x => !x.ended_ms).length };
      results.forEach(success);
      must(records.length === concurrency && records.every(x => x.identity === 'A' && x.finished), 'load_duplicate_crossover_or_stuck');
    });
  }
  await test('G05-soak', 'Bounded synthetic soak produces error/duplicate/stuck connections or tenant crossover.', async row => {
    const duration = 30000, concurrency = 5, maxRequests = 500;
    const deadline = performance.now() + duration;
    await control('rule', { id: 'G05-soak', scenario: 'ok' });
    const before = await control('records');
    const results = [];
    while (performance.now() < deadline && results.length < maxRequests) {
      results.push(...await Promise.all(Array.from({ length: Math.min(concurrency, maxRequests - results.length) }, () => request('A', 'G05-soak'))));
      await sleep(300);
    }
    await sleep(200);
    const after = await control('records');
    const records = after.records.filter(x => x.sequence > before.total && x.case_id === 'G05-soak');
    row.observations = { ...metrics(results), max_requests: maxRequests, duration_bound_ms: duration, upstream_requests: records.length, engine_retries: Math.max(0, records.length - results.length), stuck_upstream: records.filter(x => !x.ended_ms).length };
    results.forEach(success);
    must(records.length === results.length && records.every(x => x.identity === 'A' && x.finished), 'soak_duplicate_crossover_or_stuck');
  });
}
function metrics(results) {
  const sorted = results.map(x => x.duration_ms).sort((a, b) => a - b);
  return { client_requests: results.length, errors: results.filter(x => !x.success || x.transport || x.http_status !== 200).length,
    p50_ms: sorted[Math.floor((sorted.length - 1) * .5)] ?? null, p95_ms: sorted[Math.floor((sorted.length - 1) * .95)] ?? null,
    control_rss_bytes: process.memoryUsage().rss, engine_rss_bytes: null };
}
async function lifecycle() {
  // Coordinator only: read this ready signal, then stop/start OWN engine while hold is active.
  await test('G02-active-restart', 'Own engine restart hides stream failure or causes duplicate upstream effects.', async row => {
    await recover('A');
    await control('rule', { id: 'G02-active', scenario: 'hold', delay_ms: 10000 });
    const before = await control('records');
    const pending = request('A', 'G02-active', { timeout: 18000 });
    let started = false;
    for (let i = 0; i < 40; i++) {
      const state = await control('records');
      if (state.records.some(x => x.sequence > before.total && x.case_id === 'G02-active' && x.committed && !x.ended_ms)) { started = true; break; }
      await sleep(100);
    }
    must(started, 'active_stream_not_observed');
    await writeFile(`/private/${cfg.run_id}.restart-ready`, 'Stop/start ONLY owned engine now.\n', { flag: 'wx', mode: 0o600 });
    const result = await pending;
    const after = await control('records');
    const records = after.records.filter(x => x.sequence > before.total && x.case_id === 'G02-active');
    row.observations = { downstream: result, upstream_requests: records.length, upstream: records.map(normalized) };
    must(records.length === 1 && !result.success && !!result.transport, 'restart_not_observed_or_hidden_or_duplicate');
    row.limitations.push('Coordinator must attach normalized container restart timestamps to establish cause.');
  });
}
async function recovery() {
  await test('G01-recovery', 'Recovered engine loses synthetic group/account/key persistence or crosses tenant.', async row => {
    for (const label of ['A', 'B', 'M', 'S']) {
      const group = await api(`/admin/groups/${tenants[label].group_id}`);
      must(group.is_exclusive && !group.fallback_group_id && !group.fallback_group_id_on_invalid_request, 'recovered_group_boundary_changed');
      for (const a of tenants[label].accounts) {
        const account = await api(`/admin/accounts/${a.id}`);
        must(account.group_ids?.length === 1 && account.group_ids[0] === tenants[label].group_id, 'recovered_account_binding_changed');
      }
      await recover(label);
      const { result, records } = await sample(row, label, `G01-recovery-${label}`, { scenario: 'ok' });
      success(result); single(records);
    }
    row.limitations.push('Recovery must be paired with coordinator outage and restore timestamps; this alone is a persistence read/forward probe.');
  });
}
async function flush() {
  await mkdir(output, { recursive: true });
  await writeFile(`${output}/${cfg?.run_id ?? 'invalid-config'}-${stage}.json`, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
}
try {
  cfg = JSON.parse(await readFile(process.env.LAB_CONFIG ?? '/private/lab.json', 'utf8'));
  must(/^[a-z0-9-]{1,36}$/.test(cfg.run_id ?? ''), 'invalid_run_id');
  must(cfg.admin_jwt || cfg.admin_api_key, 'admin_auth_missing');
  must(typeof cfg.control_token === 'string' && cfg.control_token.length >= 24, 'control_token_missing');
  for (const name of ['A', 'B', 'M', 'S1', 'S2']) must(typeof cfg.sentinels?.[name] === 'string' && cfg.sentinels[name].startsWith('rr-synthetic-') && !cfg.sentinels[name].startsWith('sk-'), 'synthetic_sentinel_missing');
  must(new Set(Object.values(cfg.sentinels)).size === 5, 'sentinel_identity_collision');
  journal = await open(`/private/${cfg.run_id}.${stage}.journal`, 'wx', 0o600);
  await journal.writeFile(JSON.stringify({ started_at: receipt.started_at, stage, source_sha: SOURCE }) + '\n');
  receipt.run_id = cfg.run_id;
  receipt.config_mode = 'private-admin-auth; synthetic-user-keys; standard; trusted-HTTP-mock-only';
  receipt.pin_evidence = 'operator must confirm deployed digest/source; constants are expected pins';
  if (stage === 'baseline') { await setup(); await baseline(); }
  else {
    const manifest = JSON.parse(await readFile(`/private/${cfg.run_id}.resources.json`, 'utf8'));
    resources = manifest.resources; tenants = manifest.tenants;
    must(Object.keys(tenants).length === 4, 'incomplete_private_manifest');
    receipt.resources = resources;
    if (stage === 'lifecycle') await lifecycle(); else if (stage.startsWith('faults')) await baseline(); else await recovery();
  }
  for (const [id, reason] of [['F04-F05', 'No synthetic OAuth refresh server/identity supplied; API-key scheduling does not prove OAuth lifecycle.'], ['F07-F08', 'Live OAuth test identity absent.'], ['G01-outage', 'Requires separate operator outage run and normalized receipt.'], ['G04', 'Separate database restore and stale-key behavior require coordinator receipt.'], ['G07', 'Network/public-port and teardown verification require coordinator receipt.']]) receipt.results.push({ id, status: 'NOTRUN', evidence_kind: 'synthetic-container', observable_failure: reason, limitations: [reason] });
  receipt.receipt_state = 'executed';
} catch (e) {
  receipt.receipt_state = 'failed';
  receipt.failure_code = e instanceof LabError ? e.code : e?.code === 'EEXIST' ? 'ambiguous_rerun_refused' : 'configuration_setup_or_runtime_failure';
  process.exitCode = 1;
} finally {
  receipt.ended_at = new Date().toISOString();
  try {
    if (cfg?.control_token) { const state = await control('records'); receipt.mock_total_upstream_requests = state.total; receipt.mock_active_at_end = state.active; receipt.mock_record_overflow = state.overflow; }
    await flush();
    await journal?.close();
  } catch { process.stderr.write('normalized receipt write failure (details withheld)\n'); process.exitCode = 1; }
}
if (receipt.results.some(x => x.status === 'FAIL')) process.exitCode = 1;
