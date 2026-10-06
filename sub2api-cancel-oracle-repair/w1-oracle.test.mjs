import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const own = resolve(import.meta.dirname), canonical = resolve(own, '../.spike-inputs/canonical');
const source = resolve(process.env.CANCEL_CODE ?? `${own}/.verification/new`);
let code = await readFile(`${source}/sub2api-regression-lab/receipts.mjs`, 'utf8');
for (const name of ['common', 'client']) code = code.replace(`'./${name}.mjs'`, JSON.stringify(pathToFileURL(`${canonical}/sub2api-regression-lab/${name}.mjs`).href));
const { cancellationVerdict: verdict } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const fixtureDir = resolve(own, '../.spike-inputs/actual-faults');
const fixtures = await Promise.all((await readdir(fixtureDir)).sort().map(async name => JSON.parse(await readFile(`${fixtureDir}/${name}`, 'utf8'))));

// An explicit synthetic trace with observed action -> abort -> physical incomplete close -> response close.
// Numeric event times are test data, never added to historical receipts.
function trace(protocol = 'responses', placement = 'after', trigger = 'revoke', cause = trigger) {
  const healthy = structuredClone(fixtures.find(r => r.protocol === protocol).preparation_control);
  const id = `cancel-${protocol}-${placement}-${trigger}`;
  healthy.upstream[0].id = `${id}.healthy`;
  const r = { id, sequence: 2, identity: protocol, protocol, mode: `hold-${placement}`, started_ms: 800, effect_ms: 801,
    effects: 1, first_write_ms: placement === 'after' ? 810 : null, first_flush_ms: placement === 'after' ? 811 : null,
    client_ack_ms: placement === 'after' ? 820 : null, ack_received_ms: placement === 'after' ? 830 : null,
    ack_frame_bytes: placement === 'after' ? 9415 : 0, close_ms: 1004, finished: false,
    terminal_ms: null, release_ms: null, reset_ms: null, hold_started_ms: 812, hold_until_ms: 10812,
    bytes: placement === 'after' ? 9775 : 0 };
  return { id, protocol, started_ms: 700, healthy_control: true, preparation_control: healthy,
    deployment: { clock: 'linux-CLOCK_MONOTONIC' }, cancel_clock: 'linux-CLOCK_MONOTONIC',
    cancel_trigger: trigger, action_requested_ms: 1000, cancel_ms: trigger === 'expiry' ? 1002 : 1000,
    broker_boundary_close_ms: 1005, closed_capability_denied: true,
    broker_abort_events: trigger === 'client' ? [] : [{ id, protocol, dispatch: 1, cause, mono_ms: 1002, clock: 'linux-CLOCK_MONOTONIC' }],
    downstream: { started_ms: 750, http_status: placement === 'before' ? 502 : 200,
      transport: trigger === 'client' ? 'client_cancel' : placement === 'before' ? null : 'aborted',
      client_cancel_ms: trigger === 'client' ? 1000 : null, client_close_ms: 1006,
      ack_ms: r.client_ack_ms, ack_frame_bytes: r.ack_frame_bytes, terminal_ms: null, failed: false, malformed: false },
    upstream: [r], upstream_at_immediate_oracle: [structuredClone(r)], immediate_observation_ms: 2253 };
}
function closeAt(row, time) { row.upstream[0].close_ms = time; row.upstream_at_immediate_oracle[0].close_ms = time; return row; }
for (const protocol of ['responses', 'messages']) {
  for (const placement of ['before', 'after']) {
    for (const trigger of ['client', 'revoke', 'expiry']) test(`${protocol} ${placement} ${trigger}: rapid physical close is valid`, () => {
      const row = trace(protocol, placement, trigger);
      assert.equal(verdict(row, placement).status, 'PASS');
    });
  }
  for (const cause of ['expiry', 'request-expiry']) test(`${protocol}: ${cause} callback anchors expiry, not setup`, () => {
    const row = trace(protocol, 'after', 'expiry', cause);
    row.action_requested_ms = 840; row.cancel_ms = 4000;
    row.broker_abort_events[0].mono_ms = 4000; row.broker_boundary_close_ms = 4005;
    row.downstream.client_close_ms = 4006; row.immediate_observation_ms = 5251; closeAt(row,4004);
    assert.equal(verdict(row, 'after').status, 'PASS');
    row.cancel_ms = row.action_requested_ms;
    assert.equal(verdict(row, 'after').status, 'FAIL');
  });
}
for (const ms of [1201, 1249.9, 1250]) test(`physical close at ${ms}ms meets the unchanged 1250ms deadline`, () => {
  const row = closeAt(trace(), 1000+ms); row.broker_boundary_close_ms = 2260; row.downstream.client_close_ms = 2261;
  assert.equal(verdict(row, 'after').status, 'PASS');
});
const negatives = {
  'close before abort despite being after request': row => closeAt(row,1001),
  'close before action request': row => closeAt(row,999),
  'close before upstream request': row => closeAt(row,799),
  'close after 1250ms deadline': row => closeAt(row,2250.01),
  'late broker response cannot extend deadline': row => { closeAt(row,2300); row.broker_boundary_close_ms=2400; row.downstream.client_close_ms=2401; },
  'upstream semantic terminal': row => { row.upstream[0].terminal_ms = 1003; },
  'downstream terminal even with transport error': row => { row.downstream.terminal_ms = 1003; },
  'normal complete upstream close': row => { row.upstream[0].finished = true; },
  'manual upstream release': row => { row.upstream[0].release_ms = 1003; },
  'manual upstream reset': row => { row.upstream[0].reset_ms = 1003; },
  'upstream safety reset': row => { row.upstream[0].safety_stop_ms = 1003; },
  'missing physical close': row => { row.upstream[0].close_ms = null; },
  'missing pre-abort event': row => { delete row.broker_abort_events; },
  'foreign pre-abort protocol': row => { row.broker_abort_events[0].protocol = 'messages'; },
  'foreign pre-abort request': row => { row.broker_abort_events[0].id += '.foreign'; },
  'foreign source clock': row => { row.broker_abort_events[0].clock = 'wall'; },
  'missing clock custody': row => { delete row.deployment.clock; },
  'foreign physical protocol': row => { row.upstream[0].protocol = 'messages'; },
  'foreign physical identity': row => { row.upstream[0].identity = 'UNKNOWN'; },
  'foreign physical request': row => { row.upstream[0].id += '.other'; },
  'double upstream dispatch': row => { row.upstream.push(structuredClone(row.upstream[0])); },
  'double broker dispatch': row => { row.broker_abort_events.push({ ...row.broker_abort_events[0], dispatch: 2 }); },
  'second broker dispatch substituted': row => { row.broker_abort_events[0].dispatch = 2; },
  'multiple effects': row => { row.upstream[0].effects = 2; },
  'missing immediate snapshot': row => { delete row.upstream_at_immediate_oracle; },
  'late close only in final snapshot': row => { row.upstream_at_immediate_oracle[0].close_ms = null; },
  'foreign immediate sequence': row => { row.upstream_at_immediate_oracle[0].sequence = 99; },
  'immediate terminal later erased': row => { row.upstream_at_immediate_oracle[0].terminal_ms = 1003; },
  'shortened hold': row => { row.upstream[0].hold_until_ms = 2000; },
  'oracle observation too early': row => { row.immediate_observation_ms = 2249; },
  'oracle observation after hold': row => { row.immediate_observation_ms = 10812; },
  'healthy boolean without physical control': row => { delete row.preparation_control; },
  'missing healthy downstream': row => { delete row.preparation_control.downstream; },
  'missing healthy ack size': row => { delete row.preparation_control.downstream.ack_frame_bytes; },
  'null upstream record': row => { row.upstream[0] = null; },
  'null broker event': row => { row.broker_abort_events[0] = null; },
  'missing healthy acknowledgment': row => { delete row.preparation_control.downstream.ack_ms; },
  'foreign healthy request': row => { row.preparation_control.upstream[0].id += '.other'; },
  'missing healthy physical close': row => { row.preparation_control.upstream[0].close_ms = null; },
  'tiny acknowledged healthy frame': row => { row.preparation_control.downstream.ack_frame_bytes = 4096; },
  'tiny acknowledged early frame': row => { row.downstream.ack_frame_bytes = 4096; },
  'ack before upstream flush': row => { row.downstream.ack_ms = 810; },
  'ack at cancellation': row => { row.upstream[0].ack_received_ms = 1000; },
  'before placement already wrote output': row => { row.upstream[0].first_write_ms = 810; },
  'request timeout pretending expiry': row => { row.cancel_trigger = 'expiry'; row.cancel_ms = 1002; row.broker_abort_events[0].cause = 'timeout'; },
  'finally abort pretending revoke': row => { row.broker_abort_events[0].cause = 'request-finally'; },
  'client completion pretending cancellation': row => { row.cancel_trigger = 'client'; row.broker_abort_events = []; row.downstream.client_cancel_ms = null; },
};
for (const [name, mutate] of Object.entries(negatives)) test(`reject ${name}`, () => {
  const placement = name.startsWith('before placement') ? 'before' : 'after';
  const row = trace('responses', placement); mutate(row);
  assert.equal(verdict(row,placement).status, 'FAIL');
});
for (const row of fixtures) test(`historical ${row.id}: absent pre-abort evidence cannot become green`, () => {
  assert.equal(row.broker_abort_events, undefined);
  assert.notEqual(verdict(row,row.id.includes('-before-') ? 'before' : 'after').status, 'PASS');
});
test('missing upstream exercise stays NOT RUN', () => {
  const row=trace(); row.upstream=[];
  assert.equal(verdict(row,'after').status,'NOT RUN');
});
