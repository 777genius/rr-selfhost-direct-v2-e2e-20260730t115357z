// Pure assertions. Only the runner supplies observed Redis/wire evidence.
export const mono = () => Number(process.hrtime.bigint()) / 1e6;
export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
export function requireFact(ok, code) { if (!ok) throw Object.assign(Error(code), { code }); }
export function plan(run = 'slot') {
  requireFact(/^[a-z0-9-]{1,36}$/.test(run), 'RUN_ID');
  return ['responses', 'messages'].flatMap(protocol => ['account', 'user'].flatMap(lane => [
    ...Array.from({ length: 20 }, (_, i) => ({ id: `${run}.${protocol}.${lane}.${i + 1}`, protocol, lane, optin: true })),
    { id: `${run}.${protocol}.${lane}.default`, protocol, lane, optin: false }
  ]));
}
export const limits = lane => lane === 'account' ? { user: 2, account: 1 } : { user: 1, account: 2 };
export function ownedKeys(ids) {
  requireFact(['user', 'account', 'key'].every(k => Number.isSafeInteger(ids[k]) && ids[k] > 0), 'OWNED_NUMERIC_IDS');
  return { user: `concurrency:user:${ids.user}`, account: `concurrency:account:${ids.account}`,
    key: `concurrency:api_key:${ids.key}`, userWait: `concurrency:wait:${ids.user}`, accountWait: `wait:account:${ids.account}` };
}
export function snapshotShape(s) {
  requireFact(Number.isFinite(s.started_ms) && s.observed_ms >= s.started_ms, 'SNAPSHOT_TIME');
  for (const k of ['user', 'account', 'key']) {
    const x = s[k];
    requireFact(x && Number.isSafeInteger(x.count) && x.count >= 0 && x.count <= 1024 &&
      Array.isArray(x.members) && x.members.length === x.count && new Set(x.members).size === x.count &&
      x.members.every(v => typeof v === 'string' && v.length > 0 && v.length <= 256), 'REDIS_SLOT_SHAPE');
    requireFact(Number.isSafeInteger(x.ttl_ms) && x.ttl_ms >= -2, 'REDIS_TTL_SHAPE');
  }
  for (const k of ['userWait', 'accountWait']) {
    requireFact(Number.isSafeInteger(s[k].count) && s[k].count >= 0, 'REDIS_WAIT_SHAPE');
    requireFact(Number.isSafeInteger(s[k].ttl_ms) && s[k].ttl_ms >= -2, 'REDIS_TTL_SHAPE');
  }
  return s;
}
export function validSnapshot(s) {
  snapshotShape(s);
  for (const k of ['user', 'account', 'key'])
    requireFact(s[k].count === 0 || s[k].ttl_ms > 5000, 'LEASE_EXPIRY_TOO_NEAR');
  for (const k of ['userWait', 'accountWait'])
    requireFact(s[k].count === 0 || s[k].ttl_ms > 5000, 'WAITER_EXPIRY_TOO_NEAR');
  return s;
}
export function counts(s, user, account, userWait = 0, accountWait = 0) {
  validSnapshot(s);
  return s.user.count === user && s.account.count === account && s.key.count === user &&
    s.userWait.count === userWait && s.accountWait.count === accountWait;
}
// Failure-state validation must never prevent the finally block from writing
// its row and completing owned resource cleanup.
export function finalZero(s) {
  try { return counts(s, 0, 0); } catch { return false; }
}
export function retainsFirst(first, next) {
  return ['user', 'account', 'key'].every(k => first[k].members.every(v => next[k].members.includes(v)));
}
export function recordSet(state, ids, expected) {
  requireFact(state && state.exceeded === false && Number.isSafeInteger(state.total), 'MOCK_BUDGET_OR_STATE');
  const records = state.records.filter(r => ids.includes(r.id));
  requireFact(records.length === expected && records.every(r => r.effects === 1 && r.identity === r.protocol &&
    r.safety_stop_ms == null && r.reset_ms === null), 'DISPATCH_EFFECT_OR_FORCED_CLOSE');
  requireFact(ids.every(id => records.filter(r => r.id === id).length <= 1), 'DUPLICATE_DISPATCH');
  return records;
}
export function cancelEvidence(record, snapshot, cancel_ms, observation_ms) {
  requireFact(Number.isFinite(cancel_ms) && Number.isFinite(observation_ms) && observation_ms >= snapshot.observed_ms &&
    observation_ms >= cancel_ms && observation_ms - cancel_ms <= 1250,
    'CANCEL_OBSERVATION_OVER_BUDGET');
  requireFact(record && Number.isFinite(record.first_flush_ms) && record.first_flush_ms <= cancel_ms &&
    Number.isFinite(record.hold_until_ms) && record.hold_until_ms <= cancel_ms &&
    Number.isFinite(record.close_ms) && record.close_ms >= cancel_ms && record.close_ms <= observation_ms && record.close_ms - cancel_ms <= 1250 &&
    Number.isFinite(record.socket_close_ms) && record.socket_close_ms >= cancel_ms && record.socket_close_ms <= observation_ms && record.socket_close_ms - cancel_ms <= 1250 &&
    record.finished === false && record.release_ms === null && record.reset_ms === null && record.safety_stop_ms == null &&
    record.terminal_ms === null && record.effects === 1, 'UPSTREAM_BODY_NOT_CLOSED_BY_CANCELLATION');
  requireFact(counts(snapshot, 0, 0), 'CANCELED_LEASE_OR_WAITER_LEAK');
}
export async function pollUntil(observe, predicate, deadline, { now = mono, pause = sleep, interval = 20 } = {}) {
  // The deadline covers command round trips, body reads, assertions and pauses.
  while (now() < deadline) {
    const observation = await observe(deadline);
    if (now() > deadline) break;
    const satisfied = predicate(observation);
    if (now() > deadline) break;
    if (satisfied) return observation;
    await pause(Math.min(interval, Math.max(0, deadline - now())));
  }
  throw Object.assign(Error('OBSERVATION_DEADLINE'), { code: 'OBSERVATION_DEADLINE' });
}
