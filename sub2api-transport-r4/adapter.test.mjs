import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { telemetryVerdict } from './adapter.mjs';
const MiB = 1048576;
function fixture() {
  const identity = { instance: 'unit-only', engine_pid: 42, pid_start_ticks: 10, cgroup_path: '/unit-only',
    cgroup_device: 1, cgroup_inode: 2, container_id: 'a'.repeat(64), exe_device: 3, exe_inode: 4 };
  const ready = { ...identity, schema: 'raw-observation-v2', fresh_container_inspected: true,
    container_created_ms: 800, pid_created_ms: 900, first_ready_ms: 1000 };
  const meta = { ...identity, id: 'memory-responses-8-1', streams: 1, started_ms: 1100, ended_ms: 1300 };
  const samples = Array.from({ length: 55 }, (_, i) => {
    const mono_ms = 1000 + i * 100;
    return { ...identity, schema: ready.schema, batch_id: meta.id, collector: 'root-go-pid', clock: 'linux-CLOCK_MONOTONIC',
      mono_ms, sample_started_ms: mono_ms - 1, sample_duration_ms: 1,
      phase: i === 0 ? 'baseline' : mono_ms < meta.ended_ms ? 'active' : 'quiescent',
      rss_bytes: 100 * MiB, raw_vm_hwm_bytes: 120 * MiB, smaps_rollup_rss_bytes: 100 * MiB,
      rss_kind: 'raw-proc-status-approximate', smaps_kind: 'page-table-walk-observation-not-interval-peak',
      mapped_virtual_extent_bytes: 1024 * MiB, mapped_external_candidate_extent_bytes: 50 * MiB,
      maps_count: 3, maps_sha256: 'b'.repeat(64), maps_kind: 'observed-virtual-extents-not-continuous-bound',
      physical_interval_rss_upper_bound_bytes: null, cgroup_current_bytes: 30 * MiB, cgroup_peak_bytes: 60 * MiB,
      cgroup_limit_bytes: 768 * MiB, sockets: 2, goroutines: null, goroutines_source: 'unavailable-instantaneous' };
  });
  ready.first_sample = { ...samples[0] };
  const done = { ...identity, schema: ready.schema, batch_id: meta.id, status: 'DONE', ended_ms: meta.ended_ms,
    last_sample_ms: samples.at(-1).mono_ms, full_tail_ms: samples.at(-1).sample_started_ms - meta.ended_ms };
  return { ready, meta, samples, done };
}
const verdict = f => telemetryVerdict(f.samples, f.meta, f.ready, { done: f.done });
test('before-test history remains11FAIL9NOTRUN/686 attempts and all cleanup', () => {
  const old = JSON.parse(readFileSync(new URL('./historical-input/execution.json', import.meta.url)));
  assert.equal(old.results.filter(r => r.status === 'FAIL').length, 11);
  assert.equal(old.results.filter(r => r.status === 'NOT RUN').length, 9);
  assert.equal(old.total_upstream_attempts, 686);
  assert.ok(old.results.every(r => r.cleanup.failures === 0 && r.cleanup.remaining_resources.length === 0));
});
test('documented Linux6.8 raw decline remains raw with sampled maxima, never physical bound', () => {
  const f = fixture();
  // Public review counter pair; the underlying per-sample snapshot is unavailable in this checkout.
  f.samples[1].raw_vm_hwm_bytes = 295055360;
  f.samples[2].raw_vm_hwm_bytes = 292126720;
  f.samples[1].rss_bytes = 110 * MiB;
  const v = verdict(f);
  assert.equal(v.empirical_qualified_status, 'PASS'); assert.equal(v.status, 'NOT RUN');
  assert.equal(v.physical_interval_rss_status, 'NOTPROVEN');
  assert.equal(v.highest_observed_raw_vm_hwm_bytes, 295055360);
  assert.ok(v.raw_hwm_regressions > 0 && v.raw_rss_regressions > 0);
  assert.equal(v.physical_interval_rss_upper_bound_bytes, null);
  assert.equal(f.samples[2].raw_vm_hwm_bytes, 292126720);
});
test('raw HWM below RSS allowed; missing metrics and fabricated exact values fail closed', () => {
  const f = fixture(); f.samples[1].raw_vm_hwm_bytes = 90 * MiB;
  assert.equal(verdict(f).raw_hwm_below_rss_observations, 1);
  for (const edit of [s => delete s.raw_vm_hwm_bytes, s => s.raw_vm_hwm_bytes = -1,
    s => s.rss_kind = 'exact-physical', s => s.physical_interval_rss_upper_bound_bytes = 120 * MiB,
    s => s.rss_lifetime_peak_bytes = 120 * MiB, s => s.smaps_rollup_rss_bytes = null]) {
    const x = fixture(); edit(x.samples[1]); assert.equal(verdict(x).empirical_qualified_status, 'NOT RUN');
  }
});
test('PID, cgroup, executable, freshness, baseline and source clock stay strict', () => {
  const edits = ['engine_pid','pid_start_ticks','cgroup_path','cgroup_device','cgroup_inode','container_id','exe_device','exe_inode']
    .map(k => f => f.samples[1][k] = 'changed');
  edits.push(f => f.ready.fresh_container_inspected = false, f => f.ready.container_created_ms = 901,
    f => f.meta.started_ms = 2101, f => f.samples[1].clock = 'wall', f => f.samples[0].phase = 'active', f => delete f.ready.first_sample);
  for (const edit of edits) { const f=fixture(); edit(f); assert.equal(verdict(f).empirical_qualified_status,'NOT RUN'); }
});
test('limit, cgroup peak regression,250ms gaps, slow reads, fake resets/goroutines rejected', () => {
  for (const edit of [f => f.samples[1].cgroup_peak_bytes -= MiB, f => f.samples[1].cgroup_limit_bytes -= 1,
    f => f.samples[1].cgroup_current_bytes = 61 * MiB, f => f.samples[1].mono_ms += 151,
    f => f.samples[1].sample_duration_ms = 251, f => f.samples[0].peak_reset_ms = 0,
    f => f.samples[1].goroutines = 0]) {
    const f=fixture(); edit(f); assert.equal(verdict(f).empirical_qualified_status,'NOT RUN');
  }
});
test('512absolute/128+16perstream/768cgroup bounds unchanged', () => {
  let f=fixture(); f.samples[1].smaps_rollup_rss_bytes=513*MiB; assert.equal(verdict(f).status,'FAIL');
  f=fixture(); f.samples[1].rss_bytes=245*MiB; assert.equal(verdict(f).status,'FAIL');
  f.meta.streams=5; assert.equal(verdict(f).empirical_qualified_status,'PASS');
  f=fixture(); f.samples.forEach(s=>s.cgroup_peak_bytes=768*MiB); assert.equal(verdict(f).status,'FAIL');
});
test('full5second tail, acknowledged DONE, and actual endpoint within5sec mandatory;32MiB retained', () => {
  for (const edit of [f=>f.done=undefined, f=>f.done.engine_pid=43, f=>f.done.last_sample_ms--,
    f=>f.samples=f.samples.slice(0,53), f=>f.samples=f.samples.slice(0,24)]) {
    const f=fixture(); edit(f); assert.equal(verdict(f).empirical_qualified_status,'NOT RUN');
  }
  let f=fixture(); f.samples.at(-2).smaps_rollup_rss_bytes=133*MiB;
  assert.equal(verdict(f).status,'FAIL');
  f.samples.at(-2).smaps_rollup_rss_bytes=132*MiB; assert.equal(verdict(f).observed_quiescence_status,'PASS');
});
test('cgroup charge smaller than processRSS valid and never substituted for RSS', () => {
  const v=verdict(fixture()); assert.equal(v.cgroup_lifetime_peak_bytes,60*MiB);
  assert.equal(v.highest_observed_smaps_rollup_rss_bytes,100*MiB);
  assert.equal(v.instantaneous_goroutines,null); assert.equal(v.physical_interval_rss_status,'NOTPROVEN');
});
