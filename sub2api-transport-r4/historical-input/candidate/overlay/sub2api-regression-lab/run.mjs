import { mkdir, readFile } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { createBroker } from '../sub2api-spike/broker.mjs'; // read-only existing implementation
import { admin, control, fetchJSON, loadConfig, save, mono, sleep, must, MiB } from './common.mjs';
import { request, success } from './client.mjs';
import { models, CALL, TOOL } from './wire.mjs';
import { cancellationVerdict, uncertaintyVerdict } from './receipts.mjs';
import { cases, budget } from './plan.mjs';
import { telemetryVerdict } from '../sub2api-transport-r2/adapter.mjs';
const out = '/evidence';
async function waitFor(c, id, predicate, ms = 6000) {
  const end = Math.min(mono() + ms, c.deadline);
  while (mono() < end) {
    const state = await control(c, 'state');
    must(!state.exceeded && state.total < 2000, 'GLOBAL_UPSTREAM_BUDGET');
    const rs = state.records.filter(r => r.id === id);
    if (predicate(rs)) return rs;
    await sleep(50);
  }
  throw Object.assign(Error('OBSERVATION_DEADLINE'), { labCode: 'OBSERVATION_DEADLINE' });
}
async function setup(c, spec, row, owned) {
  const name = `rr-transport-${c.run_id}-${spec.id}`;
  const create = async (kind, body) => {
    // Persist ambiguity BEFORE calling actual admin; never retry a create.
    owned.intent = { kind, name }; await save(owned.path, owned);
    const obj = await admin(c, `/admin/${kind}`, 'POST', body);
    must(Number.isSafeInteger(obj.id) && obj.id > 0, 'CREATED_ID_MISSING');
    owned.resources.push({ kind, id: obj.id }); owned.intent = null; await save(owned.path, owned); return obj;
  };
  const platform = spec.protocol === 'responses' ? 'openai' : 'anthropic';
  const group = await create('groups', { name, platform, is_exclusive: true, subscription_type: 'standard', rate_multiplier: 1,
    fallback_group_id: null, fallback_group_id_on_invalid_request: null });
  const account = await create('accounts', { name, platform, type: 'apikey', concurrency: spec.stage === 'cancel' ? 1 : 25, priority: 1, group_ids: [group.id],
    upstream_billing_probe_enabled: false,
    credentials: { api_key: c.sentinels[spec.protocol], base_url: spec.protocol === 'responses' ? `${c.mock_url}/v1` : c.mock_url,
      pool_mode: true, pool_mode_retry_count: 0, model_mapping: { [models[spec.protocol]]: models[spec.protocol] } },
    extra: spec.protocol === 'responses' ? { openai_responses_mode: 'force_responses', openai_passthrough: true } : { anthropic_passthrough: true } });
  const password = randomBytes(24).toString('hex'), email = `${name}@example.invalid`;
  await create('users', { email, password, username: name, role: 'user', balance: 1000, concurrency: 25,
    allowed_groups: [group.id], restrict_public_groups: true });
  const auth = await admin(c, '/auth/login', 'POST', { email, password });
  must(typeof auth.access_token === 'string', 'USER_LOGIN_FAILED');
  owned.user_token = auth.access_token;
  const key = await admin(c, '/keys', 'POST', { name, group_id: group.id, expires_in_days: 1 }, auth.access_token);
  must(typeof key.key === 'string' && Number.isSafeInteger(key.id), 'PRIVATE_KEY_CREATE_FAILED');
  owned.resources.push({ kind: 'keys', id: key.id }); await save(owned.path, owned);
  const [g, a] = await Promise.all([admin(c, `/admin/groups/${group.id}`), admin(c, `/admin/accounts/${account.id}`)]);
  must(g.is_exclusive && !g.fallback_group_id && !g.fallback_group_id_on_invalid_request && a.status === 'active' &&
    (a.group_ids ?? a.groups?.map(x => x.id))?.length === 1 && (a.group_ids ?? a.groups?.map(x => x.id))[0] === group.id, 'DEDICATED_BINDING_NOT_READY');
  row.dedicated_group_id = group.id; row.dedicated_account_id = account.id;
  const id = `${spec.id}.healthy`;
  await control(c, 'rule', { id, mode: 'healthy' });
  const result = await request(c.engine_url, key.key, spec.protocol, id, { timeout: 6000 }).promise;
  const rs = await waitFor(c, id, x => x.length > 0 && x.every(r => r.close_ms !== null));
  row.healthy_control = success(result) && rs.length === 1 && rs[0].effects === 1 && rs[0].identity === spec.protocol && rs[0].finished;
  row.preparation_control = { downstream: result, upstream: rs };
  must(row.healthy_control, 'HEALTHY_CONTROL_FAILED_NO_SCENARIO_ADMISSION');
  return { key: key.key, group: group.id };
}
export async function cleanup(c, owned) {
  let failures = 0;
  for (const r of [...owned.resources].reverse()) {
    try {
      await admin(c, r.kind === 'keys' ? `/keys/${r.id}` : `/admin/${r.kind}/${r.id}`, 'DELETE', undefined,
        r.kind === 'keys' ? owned.user_token : c.admin_bearer);
      owned.resources = owned.resources.filter(x => x !== r); await save(owned.path, owned);
    } catch { failures++; }
  }
  return { failures, ambiguous_intent: owned.intent !== null, remaining_resources: owned.resources.map(({ kind, id }) => ({ kind, id })) };
}
async function broker(c, spec, tenant, row) {
  const oidc = randomBytes(24).toString('hex');
  const server = await createBroker({ ledgerPath: `/private/${c.run_id}.${spec.id}.broker.json`,
    verifyOIDC: async token => { must(token === oidc, 'SYNTHETIC_OIDC_DENIED'); return { runID: spec.id, attempt: '1', workflowSHA: 'a'.repeat(40), expires: Date.now() + 60000 }; },
    resolveWorkspace: async () => 'lab', ttlMs: spec.trigger === 'expiry' ? 3000 : 30000, timeoutMs: 30000,
    scopes: { [`synthetic:${spec.protocol}`]: { model: models[spec.protocol], protocol: spec.protocol, baseURL: c.engine_url,
      workspaces: { lab: { key: tenant.key, groupID: tenant.group } } } } });
  server.prependListener('request', (req, res) => {
    if (req.url === `/v1/${spec.protocol}`) res.once('close', () => { row.broker_boundary_close_ms ??= mono(); });
  });
  try {
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    const base = `http://127.0.0.1:${server.address().port}`;
    const grant = await fetchJSON(`${base}/grant`, 'POST', { provider: 'synthetic', protocol: spec.protocol }, { authorization: `Bearer ${oidc}` }, c.deadline);
    row.broker_evidence = 'actual createBroker module; synthetic verifier; not signed OIDC proof';
    row.capability_expires_wall_ms = grant.expires;
    return { base, key: grant.capability, revoke: () => fetchJSON(`${base}/grant`, 'DELETE', undefined, { authorization: `Bearer ${grant.capability}` }, c.deadline),
      close: () => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }) };
  } catch (e) { server.close(); server.closeAllConnections(); throw e; }
}
async function cancel(c, spec, tenant, row, clients) {
  let b;
  try {
    if (spec.trigger !== 'client') b = await broker(c, spec, tenant, row);
    await control(c, 'rule', { id: spec.id, mode: `hold-${spec.placement}` });
    let ack;
    const pending = request(b?.base ?? c.engine_url, b?.key ?? tenant.key, spec.protocol, spec.id, {
      timeout: 16000, onAck: (ms, size) => { ack = { ms, size }; } }); clients.push(pending);
    let rs = await waitFor(c, spec.id, x => x.length > 0 && x[0].hold_until_ms !== null);
    if (spec.placement === 'after') {
      const end = mono() + 2000; while (!ack && mono() < end) await sleep(20);
      must(ack, 'EARLY_VALID_FRAME_NOT_RECEIVED');
      await control(c, 'ack', { id: spec.id, mono_ms: ack.ms, frame_bytes: ack.size });
    }
    row.action_requested_ms = mono();
    if (spec.trigger === 'client') { pending.cancel(); row.cancel_ms = pending.state.client_cancel_ms; }
    else if (spec.trigger === 'revoke') await b.revoke();
    if (b) {
      const end = mono() + 4500; while (row.broker_boundary_close_ms === undefined && mono() < end) await sleep(20);
      row.cancel_ms = row.broker_boundary_close_ms ?? null;
      must(row.cancel_ms !== null, 'BROKER_CANCEL_BOUNDARY_NOT_OBSERVED');
      const denied = await fetch(`${b.base}/v1/${spec.protocol}`, { method: 'POST', headers: { authorization: `Bearer ${b.key}`, 'content-type': 'application/json' }, body: '{}', signal: AbortSignal.timeout(2000) });
      row.closed_capability_denied = denied.status === 401; await denied.body?.cancel();
    }
    await sleep(Math.max(0, row.cancel_ms + 1250 - mono()));
    row.immediate_observation_ms = mono();
    rs = (await control(c, 'state')).records.filter(r => r.id === spec.id);
    row.upstream_at_immediate_oracle = rs;
    // Hold for ten seconds; only this explicit release permits deliberate usage drain to finish.
    await sleep(Math.max(0, rs[0].hold_until_ms - mono()));
    await control(c, 'release', { id: spec.id });
    row.downstream = await pending.promise;
    row.upstream = await waitFor(c, spec.id, x => x.length > 0 && x.every(r => r.close_ms !== null), 5000);
    Object.assign(row, cancellationVerdict(row, spec.placement));
    row.post_release_control = await request(b?.base ?? c.engine_url, b?.key ?? tenant.key, spec.protocol, `${spec.id}.capacity`, { timeout: 5000 }).promise;
    row.post_release_health_or_revoked_authority = b ? row.closed_capability_denied : success(row.post_release_control);
    if (!row.post_release_health_or_revoked_authority) { row.status = 'FAIL'; row.reason = 'POST_RELEASE_CAPACITY_OR_AUTHORITY_FAILED'; }
  } finally { await b?.close(); }
}
async function uncertain(c, spec, tenant, row, clients) {
  if (spec.mode === 'tool-accepted') {
    const id = `${spec.id}.tool`;
    await control(c, 'rule', { id, mode: 'tool' });
    const d = await request(c.engine_url, tenant.key, spec.protocol, id, { timeout: 6000 }).promise;
    const rs = await waitFor(c, id, x => x.length > 0 && x.every(r => r.close_ms !== null));
    row.tool_turn_verified = success(d) && d.tool_id === (spec.protocol === 'responses' ? CALL : TOOL) && rs.length === 1;
    row.tool_turn = { downstream: d, upstream: rs }; must(row.tool_turn_verified, 'TOOL_TURN_FAILED');
  }
  await control(c, 'rule', { id: spec.id, mode: spec.mode });
  let ack;
  const p = request(c.engine_url, tenant.key, spec.protocol, spec.id, { timeout: 10000, toolResult: spec.mode === 'tool-accepted',
    onAck: (ms, size) => { ack = { ms, size }; } }); clients.push(p);
  await waitFor(c, spec.id, x => x.length > 0 && x[0].hold_until_ms !== null);
  if (spec.mode === 'uncertain-after') {
    const end = mono() + 2500; while (!ack && mono() < end) await sleep(20);
    must(ack, 'COMMITTED_FRAME_NOT_RECEIVED'); await control(c, 'ack', { id: spec.id, mono_ms: ack.ms, frame_bytes: ack.size });
  }
  await control(c, 'reset', { id: spec.id });
  row.downstream = await p.promise;
  await sleep(1200); // cover bounded engine retry observation, not just first socket close
  row.upstream = await waitFor(c, spec.id, x => x.length > 0 && x.every(r => r.close_ms !== null));
  Object.assign(row, uncertaintyVerdict(row, spec.mode));
}
async function telemetry(id) {
  try {
    const text = await readFile(`/telemetry/${id}.ndjson`, 'utf8'); must(text.length <= 2 * MiB, 'TELEMETRY_LIMIT');
    // The collector appends; an incomplete last line is ignored until the next poll.
    return text.slice(0, text.lastIndexOf('\n') + 1).trim().split('\n').filter(Boolean).map(JSON.parse);
  } catch { return []; }
}
async function load(c, spec, tenant, row, clients) {
  row.functional_status = 'NOT RUN';
  const ready = JSON.parse(await readFile(`/telemetry/${spec.id}.ready.json`, 'utf8'));
  must(ready.schema === 'raw-observation-v2' && ready.fresh_container_inspected === true &&
    ready.engine_pid === c.observed.engine_pid && ready.instance === c.observed.instance &&
    ready.container_id === c.observed.container_id, 'FRESH_ENGINE_HANDSHAKE_REQUIRED');
  const identity = Object.fromEntries(['pid_start_ticks', 'cgroup_path', 'cgroup_device', 'cgroup_inode', 'container_id', 'exe_device', 'exe_inode'].map(k => [k, ready[k]]));
  const meta = { id: spec.id, ...c.observed, ...identity, streams: spec.streams,
    telemetry_ready: ready, started_ms: mono(), ended_ms: null };
  await save(`${out}/${spec.id}.start.json`, { ...meta, run_id: c.run_id });
  row.telemetry_boundary = meta;
  let watchdogBusy = false, stopping = false;
  const watchdog = setInterval(async () => {
    if (watchdogBusy || stopping) return; watchdogBusy = true;
    try {
      const v = telemetryVerdict(await telemetry(spec.id), meta, ready, { final: false });
      if (v.status === 'FAIL') { stopping = true; row.safety_stop = v; for (const p of clients) p.cancel(); await control(c, 'stop', { id: spec.id }); }
    } catch { row.safety_stop_control_failed = true; stopping = true; for (const p of clients) p.cancel(); }
    finally { watchdogBusy = false; }
  }, 100);
  const results = [];
  try {
    await control(c, 'rule', { id: spec.id, mode: spec.stage === 'memory' ? 'memory' : 'healthy', mib: spec.mib });
    const count = spec.count ?? spec.streams;
    while (results.length < count && !stopping && mono() < c.deadline - 8500) {
      const n = Math.min(spec.streams, count - results.length);
      const batch = Array.from({ length: n }, () => request(c.engine_url, tenant.key, spec.protocol, spec.id,
        { slow: spec.stage === 'memory', timeout: Math.max(1, Math.min(60000, c.deadline - mono() - 8500)) }));
      clients.push(...batch); results.push(...await Promise.all(batch.map(p => p.promise)));
      if (results.some(r => !success(r))) break;
    }
    row.upstream = await waitFor(c, spec.id, x => x.length > 0 && x.every(r => r.close_ms !== null), 3000);
    const latencies = results.map(r => r.duration_ms).sort((a, b) => a - b);
    row.downstream = { requests: results.length, successful: results.filter(success).length,
      bytes: results.reduce((n, r) => n + r.bytes, 0), p50_ms: latencies[Math.floor((latencies.length - 1) * .5)] ?? null,
      p95_ms: latencies[Math.floor((latencies.length - 1) * .95)] ?? null, max_frame_bytes: Math.max(0, ...results.map(r => r.max_frame_bytes)) };
    const valid = results.length === count && results.every(success) && row.upstream.length === count &&
      row.upstream.every(r => r.effects === 1 && r.finished && r.identity === spec.protocol) &&
      (spec.stage !== 'memory' || results.every(r => r.bytes >= spec.mib * MiB && r.text_delta_bytes > 4096 && r.tool_id !== null && r.comments > 0));
    row.functional_status = valid ? 'PASS' : 'FAIL';
    row.status = valid && !row.safety_stop ? 'PASS' : 'FAIL'; row.reason = valid ? 'FINITE_STREAM_PROTOCOL_AND_EFFECT_GATE' : 'LOAD_LOSS_DUPLICATE_OR_STUCK';
    meta.ended_ms = mono(); await save(`${out}/${spec.id}.end.json`, meta);
    await sleep(5000);
    let done;
    const ackDeadline = Math.min(c.deadline, meta.ended_ms + 5500);
    while (mono() < ackDeadline) {
      try { done = JSON.parse(await readFile(`/telemetry/${spec.id}.done.json`, 'utf8')); break; } catch {}
      await sleep(25);
    }
    row.memory_envelope = telemetryVerdict(await telemetry(spec.id), meta, ready, { done });
    if (row.memory_envelope.status === 'FAIL') row.status = 'FAIL';
    row.acceptance_status = row.status === 'PASS' && row.memory_envelope.status === 'NOT RUN' ? 'NOT RUN' : row.status;
  } finally { clearInterval(watchdog); }
}
async function runOne(config, spec) {
  const c = { ...config, deadline: mono() + 85000 }, started = mono(), clients = [];
  const row = { id: spec.id, run_id: c.run_id, started_ms: started, status: 'NOT RUN', red: spec.red, protocol: spec.protocol, evidence_kind: 'actual-engine/synthetic-upstream',
    deployment: c.observed, node: process.version, live_provider: false, engine_protocol_verified: false };
  const owned = { path: `/private/${c.run_id}.${spec.id}.resources.json`, intent: null, resources: [] };
  let before;
  await save(`/private/${c.run_id}.${spec.id}.journal.json`, { started_ms: started }, true);
  await save(`${out}/${spec.id}.admission.json`, { run_id: c.run_id, started_ms: started }, true);
  const stopTimer = setTimeout(() => { row.safety_deadline_ms = mono(); for (const p of clients) p.cancel(); }, 80000);
  const terminate = () => {
    row.shutdown_requested_ms = mono(); c.deadline = Math.min(c.deadline, mono() + 3000);
    for (const p of clients) p.cancel(); control(c, 'stop', { id: spec.id }).catch(() => {});
  };
  process.once('SIGTERM', terminate);
  try {
    before = await control(c, 'state'); must(!before.exceeded && before.total + (spec.count ?? spec.streams ?? 1) + 20 < 2000, 'GLOBAL_UPSTREAM_BUDGET');
    const tenant = await setup(c, spec, row, owned);
    if (spec.stage === 'cancel') await cancel(c, spec, tenant, row, clients);
    else if (spec.stage === 'uncertainty') await uncertain(c, spec, tenant, row, clients);
    else await load(c, spec, tenant, row, clients);
    row.engine_protocol_verified = true;
  } catch (e) { row.status = row.healthy_control ? 'FAIL' : 'NOT RUN'; row.reason = e.labCode ?? 'LAB_SETUP_OR_TRANSPORT_FAILURE'; }
  finally {
    clearTimeout(stopTimer); process.off('SIGTERM', terminate); for (const p of clients) p.cancel();
    await control(c, 'stop', { id: spec.id }).catch(() => { row.stop_control_failed = true; });
    const after = await control(c, 'state').catch(() => null);
    if (after && before) {
      const actual = after.records.filter(r => r.sequence > before.total);
      row.upstream_attempts_total = after.total - before.total; row.upstream_effects_total = after.effects - before.effects;
      row.preparation_requests = actual.filter(r => r.id === 'preparation' || r.id.endsWith('.healthy')).length;
      row.preparation_effects = actual.filter(r => r.id === 'preparation' || r.id.endsWith('.healthy')).reduce((n, r) => n + r.effects, 0);
      row.auxiliary_requests = actual.filter(r => r.id.endsWith('.tool') || r.id.endsWith('.capacity')).length;
      row.active_at_boundary = actual.filter(r => r.close_ms === null).length;
      row.unknown_identity = actual.some(r => r.identity === 'UNKNOWN');
      row.upstream = actual.filter(r => r.id === spec.id);
      if (row.engine_protocol_verified) {
        const previousFailure = row.status === 'FAIL' ? { status: row.status, reason: row.reason } : null;
        if (spec.stage === 'cancel') Object.assign(row, cancellationVerdict(row, spec.placement));
        if (spec.stage === 'uncertainty') Object.assign(row, uncertaintyVerdict(row, spec.mode));
        if (previousFailure && row.status === 'PASS') Object.assign(row, previousFailure);
        if (row.upstream.length !== (spec.count ?? spec.streams ?? 1) || row.active_at_boundary > 0) {
          row.status = 'FAIL'; row.reason = 'FINAL_EFFECT_RECHECK_DUPLICATE_OR_UNQUIESCENT';
        }
      }
      if (row.unknown_identity || after.exceeded) { row.status = 'FAIL'; row.reason = 'CUSTODY_IDENTITY_OR_BUDGET_STOP'; }
    }
    row.cleanup = await cleanup(c, owned);
    if (row.cleanup.failures || row.cleanup.ambiguous_intent) { row.cleanup_status = 'FAIL'; row.acceptance_status = 'FAIL'; }
    row.duration_ms = mono() - started;
    if (row.duration_ms > 90000 || row.safety_deadline_ms || row.shutdown_requested_ms) { row.status = 'FAIL'; row.reason = 'BATCH_TIME_BOUND_OR_SHUTDOWN'; }
    if (row.status === 'FAIL') row.acceptance_status = 'FAIL';
    await save(`${out}/${spec.id}.json`, row, true);
  }
  return row;
}
async function main() {
  if (process.argv.includes('--plan')) { process.stdout.write(JSON.stringify({ cases, budget }, null, 2) + '\n'); return; }
  const id = process.argv[process.argv.indexOf('--case') + 1], spec = cases.find(s => s.id === id);
  must(process.argv.includes('--case') && spec, 'EXPLICIT_SINGLE_BATCH_REQUIRED');
  await mkdir(out, { recursive: true, mode: 0o700 });
  const c = await loadConfig();
  const row = await runOne(c, spec);
  process.stdout.write(`${row.id} ${row.acceptance_status ?? row.status}\n`);
  if (row.status === 'FAIL' || row.acceptance_status === 'NOT RUN' || row.status === 'NOT RUN' || row.cleanup_status === 'FAIL') process.exitCode = 1;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch(() => { process.stderr.write('LAB_COMMAND_FAILED_DETAILS_WITHHELD\n'); process.exitCode = 1; });
