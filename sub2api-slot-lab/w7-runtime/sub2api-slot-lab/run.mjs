import { readFile, mkdir } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { request, success } from '../sub2api-regression-lab/client.mjs';
import { admin, control, save } from '../sub2api-regression-lab/common.mjs';
import { setup, cleanup } from './adapter.mjs';
import { RedisObserver } from './redis.mjs';
import { mono, sleep, plan, counts, finalZero, retainsFirst, recordSet, cancelEvidence, pollUntil, requireFact } from './contracts.mjs';

async function cycle(c, spec, redis) {
  const row = { ...spec, status: 'FAIL', evidence_kind: 'actual-native-handler/private-real-Redis/synthetic-provider',
    started_ms: mono(), phases: {}, ids: null, requests: {}, live_provider: false };
  const journal = { path: `/private/${spec.id}.journal.json`, resources: [], intent: null };
  const clients = [], ids = [`${spec.id}.first`, `${spec.id}.pending`, `${spec.id}.third`];
  c.deadline = Math.min(c.supervisor_deadline, mono() + 35000);
  await save(journal.path, journal, true);
  let tenant, baseline;
  const examine = async (phase, deadline, expected) => {
    const d = { ...c, deadline };
    const [snapshot, state] = await Promise.all([redis.snapshot(tenant.ids, deadline), control(d, 'state')]);
    const observed_ms = mono();
    (row.phases[phase] ??= []).push({ snapshot, observed_ms, records: state.records.filter(r => ids.includes(r.id)), total: state.total });
    requireFact(state.total - baseline.total === expected && state.effects - baseline.effects === expected,
      'UNEXPECTED_OR_PENDING_UPSTREAM_DISPATCH');
    const records = recordSet(state, ids, expected);
    requireFact(records.every(r => r.protocol === spec.protocol && r.identity === spec.protocol), 'NATIVE_PROTOCOL_CHANGED');
    requireFact(!records.some(r => r.id === ids[1]), 'PENDING_DISPATCHED');
    return { snapshot, records, observed_ms };
  };
  const wait = async (phase, expected, predicate, deadline = Math.min(c.deadline, mono() + 5000)) => {
    try { return await pollUntil(d => examine(phase, d, expected), predicate, deadline); }
    catch (e) {
      if (phase === 'queued' && e.code === 'OBSERVATION_DEADLINE') e.code = 'REQUIRED_HANDLER_QUEUE_NOT_ENTERED';
      throw e;
    }
  };
  const launch = id => {
    const p = request(c.engine_url, tenant.key, spec.protocol, id, { timeout: Math.min(30000, c.deadline - mono()),
      onAck: (ms, size) => { row.requests[id] = { ack_ms: ms, frame_bytes: size }; } });
    clients.push(p); return p;
  };
  try {
    baseline = await control(c, 'state');
    tenant = await setup(c, spec, journal); row.ids = tenant.ids; row.group_id = tenant.group;
    const initial = await redis.snapshot(tenant.ids, c.deadline);
    row.initial = initial; requireFact(counts(initial, 0, 0), 'NONEMPTY_OWNED_START');
    for (const [id, mode] of [[ids[0], 'hold-after'], [ids[1], 'pending'], [ids[2], 'healthy']])
      await control(c, 'rule', { id, mode });
    const first = launch(ids[0]);
    // Dispatch admission may not yet exist: poll with explicit 0-or-1 admission,
    // then require exact one thereafter. No preparatory provider requests.
    const accepted = await pollUntil(async deadline => {
      const state = await control({ ...c, deadline }, 'state');
      requireFact(state.exceeded === false && state.total - baseline.total <= 1, 'ACCEPTED_BUDGET');
      return state.records.filter(r => r.id === ids[0]);
    }, rs => rs.length === 1 && rs[0].first_flush_ms !== null && rs[0].hold_until_ms !== null &&
      row.requests[ids[0]]?.ack_ms != null, Math.min(c.deadline, mono() + 5000));
    row.accepted_wire_barrier = accepted[0];
    const active = await wait('active', 1, x => counts(x.snapshot, 1, 1) && x.records[0].close_ms === null);
    if (spec.optin) {
      const pending = launch(ids[1]);
      const queued = await wait('queued', 1, x => {
        requireFact(x.records[0].close_ms === null && retainsFirst(active.snapshot, x.snapshot), 'FIRST_LEASE_LOST_DURING_PENDING');
        return spec.lane === 'account' ? counts(x.snapshot, 2, 1, 0, 1) : counts(x.snapshot, 1, 1, 1, 0);
      });
      row.queue_entered = queued.snapshot;
      pending.cancel(); row.pending_cancel_ms = pending.state.client_cancel_ms;
      const pendingEnd = await wait('pending_cancel', 1, x => {
        requireFact(x.records[0].close_ms === null && retainsFirst(active.snapshot, x.snapshot), 'FIRST_LOST_ON_PENDING_CANCEL');
        return counts(x.snapshot, 1, 1) && ['user', 'account', 'key'].every(k =>
          x.snapshot[k].members[0] === active.snapshot[k].members[0]);
      }, Math.min(c.deadline, row.pending_cancel_ms + 1250));
      row.pending_cancel_observed_ms = mono();
      requireFact(row.pending_cancel_observed_ms - row.pending_cancel_ms <= 1250, 'PENDING_CANCEL_OBSERVATION_OVER_BUDGET');
      row.pending_downstream = await pending.promise;
      requireFact(pending.state.transport === 'client_cancel', 'PENDING_CLIENT_NOT_CANCELED');
      first.cancel(); row.active_cancel_ms = first.state.client_cancel_ms;
      const canceled = await wait('active_cancel', 1, x => counts(x.snapshot, 0, 0) && x.records[0].close_ms !== null && x.records[0].socket_close_ms !== null,
        Math.min(c.deadline, row.active_cancel_ms + 1250));
      row.active_cancel_observed_ms = mono();
      cancelEvidence(canceled.records[0], canceled.snapshot, row.active_cancel_ms, row.active_cancel_observed_ms);
    } else {
      first.cancel(); row.active_cancel_ms = first.state.client_cancel_ms;
      // Observed default drain throughout the interval. Poll after its end too;
      // do not label a short single sample as the complete default control.
      const until = row.active_cancel_ms + 1250;
      do {
        const x = await examine('default_drain', c.deadline, 1), r = x.records[0];
        requireFact(r.close_ms === null && r.terminal_ms === null && r.release_ms === null && r.reset_ms === null &&
          r.safety_stop_ms == null && r.effects === 1, 'DEFAULT_DRAIN_CHANGED');
        if (x.observed_ms >= until) break;
        await sleep(Math.min(25, until - mono()));
      } while (mono() < c.deadline);
      requireFact(row.phases.default_drain.at(-1).observed_ms >= until, 'DEFAULT_OBSERVATION_INCOMPLETE');
      await control(c, 'release', { id: ids[0] });
      await wait('default_released', 1, x => counts(x.snapshot, 0, 0) && x.records[0].finished && x.records[0].terminal_ms !== null);
    }
    row.first_downstream = await first.promise;
    const third = launch(ids[2]); row.third_downstream = await third.promise;
    requireFact(success(row.third_downstream) && row.third_downstream.native_valid === true && row.third_downstream.native_usage != null, 'RECOVERY_NATIVE_SSE_FAILED');
    const final = await wait('recovery', 2, x => counts(x.snapshot, 0, 0) && x.records.every(r => r.close_ms !== null) &&
      x.records.find(r => r.id === ids[2])?.finished && x.records.find(r => r.id === ids[2])?.terminal_ms !== null);
    const thirdRecord = final.records.find(r => r.id === ids[2]);
    requireFact(thirdRecord.effects === 1 && thirdRecord.protocol === spec.protocol && thirdRecord.identity === spec.protocol,
      'RECOVERY_EFFECT_OR_PROTOCOL');
    // Bounded late-orphan window with actual Redis and provider observations.
    const quietUntil = mono() + 1250;
    do {
      const x = await examine('quiet', c.deadline, 2);
      requireFact(counts(x.snapshot, 0, 0) && x.records.every(r => r.close_ms !== null), 'LATE_ORPHAN');
      if (x.observed_ms >= quietUntil) break;
      await sleep(Math.min(50, quietUntil - mono()));
    } while (mono() < c.deadline);
    requireFact(row.phases.quiet.at(-1).observed_ms >= quietUntil, 'QUIET_WINDOW_INCOMPLETE');
    row.status = 'PASS';
  } catch (e) { row.reason = e.code ?? e.labCode ?? 'FIXTURE_OR_NATIVE_TRANSPORT_FAILURE'; }
  finally {
    for (const p of clients) p.cancel();
    // Capture real failure state before forced fixture teardown; cleanup never
    // supplies cancellation success evidence or deletes lease/wait keys.
    if (tenant) {
      row.before_cleanup = await redis.snapshot(tenant.ids, mono() + 1000).catch(() => null);
      row.mock_before_cleanup = await control({ ...c, deadline: mono() + 1000 }, 'state').then(s => ({
        total: s.total, effects: s.effects, exceeded: s.exceeded, records: s.records.filter(r => ids.includes(r.id)), rejections: s.rejections
      })).catch(() => null);
      if (row.status === 'PASS' && (!finalZero(row.before_cleanup) ||
        !row.mock_before_cleanup || row.mock_before_cleanup.total - baseline.total !== 2 || row.mock_before_cleanup.exceeded)) {
        row.status = 'FAIL'; row.reason = 'FINAL_OWNERSHIP_RECHECK';
      }
    }
    for (const id of ids) await control({ ...c, deadline: mono() + 1000 }, 'stop', { id }).catch(() => {});
    row.cleanup = await cleanup({ ...c, deadline: mono() + 6000 }, journal);
    if (row.cleanup.failures || row.cleanup.ambiguous_intent || row.cleanup.remaining.length) { row.status = 'FAIL'; row.reason ??= 'CLEANUP_INCOMPLETE'; }
    row.duration_ms = mono() - row.started_ms;
    await save(`/evidence/${spec.id}.json`, row, true);
  }
  return row;
}

