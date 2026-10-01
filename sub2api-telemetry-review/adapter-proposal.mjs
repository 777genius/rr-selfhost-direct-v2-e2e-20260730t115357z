// Review-only v2 proposal. A sampled green never promotes a physical interval PASS.
const MiB = 1048576;
const identity = ['instance', 'engine_pid', 'pid_start_ticks', 'cgroup_path', 'cgroup_device', 'cgroup_inode', 'container_id', 'exe_device', 'exe_inode'];
export function telemetryVerdict(samples, meta, ready, { final = true } = {}) {
  const missing = reason => ({ status: 'NOT RUN', reason, physical_interval_rss_status: 'NOT RUN' });
  const finite = x => Number.isFinite(x) && x >= 0;
  if (!meta || !ready || ready.schema !== 'raw-observation-v2' || ready.fresh_container_inspected !== true ||
      !/^[a-f0-9]{64}$/.test(ready.container_id ?? '') || !Number.isSafeInteger(meta.engine_pid) || meta.engine_pid <= 0 ||
      ![1, 5, 20].includes(meta.streams) || !finite(meta.started_ms) ||
      ![ready.container_created_ms, ready.pid_created_ms, ready.first_ready_ms].every(finite) ||
      ready.container_created_ms > ready.pid_created_ms || ready.pid_created_ms > ready.first_ready_ms || ready.first_ready_ms > meta.started_ms ||
      identity.some(k => ready[k] === undefined || meta[k] !== ready[k])) return missing('FRESH_IDENTITY_HANDSHAKE_MISSING');
  if (!Array.isArray(samples) || samples.length < 2) return missing('ACTUAL_ENGINE_TELEMETRY_MISSING');
  const numeric = ['mono_ms', 'sample_started_ms', 'sample_duration_ms', 'rss_bytes', 'raw_vm_hwm_bytes',
    'smaps_rollup_rss_bytes', 'mapped_virtual_extent_bytes', 'mapped_external_candidate_extent_bytes',
    'maps_count', 'cgroup_current_bytes', 'cgroup_peak_bytes', 'sockets'];
  if (samples.some(s => s.collector !== 'root-go-pid' || s.schema !== ready.schema || s.batch_id !== meta.id ||
      s.clock !== 'linux-CLOCK_MONOTONIC' || identity.some(k => s[k] !== ready[k]) ||
      s.cgroup_limit_bytes !== 768 * MiB || numeric.some(k => !finite(s[k])) ||
      s.cgroup_peak_bytes < s.cgroup_current_bytes || s.sample_started_ms > s.mono_ms || s.sample_duration_ms > 250 ||
      s.mapped_external_candidate_extent_bytes > s.mapped_virtual_extent_bytes || s.maps_count < 1 ||
      !/^[a-f0-9]{64}$/.test(s.maps_sha256 ?? '') || s.rss_kind !== 'raw-proc-status-approximate' ||
      s.smaps_kind !== 'page-table-walk-observation-not-interval-peak' ||
      s.maps_kind !== 'observed-virtual-extents-not-continuous-bound' ||
      s.physical_interval_rss_upper_bound_bytes !== null || s.peak_reset_ms !== undefined ||
      s.rss_lifetime_peak_bytes !== undefined || s.goroutines !== null || s.goroutines_source !== 'unavailable-instantaneous'))
    return missing('TELEMETRY_IDENTITY_OR_FIELDS_UNVERIFIED');
  const base = samples[0];
  if (base.phase !== 'baseline' || base.mono_ms < ready.first_ready_ms || base.mono_ms > meta.started_ms ||
      meta.started_ms - base.mono_ms > 1000) return missing('PRELOAD_BASELINE_MISSING');
  if (samples.some((s, i) => i && (s.mono_ms <= samples[i-1].mono_ms || s.mono_ms - samples[i-1].mono_ms > 250 ||
      s.cgroup_peak_bytes < samples[i-1].cgroup_peak_bytes))) return missing('SAMPLING_GAP_OR_CGROUP_PEAK_REGRESSION');
  if (samples.some((s, i) => i > 0 && (s.mono_ms < meta.started_ms || !['active', 'quiescent'].includes(s.phase))))
    return missing('PHASE_OR_BOUNDARY_INVALID');
  const highest = key => samples.reduce((n, s) => Math.max(n, s[key]), 0);
  const observation = {
    derived_kind: 'highest-observed-samples-not-physical-interval-bound',
    baseline_raw_vm_rss_bytes: base.rss_bytes, baseline_smaps_rollup_rss_bytes: base.smaps_rollup_rss_bytes,
    highest_observed_raw_vm_rss_bytes: highest('rss_bytes'), highest_observed_raw_vm_hwm_bytes: highest('raw_vm_hwm_bytes'),
    highest_observed_smaps_rollup_rss_bytes: highest('smaps_rollup_rss_bytes'),
    highest_observed_mapped_virtual_extent_bytes: highest('mapped_virtual_extent_bytes'),
    highest_observed_external_candidate_extent_bytes: highest('mapped_external_candidate_extent_bytes'),
    cgroup_lifetime_peak_bytes: highest('cgroup_peak_bytes'),
    raw_hwm_regressions: samples.filter((s, i) => i > 0 && s.raw_vm_hwm_bytes < samples[i-1].raw_vm_hwm_bytes).length,
    raw_hwm_below_rss_observations: samples.filter(s => s.raw_vm_hwm_bytes < s.rss_bytes).length,
    physical_interval_rss_status: 'NOT RUN', physical_interval_rss_upper_bound_bytes: null,
    physical_interval_rss_delta_upper_bound_bytes: null,
    instantaneous_goroutines: null, max_observed_sockets: highest('sockets'), samples: samples.length
  };
  // Both observation series retain 512MiB / 128+16 per stream; HWM is diagnostic only.
  const exceeded = ['rss_bytes', 'smaps_rollup_rss_bytes'].some(k =>
    highest(k) > 512 * MiB || highest(k) - base[k] > (128 + 16 * meta.streams) * MiB);
  if (exceeded || observation.cgroup_lifetime_peak_bytes >= 768 * MiB)
    return { status: 'FAIL', reason: 'OBSERVED_MEMORY_ENVELOPE_EXCEEDED', ...observation };
  if (!final) return { status: 'OBSERVING', ...observation };
  const last = samples.at(-1);
  if (!finite(meta.ended_ms) || meta.ended_ms < meta.started_ms || last.phase !== 'quiescent' ||
      last.sample_started_ms - meta.ended_ms < 4800 || last.mono_ms - meta.ended_ms > 5000 ||
      samples.slice(1).some(s => (s.phase === 'quiescent') !== (s.mono_ms >= meta.ended_ms)))
    return { ...missing('ACTUAL_4_8_SECOND_TAIL_MISSING'), ...observation };
  const quiescence = {
    observed_post_end_ms: last.mono_ms - meta.ended_ms,
    quiescent_raw_vm_rss_bytes: last.rss_bytes, quiescent_smaps_rollup_rss_bytes: last.smaps_rollup_rss_bytes
  };
  if (['rss_bytes', 'smaps_rollup_rss_bytes'].some(k => last[k] - base[k] > 32 * MiB))
    return { status: 'FAIL', reason: 'OBSERVED_ENGINE_DID_NOT_RETURN_TO_QUIESCENCE', ...observation, ...quiescence };
  return { status: 'NOT RUN', reason: 'PHYSICAL_RSS_BETWEEN_SAMPLES_UNPROVEN',
    sampled_envelope_status: 'PASS', cgroup_peak_status: 'PASS', observed_quiescence_status: 'PASS',
    ...observation, ...quiescence };
}
