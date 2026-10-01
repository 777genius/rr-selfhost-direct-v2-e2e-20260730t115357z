import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { fixture, CALL, TOOL, TEXT } from './wire.mjs';
import { mono, MiB, must } from './common.mjs';
export function createMock({ control_token, sentinels }) {
  must(control_token?.length >= 24, 'CONTROL_TOKEN_REQUIRED');
  const rules = new Map(), records = [], live = new Map();
  let total = 0, effects = 0, active = 0, exceeded = false;
  const send = (res, status, data) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(data)); };
  const server = http.createServer(async (req, res) => {
    try {
      const u = new URL(req.url, 'http://mock');
      if (u.pathname.startsWith('/__lab/')) {
        if (req.headers['x-lab-control'] !== control_token) return send(res, 403, { code: 'CONTROL_DENIED' });
        const b = req.method === 'POST' ? await body(req) : {};
        if (u.pathname === '/__lab/state' && req.method === 'GET') return send(res, 200, { total, effects, active, exceeded, records });
        must(/^[a-z0-9_.-]{1,110}$/.test(b.id ?? ''), 'CASE_ID_INVALID');
        if (u.pathname === '/__lab/rule') {
          must(['healthy', 'tool', 'memory', 'hold-before', 'hold-after', 'uncertain-before', 'uncertain-after', 'tool-accepted', 'pending'].includes(b.mode), 'RULE_INVALID');
          must(b.mode !== 'memory' || [8, 32, 64].includes(b.mib), 'MEMORY_SIZE_INVALID');
          must(rules.size < 2000 && !rules.has(b.id), 'RULE_ALREADY_EXISTS_OR_LIMIT');
          rules.set(b.id, { mode: b.mode, mib: b.mib }); return send(res, 200, { ok: true });
        }
        const hits = records.filter(r => r.id === b.id);
        if (u.pathname === '/__lab/ack') {
          must(Number.isFinite(b.mono_ms) && b.frame_bytes > 4096 && b.frame_bytes <= 2 * MiB, 'ACK_INVALID');
          for (const r of hits) { r.client_ack_ms ??= b.mono_ms; r.ack_received_ms ??= mono(); r.ack_frame_bytes = b.frame_bytes; }
        } else if (u.pathname === '/__lab/release') {
          for (const r of hits) if (live.has(r.sequence)) {
            must(mono() >= r.hold_until_ms, 'HOLD_NOT_FINISHED');
            r.release_ms = mono(); live.get(r.sequence).release();
          }
        } else if (u.pathname === '/__lab/reset' || u.pathname === '/__lab/stop') {
          for (const r of hits) if (live.has(r.sequence)) {
            r.reset_ms = mono(); live.get(r.sequence).reset();
          }
        } else return send(res, 404, { code: 'CONTROL_ROUTE_DENIED' });
        return send(res, 200, { matched: hits.length });
      }
      // Count every provider attempt, including create probes and denied over-budget attempts.
      total++; if (total > 2000) { exceeded = true; return send(res, 429, { error: { type: 'lab_budget_exhausted' } }); }
      const auth = req.headers.authorization?.replace(/^Bearer /i, '') ?? req.headers['x-api-key'];
      const identity = Object.entries(sentinels).find(([, v]) => v === auth)?.[0] ?? 'UNKNOWN';
      const protocol = u.pathname.endsWith('/responses') ? 'responses' : u.pathname.endsWith('/messages') ? 'messages' : 'probe';
      const b = await body(req);
      const id = JSON.stringify(b.input ?? b.messages ?? '').match(/rrlab:([a-z0-9_.-]{1,110})/)?.[1] ?? 'preparation';
      const rule = rules.get(id) ?? { mode: 'healthy' };
      const result = protocol === 'responses' ? b.input?.find?.(x => x.type === 'function_call_output')
        : b.messages?.flatMap(x => Array.isArray(x.content) ? x.content : []).find(x => x.type === 'tool_result');
      const matched = result ? (protocol === 'responses' ? result.call_id === CALL && result.output === TEXT : result.tool_use_id === TOOL && result.content === TEXT) : null;
      const r = { sequence: total, id, identity, protocol, mode: rule.mode, started_ms: mono(), effect_ms: null,
        first_write_ms: null, first_flush_ms: null, client_ack_ms: null, ack_received_ms: null, ack_frame_bytes: 0, release_ms: null,
        reset_ms: null, terminal_ms: null, close_ms: null, hold_until_ms: null, bytes: 0, finished: false, tool_result_accepted: matched, effects: 0 };
      records.push(r); active++;
      let release;
      const held = new Promise(resolve => { release = resolve; });
      const reset = () => { res.destroy(); release(); };
      live.set(r.sequence, { release, reset });
      const deadline = setTimeout(() => { r.safety_stop_ms = mono(); reset(); }, rule.mode === 'memory' ? 65000 : 25000);
      res.once('close', () => { r.close_ms = mono(); r.finished = res.writableFinished; active--; clearTimeout(deadline); live.delete(r.sequence); release(); });
      if (identity !== protocol || matched === false || protocol === 'probe') return send(res, 400, { error: { type: 'synthetic_scope_denied' } });
      // This increment is the actual synthetic upstream effect, independent of response bytes.
      if (rule.mode !== 'pending') { r.effect_ms = mono(); r.effects = 1; effects++; }
      res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }); res.flushHeaders();
      const f = fixture(protocol, { tool: rule.mode === 'tool', near: rule.mode === 'memory' });
      const hold = ['hold-before', 'hold-after', 'uncertain-before', 'uncertain-after', 'tool-accepted', 'pending'].includes(rule.mode);
      const early = ['hold-after', 'uncertain-after'].includes(rule.mode);
      let index = 0;
      if (early) for (; index < f.early && !res.destroyed; index++) await write(f.frames[index]);
      if (hold) {
        r.hold_started_ms = mono(); r.hold_until_ms = r.hold_started_ms + (rule.mode.startsWith('hold-') ? 10000 : 0);
        await held;
      }
      if (res.destroyed) return;
      if (rule.mode === 'memory') {
        // Reserve wire bytes for all semantic frames; rest are valid bounded SSE comments.
        const semanticBytes = f.frames.reduce((n, x) => n + x.length, 0);
        let remaining = rule.mib * MiB - semanticBytes;
        for (; index < f.early && !res.destroyed; index++) await write(f.frames[index]);
        const comment = Buffer.from(`: ${'x'.repeat(16380)}\n\n`);
        while (remaining > 0 && !res.destroyed) {
          const size = remaining <= comment.length + 4 ? remaining : comment.length;
          if (size < 5) { await write(Buffer.from(': x\n\n')); remaining = 0; }
          else { await write(size === comment.length ? comment : Buffer.from(`: ${'x'.repeat(size - 4)}\n\n`)); remaining -= size; }
        }
      }
      for (; index < f.frames.length && !res.destroyed; index++) {
        await write(f.frames[index], index === f.frames.length - 1);
      }
      if (!res.destroyed) res.end();
      async function write(bytes, terminal = false) {
        if (res.destroyed) return;
        // Distinct call/flush-callback timestamps. Callback is transport flush, not client acknowledgement.
        r.first_write_ms ??= mono(); r.bytes += bytes.length;
        if (!res.write(bytes, error => {
          if (!error) { r.first_flush_ms ??= mono(); if (terminal) r.terminal_ms = mono(); }
        })) await new Promise(resolve => {
          const done = () => { res.off('drain', done); res.off('close', done); resolve(); };
          res.once('drain', done); res.once('close', done);
        });
      }
    } catch { if (!res.headersSent) send(res, 400, { code: 'LAB_REQUEST_REJECTED' }); else res.destroy(); }
  });
  server.requestTimeout = 10000; server.headersTimeout = 10000;
  server.stopLab = () => { for (const c of live.values()) c.reset(); };
  return server;
}
async function body(req) {
  let size = 0; const parts = [];
  for await (const b of req) { size += b.length; must(size <= 2 * MiB, 'BODY_LIMIT'); parts.push(b); }
  return JSON.parse(Buffer.concat(parts).toString() || '{}');
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const c = JSON.parse(await readFile('/private/lab.json', 'utf8'));
    const server = createMock(c); server.listen(8099, '0.0.0.0');
    process.on('SIGTERM', () => { server.stopLab(); server.close(); server.closeAllConnections(); });
  } catch { process.stderr.write('LAB_MOCK_START_FAILED\n'); process.exitCode = 1; }
}
