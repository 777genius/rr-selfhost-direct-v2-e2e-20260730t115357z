import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { telemetryVerdict } from './adapter-proposal.mjs';
const MiB = 1048576;
// Synthetic fixtures only; public actual values appear only in the first test.
function fixture() {
  const identity = { instance: 'unit-only', engine_pid: 42, pid_start_ticks: 10, cgroup_path: '/unit-only',
    cgroup_device: 1, cgroup_inode: 2, container_id: 'a'.repeat(64), exe_device: 3, exe_inode: 4 };
  const ready = { ...identity, schema: 'raw-observation-v2', fresh_container_inspected: true,
    container_created_ms: 800, pid_created_ms: 900, first_ready_ms: 950 };
  const meta = { ...identity, id: 'memory-responses-8-1', streams: 1, started_ms: 1100, ended_ms: 1300 };
  const samples = Array.from({ length: 53 }, (_, i) => {
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
  return { ready, meta, samples };
}
const verdict = f => telemetryVerdict(f.samples, f.meta, f.ready);
test('actual Linux6.8 regression remains raw and highest observed stays derived, never physical PASS', () => {
  const raw = readFileSync(new URL('../.spike-inputs/actual/memory-responses-8-20/telemetry/memory-responses-8-20.ndjson', import.meta.url), 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(raw[15].rss_lifetime_peak_bytes, 295055360);
  assert.equal(raw[16].rss_lifetime_peak_bytes, 292126720);
  const f = fixture();
  f.samples[1].raw_vm_hwm_bytes = raw[15].rss_lifetime_peak_bytes;
  f.samples[2].raw_vm_hwm_bytes = raw[16].rss_lifetime_peak_bytes;
  const v = verdict(f);
  assert.equal(v.status, 'NOT RUN');
  assert.equal(v.reason, 'PHYSICAL_RSS_BETWEEN_SAMPLES_UNPROVEN');
  assert.equal(v.highest_observed_raw_vm_hwm_bytes, 295055360);
  assert.ok(v.raw_hwm_regressions > 0);
  assert.equal(v.physical_interval_rss_upper_bound_bytes, null);
  assert.equal(v.sampled_envelope_status, 'PASS');
  assert.equal(f.samples[2].raw_vm_hwm_bytes, 292126720);
});
test('HWM below VmRSS allowed only with raw kinds, missing counters never fabricated', () => {
  const f = fixture(); f.samples[1].raw_vm_hwm_bytes = 90 * MiB;
  assert.equal(verdict(f).raw_hwm_below_rss_observations, 1);
  for (const edit of [s => delete s.raw_vm_hwm_bytes, s => s.raw_vm_hwm_bytes = -1,
    s => s.rss_kind = 'exact-physical', s => s.physical_interval_rss_upper_bound_bytes = 120 * MiB,
    s => s.rss_lifetime_peak_bytes = 120 * MiB]) {
    const x = fixture(); edit(x.samples[1]);
    assert.equal(verdict(x).reason, 'TELEMETRY_IDENTITY_OR_FIELDS_UNVERIFIED');
  }
});
test('identity, executable, freshness, creation order, baseline and clock stay strict', () => {
  const edits = ['engine_pid', 'pid_start_ticks', 'cgroup_path', 'cgroup_device', 'cgroup_inode', 'container_id', 'exe_device', 'exe_inode']
    .map(k => f => f.samples[1][k] = 'changed');
  edits.push(f => f.ready.fresh_container_inspected = false, f => f.ready.container_created_ms = 901,
    f => f.meta.started_ms = 2101, f => f.samples[1].clock = 'wall', f => f.samples[0].phase = 'active');
  for (const edit of edits) { const f = fixture(); edit(f); assert.equal(verdict(f).status, 'NOT RUN'); }
});
test('cgroup regression, limit, gaps, slow page walks, reset and fake goroutines stay rejected', () => {
  for (const edit of [f => f.samples[1].cgroup_peak_bytes -= MiB, f => f.samples[1].cgroup_limit_bytes -= 1,
    f => f.samples[1].cgroup_current_bytes = 61 * MiB, f => f.samples[1].mono_ms += 151,
    f => f.samples[1].sample_duration_ms = 251, f => f.samples[0].peak_reset_ms = 0,
    f => f.samples[1].goroutines = 0, f => f.samples[1].smaps_rollup_rss_bytes = null]) {
    const f = fixture(); edit(f);
    assert.notEqual(verdict(f).reason, 'PHYSICAL_RSS_BETWEEN_SAMPLES_UNPROVEN');
    assert.equal(verdict(f).status, 'NOT RUN');
  }
});
test('512 absolute, 128+16 per stream delta and strict 768 cgroup bounds unchanged', () => {
  let f = fixture(); f.samples[1].smaps_rollup_rss_bytes = 513 * MiB; assert.equal(verdict(f).status, 'FAIL');
  f = fixture(); f.samples[1].rss_bytes = 245 * MiB; assert.equal(verdict(f).status, 'FAIL');
  f.meta.streams = 5; assert.equal(verdict(f).sampled_envelope_status, 'PASS');
  f = fixture(); f.samples.forEach(s => s.cgroup_peak_bytes = 768 * MiB); assert.equal(verdict(f).status, 'FAIL');
});
test('two-second failure preserved as old receipt; 4.8sec tail necessary, >32MiB still fails', () => {
  const old = JSON.parse(readFileSync(new URL('../.spike-inputs/actual/memory-responses-8-1/evidence/memory-responses-8-1.json', import.meta.url)));
  assert.equal(old.acceptance_status, 'FAIL'); assert.equal(old.memory_envelope.reason, 'ENGINE_DID_NOT_RETURN_TO_QUIESCENCE');
  let f = fixture(); f.samples = f.samples.slice(0, 24); assert.equal(verdict(f).reason, 'ACTUAL_4_8_SECOND_TAIL_MISSING');
  f = fixture(); f.samples.at(-1).smaps_rollup_rss_bytes = 133 * MiB; assert.equal(verdict(f).status, 'FAIL');
  f.samples.at(-1).smaps_rollup_rss_bytes = 132 * MiB; assert.equal(verdict(f).observed_quiescence_status, 'PASS');
});
test('cgroup charge smaller than RSS is valid but never a physical RSS bound', () => {
  const f = fixture(); const v = verdict(f);
  assert.equal(v.cgroup_peak_status, 'PASS'); assert.equal(v.cgroup_lifetime_peak_bytes, 60 * MiB);
  assert.equal(v.highest_observed_smaps_rollup_rss_bytes, 100 * MiB);
  assert.equal(v.physical_interval_rss_status, 'NOT RUN'); assert.equal(v.status, 'NOT RUN');
});
