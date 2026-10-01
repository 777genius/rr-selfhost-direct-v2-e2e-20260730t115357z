// Coordinator integration proposal; canonical regression-lab remains untouched.
const MiB = 1048576;
export function telemetryVerdict(samples, meta, ready, { final = true } = {}) {
  const missing = reason => ({ status: 'NOT RUN', reason });
  const finite = x => Number.isFinite(x) && x >= 0;
  const identity = ['instance', 'engine_pid', 'pid_start_ticks', 'cgroup_path', 'cgroup_device', 'cgroup_inode', 'container_id'];
  if (!ready || ready.schema !== 'fresh-lifetime-v1' || ready.fresh_container_inspected !== true ||
      !/^[a-f0-9]{64}$/.test(ready.container_id ?? '') || !Number.isSafeInteger(meta.engine_pid) || meta.engine_pid <= 0 ||
      ![1, 5, 20].includes(meta.streams) || !finite(meta.started_ms) ||
      ![ready.container_created_ms, ready.pid_created_ms, ready.first_ready_ms].every(finite) ||
      ready.container_created_ms > ready.pid_created_ms || ready.pid_created_ms > ready.first_ready_ms || ready.first_ready_ms > meta.started_ms ||
      identity.some(k => ready[k] === undefined || meta[k] !== ready[k])) return missing('FRESH_LIFETIME_HANDSHAKE_MISSING');
  if (!Array.isArray(samples) || samples.length < 2) return missing('ACTUAL_ENGINE_TELEMETRY_MISSING');
  const keys = ['mono_ms', 'rss_bytes', 'rss_lifetime_peak_bytes', 'cgroup_current_bytes', 'cgroup_peak_bytes', 'sockets'];
  if (samples.some(s => s.collector !== 'root-go-pid' || s.schema !== ready.schema || s.batch_id !== meta.id ||
      s.clock !== 'linux-CLOCK_MONOTONIC' || identity.some(k => s[k] !== ready[k]) ||
      s.cgroup_limit_bytes !== 768 * MiB || keys.some(k => !finite(s[k])) ||
      s.rss_lifetime_peak_bytes < s.rss_bytes || s.cgroup_peak_bytes < s.cgroup_current_bytes ||
      s.peak_reset_ms !== undefined || s.goroutines !== null)) return missing('TELEMETRY_IDENTITY_OR_FIELDS_UNVERIFIED');
  const base = samples[0];
  if (base.phase !== 'baseline' || base.mono_ms < ready.first_ready_ms || base.mono_ms > meta.started_ms ||
      meta.started_ms - base.mono_ms > 1000) return missing('PRELOAD_BASELINE_MISSING');
  if (samples.some((s, i) => i && (s.mono_ms <= samples[i-1].mono_ms || s.mono_ms - samples[i-1].mono_ms > 250 ||
      s.cgroup_peak_bytes < samples[i-1].cgroup_peak_bytes || s.rss_lifetime_peak_bytes < samples[i-1].rss_lifetime_peak_bytes)))
    return missing('SAMPLING_GAP_OR_LIFETIME_COUNTER_REGRESSION');
  const rssPeak = Math.max(...samples.map(s => s.rss_lifetime_peak_bytes));
  const cgPeak = Math.max(...samples.map(s => s.cgroup_peak_bytes));
  const observation = { baseline_rss_bytes: base.rss_bytes, interval_max_rss_bytes: Math.max(...samples.map(s => s.rss_bytes)),
    lifetime_peak_rss_bytes: rssPeak, batch_peak_rss_upper_bound_bytes: rssPeak,
    batch_delta_upper_bound_bytes: Math.max(0, rssPeak - base.rss_bytes), cgroup_lifetime_peak_bytes: cgPeak,
    peak_scope: 'fresh-lifetime-including-startup-and-preparation', samples: samples.length,
    max_sockets: Math.max(...samples.map(s => s.sockets)), instantaneous_goroutines: null };
  if (rssPeak > 512 * MiB || rssPeak - base.rss_bytes > (128 + 16 * meta.streams) * MiB || cgPeak >= 768 * MiB)
    return { status: 'FAIL', reason: 'CONSERVATIVE_LIFETIME_ENVELOPE_EXCEEDED', ...observation };
  if (!final) return { status: 'OBSERVING', ...observation };
  const last = samples.at(-1);
  if (!finite(meta.ended_ms) || meta.ended_ms < meta.started_ms || last.phase !== 'quiescent' ||
      last.mono_ms < meta.ended_ms || last.mono_ms - meta.ended_ms > 5000) return missing('QUIESCENT_TELEMETRY_MISSING');
  if (last.rss_bytes - base.rss_bytes > 32 * MiB)
    return { status: 'FAIL', reason: 'ENGINE_DID_NOT_RETURN_TO_QUIESCENCE', ...observation };
  return { status: 'PASS', ...observation, quiescent_rss_bytes: last.rss_bytes, quiescent_sockets: last.sockets };
}
