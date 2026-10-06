import { MiB } from './common.mjs';
import { success } from './client.mjs';
export function uncertaintyVerdict(row, mode) {
  const rs = row.upstream ?? [], d = row.downstream;
  if (!row.healthy_control || rs.length === 0) return { status: 'NOT RUN', reason: 'UPSTREAM_FAULT_NOT_EXERCISED' };
  if (rs.length !== 1 || rs.reduce((n, r) => n + r.effects, 0) !== (mode === 'pending' ? 0 : 1))
    return { status: 'FAIL', reason: 'AUTOMATIC_RETRY_OR_EFFECT_COUNT' };
  const r = rs[0];
  if (!Number.isFinite(r.reset_ms) || !Number.isFinite(r.close_ms) || !d || success(d) || d.terminal_ms !== null)
    return { status: 'FAIL', reason: 'RESET_HIDDEN_OR_NOT_OBSERVED' };
  if (mode === 'uncertain-after' && !([r.first_flush_ms, d.ack_ms, r.ack_received_ms].every(Number.isFinite) && d.ack_frame_bytes > 4096 && r.first_flush_ms <= d.ack_ms && d.ack_ms <= r.ack_received_ms && r.ack_received_ms < r.reset_ms))
    return { status: 'FAIL', reason: 'COMMITTED_FRAME_NOT_ACKNOWLEDGED' };
  if (mode === 'tool-accepted' && (!row.tool_turn_verified || r.tool_result_accepted !== true))
    return { status: 'FAIL', reason: 'TOOL_RESULT_NOT_ACCEPTED' };
  if (mode !== 'pending' && !(Number.isFinite(r.effect_ms) && r.effect_ms <= r.reset_ms)) return { status: 'FAIL', reason: 'EFFECT_NOT_ACCEPTED' };
  if (mode === 'pending' && r.effect_ms !== null) return { status: 'FAIL', reason: 'PENDING_EFFECT_ALREADY_ACCEPTED' };
  return { status: 'PASS', reason: 'OBSERVABLE_FAILURE_SINGLE_ATTEMPT_NO_RETRY' };
}
export function cancellationVerdict(row, placement) {
  const rs = row.upstream ?? [], cancel = row.cancel_ms, d = row.downstream;
  const fail = reason => ({ status: 'FAIL', reason });
  if (!row.healthy_control || rs.length === 0) return { status: 'NOT RUN', reason: 'UPSTREAM_CANCEL_NOT_EXERCISED' };
  if (rs.length !== 1 || !rs[0] || rs[0].effects !== 1) return fail('UPSTREAM_ATTEMPT_OR_EFFECT_COUNT');
  const r = rs[0], healthy = row.preparation_control;
  if (!healthy?.downstream || !success(healthy.downstream) || !(healthy.downstream.ack_frame_bytes > 4096) ||
      ![healthy.downstream.ack_ms, healthy.downstream.terminal_ms, healthy.downstream.client_close_ms].every(Number.isFinite) ||
      healthy.upstream?.length !== 1 || !healthy.upstream[0] || healthy.upstream[0].effects !== 1 || healthy.upstream[0].finished !== true ||
      healthy.upstream[0].identity !== row.protocol || healthy.upstream[0].protocol !== row.protocol ||
      healthy.upstream[0].id !== `${row.id}.healthy` ||
      ![healthy.upstream[0].effect_ms, healthy.upstream[0].first_flush_ms, healthy.upstream[0].terminal_ms, healthy.upstream[0].close_ms].every(Number.isFinite) ||
      !(healthy.upstream[0].effect_ms <= healthy.upstream[0].first_flush_ms &&
        healthy.upstream[0].first_flush_ms <= healthy.downstream.ack_ms &&
        healthy.downstream.ack_ms <= healthy.downstream.terminal_ms && healthy.downstream.terminal_ms <= healthy.downstream.client_close_ms &&
        healthy.upstream[0].first_flush_ms <= healthy.upstream[0].terminal_ms &&
        healthy.upstream[0].terminal_ms <= healthy.upstream[0].close_ms))
    return fail('HEALTHY_CONTROL_NOT_PROVEN');
  if (!['before', 'after'].includes(placement) || !['client', 'revoke', 'expiry'].includes(row.cancel_trigger) ||
      row.cancel_clock !== 'linux-CLOCK_MONOTONIC' || row.deployment?.clock !== row.cancel_clock ||
      r.id !== row.id || r.identity !== row.protocol || r.protocol !== row.protocol || r.mode !== `hold-${placement}` ||
      !d || ![row.started_ms, d.started_ms, r.started_ms, r.effect_ms, row.action_requested_ms, cancel].every(Number.isFinite) ||
      !(row.started_ms <= d.started_ms && d.started_ms <= r.started_ms && r.started_ms <= r.effect_ms &&
        r.effect_ms <= row.action_requested_ms && row.action_requested_ms <= cancel))
    return fail('CANCEL_ORDER_NOT_PROVEN');
  let abort = cancel;
  if (row.cancel_trigger === 'client') {
    if (d.client_cancel_ms !== cancel || d.transport !== 'client_cancel' || (row.broker_abort_events?.length ?? 0) !== 0)
      return fail('CLIENT_CANCEL_NOT_PROVEN');
  } else {
    const events = row.broker_abort_events;
    if (!Array.isArray(events) || events.length !== 1) return fail('BROKER_PRE_ABORT_NOT_PROVEN');
    const event = events[0];
    if (!event) return fail('BROKER_PRE_ABORT_NOT_PROVEN');
    abort = event.mono_ms;
    if (event.id !== row.id || event.protocol !== row.protocol || event.dispatch !== 1 || event.clock !== row.cancel_clock ||
        !Number.isFinite(abort) || !Number.isFinite(row.broker_boundary_close_ms) ||
        !(cancel <= abort && abort <= row.broker_boundary_close_ms) || row.closed_capability_denied !== true ||
        (row.cancel_trigger === 'revoke' ? event.cause !== 'revoke' || cancel !== row.action_requested_ms
          : !['expiry', 'request-expiry'].includes(event.cause) || cancel !== abort))
      return fail('BROKER_PRE_ABORT_NOT_PROVEN');
  }
  if (placement === 'after' && !([r.first_flush_ms, d.ack_ms, r.ack_received_ms].every(Number.isFinite) &&
      d.ack_frame_bytes > 4096 && r.ack_frame_bytes === d.ack_frame_bytes && r.client_ack_ms === d.ack_ms &&
      r.effect_ms <= r.first_flush_ms && r.first_flush_ms <= d.ack_ms && d.ack_ms <= r.ack_received_ms && r.ack_received_ms < cancel))
    return fail('EARLY_FRAME_NOT_ACKNOWLEDGED');
  if (placement === 'before' && (d.ack_ms !== null || r.first_write_ms !== null || r.first_flush_ms !== null || r.bytes !== 0))
    return fail('CANCEL_WAS_AFTER_OUTPUT');
  const physical = x => x && x.id === row.id && x.identity === row.protocol && x.protocol === row.protocol &&
    Number.isSafeInteger(x.sequence) && x.sequence > 0 && x.sequence === r.sequence &&
    x.mode === r.mode && x.effect_ms === r.effect_ms && x.hold_started_ms === r.hold_started_ms &&
    x.effects === 1 && x.finished === false &&
    Number.isFinite(x.close_ms) && x.close_ms >= abort && x.close_ms - cancel <= 1250 &&
    x.terminal_ms === null && x.release_ms === null && x.reset_ms === null && x.safety_stop_ms === undefined &&
    Number.isFinite(x.hold_started_ms) && x.hold_started_ms <= cancel &&
    x.hold_until_ms === x.hold_started_ms + 10000 && x.close_ms < x.hold_until_ms;
  const immediate = row.upstream_at_immediate_oracle;
  if (!physical(r) || !Array.isArray(immediate) || immediate.length !== 1 || !physical(immediate[0]) ||
      immediate[0].close_ms !== r.close_ms || !Number.isFinite(row.immediate_observation_ms) ||
      row.immediate_observation_ms < cancel + 1250 || row.immediate_observation_ms >= r.hold_until_ms)
    return fail('IMMEDIATE_ABORT_ORACLE_USAGE_DRAIN_PRESERVED');
  // An HTTP error ending normally before SSE headers is permitted; an SSE terminal never is.
  if (d.terminal_ms !== null || success(d) || !Number.isFinite(d.client_close_ms) || d.client_close_ms < cancel)
    return fail('CANCEL_FALSE_SUCCESS');
  return { status: 'PASS', reason: 'PHYSICAL_UPSTREAM_ABORT_OBSERVED_WITHIN_1250MS' };
}
export function telemetryVerdict(samples, meta, { final = true } = {}) {
  const missing = reason => ({ status: 'NOT RUN', reason });
  if (!Array.isArray(samples) || samples.length < 2) return missing('ACTUAL_ENGINE_TELEMETRY_MISSING');
  const numeric = ['mono_ms', 'rss_bytes', 'cgroup_current_bytes', 'cgroup_peak_bytes', 'sockets', 'goroutines'];
  if (samples.some(s => s.collector !== 'root-go-pid' || s.batch_id !== meta.id || s.instance !== meta.instance ||
      s.engine_pid !== meta.engine_pid || s.clock !== 'linux-CLOCK_MONOTONIC' || s.cgroup_limit_bytes !== 768 * MiB ||
      numeric.some(k => !Number.isFinite(s[k]) || s[k] < 0) || s.cgroup_peak_bytes < s.cgroup_current_bytes))
    return missing('TELEMETRY_IDENTITY_OR_FIELDS_UNVERIFIED');
  const base = samples[0];
  if (base.phase !== 'baseline' || base.mono_ms > meta.started_ms || meta.started_ms - base.mono_ms > 1000 ||
      !Number.isFinite(base.peak_reset_ms) || base.peak_reset_ms > base.mono_ms || base.mono_ms - base.peak_reset_ms > 1000)
    return missing('BATCH_BASELINE_OR_CGROUP_PEAK_RESET_MISSING');
  if (samples.some((s, i) => i && (s.mono_ms <= samples[i - 1].mono_ms || s.mono_ms - samples[i - 1].mono_ms > 250)))
    return missing('TELEMETRY_SAMPLING_GAP');
  const peak = Math.max(...samples.map(s => s.rss_bytes)), cgroupPeak = Math.max(...samples.map(s => s.cgroup_peak_bytes));
  const observation = { baseline_rss_bytes: base.rss_bytes, peak_rss_bytes: peak, delta_bytes: peak - base.rss_bytes,
    cgroup_peak_bytes: cgroupPeak, samples: samples.length, max_sockets: Math.max(...samples.map(s => s.sockets)),
    max_goroutines: Math.max(...samples.map(s => s.goroutines)) };
  if (peak > 512 * MiB || peak - base.rss_bytes > (128 + 16 * meta.streams) * MiB || cgroupPeak >= 768 * MiB)
    return { status: 'FAIL', reason: 'ENGINE_MEMORY_ENVELOPE_EXCEEDED', ...observation };
  if (!final) return { status: 'OBSERVING', ...observation };
  const last = samples.at(-1);
  if (last.phase !== 'quiescent' || last.mono_ms < meta.ended_ms || last.mono_ms - meta.ended_ms > 5000 ||
      !samples.some(s => s.mono_ms >= meta.ended_ms)) return missing('QUIESCENT_TELEMETRY_MISSING');
  if (last.rss_bytes - base.rss_bytes > 32 * MiB)
    return { status: 'FAIL', reason: 'ENGINE_DID_NOT_RETURN_TO_QUIESCENCE', ...observation, quiescent_rss_bytes: last.rss_bytes };
  return { status: 'PASS', ...observation, quiescent_rss_bytes: last.rss_bytes, quiescent_sockets: last.sockets, quiescent_goroutines: last.goroutines };
}
