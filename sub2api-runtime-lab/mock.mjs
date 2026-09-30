import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { responses, messages, models, CALL, TOOL, TEXT } from './wire.mjs';
const wait = ms => new Promise(r => setTimeout(r, ms));
export function createMock({ controlToken, identities = {}, maxRecords = 30000 } = {}) {
  if (!controlToken || controlToken.length < 24) throw new Error('control_token_required');
  const records = [];
  const rules = new Map();
  let total = 0, active = 0, maxActive = 0;
  const byIdentity = new Map();
  const json = (res, status, value) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(value)); };
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://mock');
      const control = url.pathname.startsWith('/__control/');
      if (control && req.headers['x-lab-control'] !== controlToken) return json(res, 403, { error: 'operator_only' });
      const chunks = [];
      let size = 0;
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 2 * 1024 * 1024) return json(res, 413, { error: 'body_limit' });
        chunks.push(chunk);
      }
      let body = {};
      try { body = JSON.parse(Buffer.concat(chunks).toString() || '{}'); } catch { return json(res, 400, { error: 'invalid_json' }); }
      if (control) {
        if (req.method === 'GET' && url.pathname === '/__control/records') return json(res, 200, { total, active, max_active: maxActive, records, overflow: total > maxRecords });
        if (req.method === 'POST' && url.pathname === '/__control/rule') {
          if (!/^[a-zA-Z0-9_.-]{1,100}$/.test(body.id ?? '')) return json(res, 400, { error: 'invalid_id' });
          rules.set(body.id, body);
          return json(res, 200, { ok: true });
        }
        return json(res, 404, { error: 'unknown_control' });
      }
      // Credential bytes are compared only in memory. Evidence contains sentinel labels only.
      const auth = req.headers.authorization?.replace(/^Bearer /i, '') ?? req.headers['x-api-key'];
      const identity = Object.entries(identities).find(([, value]) => value === auth)?.[0] ?? 'UNKNOWN';
      const protocol = url.pathname.endsWith('/responses') ? 'responses' : url.pathname.endsWith('/messages') ? 'messages' : 'probe';
      const inputString = JSON.stringify(body.input ?? body.messages ?? '');
      const id = inputString.match(/rrlab:([a-zA-Z0-9_.-]+)/)?.[1] ?? req.headers['x-lab-case'] ?? 'background';
      const rule = rules.get(id) ?? {};
      const scenario = rule.accounts?.[identity] ?? rule.scenario ?? (typeof body.model === 'string' && body.model.startsWith('rrlab:') ? body.model.slice(6) : 'ok');
      const n = (byIdentity.get(identity) ?? 0) + 1;
      byIdentity.set(identity, n);
      const rec = { sequence: ++total, case_id: id, identity, protocol, path: url.pathname, model: typeof body.model === 'string' && Object.values(models).includes(body.model) ? body.model : 'OTHER', scenario, started_ms: Date.now(), ended_ms: null, finished: false, cancelled: false, committed: false, backpressure: 0, bytes: 0, active_identity: 0, tool_result_id: null, tool_result_utf8: false, tool_result_length: 0, version_header: req.headers['anthropic-version'] ?? null };
      const result = protocol === 'responses' ? body.input?.find?.(x => x.type === 'function_call_output') : body.messages?.flatMap(x => Array.isArray(x.content) ? x.content : []).find(x => x.type === 'tool_result');
      if (result) {
        rec.tool_result_id = result.call_id === CALL ? CALL : result.tool_use_id === TOOL ? TOOL : 'OTHER';
        const output = typeof result.output === 'string' ? result.output : typeof result.content === 'string' ? result.content : JSON.stringify(result.content);
        rec.tool_result_utf8 = output.includes(TEXT);
        rec.tool_result_length = output.length;
      }
      if (records.length < maxRecords) records.push(rec);
      active++;
      maxActive = Math.max(active, maxActive);
      rec.active_identity = records.filter(x => x.identity === identity && !x.ended_ms).length;
      let ended = false;
      const end = finished => { if (ended) return; ended = true; active--; rec.ended_ms = Date.now(); rec.finished = finished; rec.cancelled = !finished; };
      res.on('finish', () => end(true));
      res.on('close', () => end(res.writableFinished));
      if (scenario === 'reset-before') return req.socket.destroy();
      if (scenario === 'slow-headers') await wait(rule.delay_ms ?? 6000);
      if (res.destroyed) return;
      if (/^http-(400|401|403|404|429|500|502|503)$/.test(scenario)) {
        res.setHeader('retry-after', '2');
        return json(res, Number(scenario.slice(5)), { error: { type: 'synthetic_error', message: 'synthetic HTTP failure' } });
      }
      if (protocol === 'probe') return json(res, 404, { error: 'synthetic_probe_unsupported' });
      res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', 'x-request-id': `rr-lab-${total}` });
      res.flushHeaders();
      const tool = scenario === 'tool';
      let frames = protocol === 'responses' ? responses(tool, scenario === 'failed') : messages(tool, scenario === 'failed');
      if (scenario === 'error') frames = ['event: error\ndata: {"type":"error","error":{"type":"api_error","message":"synthetic"}}\n\n'];
      if (scenario === 'truncated') frames = frames.slice(0, -1);
      if (scenario === 'malformed') frames = [frames[0], 'event: broken\ndata: {invalid-json}\n\n'];
      if (scenario === 'reset-after') frames = frames.slice(0, 4);
      if (scenario === 'slow-body' || scenario === 'hold') {
        await write(frames.shift());
        await wait(rule.delay_ms ?? 6000);
      }
      if (scenario === 'backpressure') {
        // SSE comments generate bounded pressure without inventing completion events.
        for (let i = 0; i < 512 && !res.destroyed; i++) await write(`: ${'x'.repeat(16384)}\n\n`);
      }
      for (const frame of frames) {
        if (res.destroyed) break;
        // Deliberately split inside multibyte UTF-8 on every fixture.
        const bytes = Buffer.from(frame);
        for (let i = 0; i < bytes.length && !res.destroyed; i += 7) await write(bytes.subarray(i, i + 7));
      }
      if (scenario === 'reset-after') return req.socket.destroy();
      if (!res.destroyed) res.end();
      async function write(chunk) {
        if (res.destroyed) return;
        rec.committed = true;
        rec.bytes += Buffer.byteLength(chunk);
        if (!res.write(chunk)) {
          rec.backpressure++;
          await new Promise(resolve => {
            const done = () => { res.off('drain', done); res.off('close', done); resolve(); };
            res.once('drain', done); res.once('close', done);
          });
        }
      }
    } catch {
      if (!res.headersSent) json(res, 500, { error: 'synthetic_handler_failure' });
      else res.destroy();
    }
  });
  server.requestTimeout = 10000;
  server.headersTimeout = 10000;
  return server;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const config = JSON.parse(await readFile(process.env.LAB_CONFIG ?? '/private/lab.json', 'utf8'));
    createMock({ controlToken: config.control_token, identities: config.sentinels }).listen(8099, '0.0.0.0', () => process.stdout.write('synthetic upstream ready on private port 8099\n'));
  } catch { process.stderr.write('mock configuration/start failure (details withheld)\n'); process.exitCode = 1; }
}
