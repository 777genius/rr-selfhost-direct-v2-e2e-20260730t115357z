import test from 'node:test';
import assert from 'node:assert/strict';
import { telemetryVerdict as proposed } from './adapter-proposal.mjs';
import { telemetryVerdict as stock } from '../sub2api-regression-lab/receipts.mjs';
const MiB = 1048576;
// Fabricated unit-test input only; never actual-engine receipts.
function fixture() {
  const identity = { instance: 'unit-test-only', engine_pid: 42, pid_start_ticks: 10,
    cgroup_path: '/unit-test-only', cgroup_device: 1, cgroup_inode: 2, container_id: 'a'.repeat(64) };
  const ready = { ...identity, schema: 'fresh-lifetime-v1', fresh_container_inspected: true,
    container_created_ms: 800, pid_created_ms: 900, first_ready_ms: 1000 };
  const meta = { ...identity, id: 'memory-responses-8-1', streams: 1, started_ms: 1100, ended_ms: 1300 };
  const samples = [1000, 1200, 1400].map((mono_ms, i) => ({ ...identity, schema: ready.schema,
    collector: 'root-go-pid', batch_id: meta.id, clock: 'linux-CLOCK_MONOTONIC', mono_ms,
    phase: ['baseline', 'active', 'quiescent'][i], rss_bytes: 100 * MiB, rss_lifetime_peak_bytes: 120 * MiB,
    cgroup_current_bytes: 110 * MiB, cgroup_peak_bytes: 130 * MiB, cgroup_limit_bytes: 768 * MiB,
    sockets: 2, goroutines: null }));
  return { ready, meta, samples };
}
test('before fix: truthful kernel6.8 lifetime evidence is NOT RUN; proposed schema accepts without fake reset/count', () => {
  const { ready, meta, samples } = fixture();
  assert.equal(stock(samples, meta).status, 'NOT RUN');
  const v = proposed(samples, meta, ready);
  assert.equal(v.status, 'PASS');
  assert.equal(v.interval_max_rss_bytes, 100 * MiB);
  assert.equal(v.batch_peak_rss_upper_bound_bytes, 120 * MiB);
  assert.equal(v.instantaneous_goroutines, null);
});
test('before fix: interval-only oracle misses intersample RSS peak; retained lifetime VmHWM defeats false green', () => {
  const { ready, meta, samples } = fixture();
  samples.forEach(s => { s.rss_lifetime_peak_bytes = 530 * MiB; s.cgroup_peak_bytes = 550 * MiB; });
  const legacy = samples.map(s => ({ ...s, goroutines: 20, peak_reset_ms: 1000 }));
  assert.equal(stock(legacy, meta).status, 'PASS');
  assert.equal(proposed(samples, meta, ready).status, 'FAIL');
});
test('retained startup HWM never subtracted away; per-stream delta bound unchanged', () => {
  const { ready, meta, samples } = fixture();
  samples.forEach(s => { s.rss_lifetime_peak_bytes = 245 * MiB; s.cgroup_peak_bytes = 260 * MiB; });
  assert.equal(proposed(samples, meta, ready).status, 'FAIL'); // delta145 >128+16
  meta.streams = 5;
  assert.equal(proposed(samples, meta, ready).status, 'PASS');
});
test('PID reuse, cgroup reuse, other container and uninspected freshness cannot establish evidence', () => {
  for (const key of ['engine_pid', 'pid_start_ticks', 'cgroup_inode', 'cgroup_device', 'container_id']) {
    const { ready, meta, samples } = fixture();
    samples[1][key] = 'different';
    assert.equal(proposed(samples, meta, ready).status, 'NOT RUN');
  }
  const { ready, meta, samples } = fixture();
  ready.fresh_container_inspected = false;
  assert.equal(proposed(samples, meta, ready).status, 'NOT RUN');
});
test('baseline within1sec, no >250ms gaps, monotone lifetime counters and real quiescence required', () => {
  for (const change of [
    f => { f.meta.started_ms = 2101; },
    f => { f.samples[1].mono_ms = 1251; },
    f => { f.samples[1].cgroup_peak_bytes -= MiB; },
    f => { f.samples[2].phase = 'active'; },
    f => { f.samples[0].peak_reset_ms = 0; },
    f => { f.samples[1].goroutines = 20; }
  ]) {
    const f = fixture(); change(f);
    assert.equal(proposed(f.samples, f.meta, f.ready).status, 'NOT RUN');
  }
});
test('768MiB cgroup reach and >32MiB quiescent RSS return fail unchanged', () => {
  let f = fixture();
  f.samples.forEach(s => { s.cgroup_peak_bytes = 768 * MiB; });
  assert.equal(proposed(f.samples, f.meta, f.ready).status, 'FAIL');
  f = fixture();
  f.samples[2].rss_bytes = 133 * MiB; f.samples[2].rss_lifetime_peak_bytes = 140 * MiB;
  assert.equal(proposed(f.samples, f.meta, f.ready).status, 'FAIL');
});
