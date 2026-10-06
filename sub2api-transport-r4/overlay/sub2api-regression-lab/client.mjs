import http from 'node:http';
import { Inspector, payload } from './wire.mjs';
import { mono } from './common.mjs';
export const slowBytesPerSecond = 2 * 1048576;
// Streaming discard, one bounded frame, one outstanding pause timer, no retries.
export function request(base, key, protocol, id, { toolResult = false, slow = false, onAck, timeout = 65000, onClose } = {}) {
  let req, res, timer, pauseTimer, finish, done = false, paceStart, received = 0;
  const inspector = new Inspector(protocol, onAck);
  const state = { started_ms: mono(), http_status: null, transport: null, client_cancel_ms: null, client_close_ms: null };
  const promise = new Promise(resolve => {
    finish = () => {
      if (done) return; done = true; clearTimeout(timer); clearTimeout(pauseTimer);
      state.client_close_ms = mono(); onClose?.(state.client_close_ms);
      resolve({ ...state, ...inspector.finish(), duration_ms: mono() - state.started_ms });
    };
    req = http.request(`${base}/v1/${protocol}`, { method: 'POST', headers: {
      authorization: `Bearer ${key}`, 'content-type': 'application/json', 'anthropic-version': '2023-06-01' } }, response => {
      res = response; state.http_status = res.statusCode;
      res.on('data', chunk => {
        if (done) return;
        try { if (res.statusCode === 200) inspector.push(chunk); }
        catch { inspector.summary.malformed = true; state.transport = 'invalid_stream'; res.destroy(); req.destroy(); finish(); }
        if (slow && !done) {
          paceStart ??= mono(); received += chunk.length;
          // Cumulative byte debt: TCP fragmentation never adds a fixed chunk penalty.
          const due = paceStart + received * 1000 / slowBytesPerSecond;
          const delay = due - mono();
          if (delay > 0) {
            res.pause(); clearTimeout(pauseTimer);
            pauseTimer = setTimeout(() => { pauseTimer = undefined; if (!done && !res.destroyed) res.resume(); }, delay);
          }
        }
      });
      res.once('end', finish); res.once('aborted', () => { state.transport ??= 'aborted'; finish(); });
      res.once('error', () => { state.transport ??= 'response_error'; finish(); });
    });
    timer = setTimeout(() => { state.transport = 'deadline'; res?.destroy(); req.destroy(); finish(); }, timeout);
    req.once('error', () => { state.transport ??= 'connection_error'; finish(); });
    req.end(JSON.stringify(payload(protocol, id, toolResult)));
  });
  return { promise, cancel() { if (done) return; state.client_cancel_ms ??= mono(); state.transport ??= 'client_cancel'; res?.destroy(); req.destroy(); finish(); }, state };
}
export const success = r => r.http_status === 200 && !r.transport && !r.failed && !r.malformed && r.terminal_ms !== null;