export async function main() {
  if (process.argv.includes('--plan')) {
    process.stdout.write(JSON.stringify({ cases: plan(), optin_cycles: 80, default_controls: 4,
      maximum_accepted: 168, maximum_gateway_requests: 248, cancellation_bound_ms: 1250 }) + '\n'); return;
  }
  requireFact(process.getuid() === 0 && /^v24\./.test(process.version), 'ROOT_NODE24_ONLY');
  const c = JSON.parse(await readFile('/private/lab.json', 'utf8'));
  const supervisor = JSON.parse(await readFile('/private/supervisor.json', 'utf8'));
  requireFact(c.engine_url === 'http://sub2api:8080' && c.mock_url === 'https://mock:8099' && supervisor.deadline_ms > mono(), 'PRIVATE_TOPOLOGY_OR_DEADLINE');
  c.supervisor_deadline = supervisor.deadline_ms; c.deadline = Math.min(supervisor.deadline_ms, mono() + 30000);
  await mkdir('/evidence', { recursive: true, mode: 0o700 });
  await pollUntil(async deadline => {
    try { await admin({ ...c, deadline }, '/admin/users'); return true; } catch { return false; }
  }, x => x, c.deadline, { interval: 250 });
  const redis = new RedisObserver(c.redis_password), specs = plan(c.run_id), rows = [];
  const allIDs = { user: new Set(), account: new Set(), key: new Set() };
  for (const spec of specs) {
    requireFact(mono() + 35000 < c.supervisor_deadline, 'SUPERVISOR_DEADLINE');
    const row = await cycle(c, spec, redis); rows.push({ id: row.id, status: row.status, reason: row.reason });
    if (row.ids) for (const k of Object.keys(allIDs)) {
      requireFact(!allIDs[k].has(row.ids[k]), 'OWNED_ID_REUSED'); allIDs[k].add(row.ids[k]);
    }
    await save('/evidence/result.json', { status: rows.some(x => x.status === 'FAIL') ? 'FAIL' : 'INCOMPLETE',
      required: 84, executed: rows.length, rows, source: c.deployment, live_provider: false });
    if (row.status !== 'PASS') { process.exitCode = 1; return; }
  }
  // Recheck every formerly owned numeric ID after all cycles; read-only exact keys.
  const final_snapshots = [];
  for (const s of specs) {
    const r = JSON.parse(await readFile(`/evidence/${s.id}.json`, 'utf8'));
    const snapshot = await redis.snapshot(r.ids, Math.min(c.supervisor_deadline, mono() + 1000));
    requireFact(counts(snapshot, 0, 0), 'FINAL_ALL_IDS_ORPHAN'); final_snapshots.push({ id: s.id, ids: r.ids, snapshot });
  }
  await save('/evidence/final-zero.json', { status: 'PASS', ids: Object.fromEntries(Object.entries(allIDs).map(([k, v]) => [k, [...v]])),
    total_owned_keys_checked: 84 * 5, snapshots: final_snapshots });
  const final_state = await control({ ...c, deadline: Math.min(c.supervisor_deadline, mono() + 2000) }, 'state');
  requireFact(final_state.total === 168 && final_state.effects === 168 && final_state.active === 0 && final_state.exceeded === false &&
    final_state.rejections.length === 0 && final_state.records.length === 168, 'FINAL_GLOBAL_EFFECT_RECHECK');
  await save('/evidence/final-provider.json', final_state);
  await save('/evidence/result.json', { status: 'PASS', required: 84, executed: 84, rows, source: c.deployment, live_provider: false });
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().catch(() => { process.stderr.write('SLOT_LAB_FAILED_DETAILS_WITHHELD\n'); process.exitCode = 1; });
