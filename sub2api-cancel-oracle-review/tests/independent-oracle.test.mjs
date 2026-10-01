import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const own = resolve(import.meta.dirname), canonical = resolve(own, '../.spike-inputs/original-inputs/canonical');
const source = resolve(process.env.CANCEL_CODE ?? `${own}/.verification/new`);
let code = await readFile(`${source}/sub2api-regression-lab/receipts.mjs`, 'utf8');
for (const name of ['common', 'client']) code = code.replace(`'./${name}.mjs'`, JSON.stringify(pathToFileURL(`${canonical}/sub2api-regression-lab/${name}.mjs`).href));
const { cancellationVerdict: verdict } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const fixtureDir = resolve(own, '../.spike-inputs/original-inputs/actual-faults');
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

for(const protocol of ['responses','messages'])for(const cause of ['membership','workspace-revoke','server-close','timeout','downstream-close','request-finally'])test(`${protocol}: ${cause} cannot substitute revoke causality`,()=>{
  const row=trace(protocol);row.broker_abort_events[0].cause=cause;assert.equal(verdict(row,'after').status,'FAIL');
});
for(const protocol of ['responses','messages'])test(`${protocol}: immediate duplicate effect cannot be erased in final receipt`,()=>{
  const row=trace(protocol);row.upstream_at_immediate_oracle[0].effects=2;assert.equal(verdict(row,'after').status,'FAIL');
});
