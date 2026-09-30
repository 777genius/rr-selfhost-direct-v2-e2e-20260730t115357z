// Synthetic transport fault server. It is not Sub2API or OAuth proof.
import http from 'node:http';
import { once } from 'node:events';
import { readJSON, send } from './util.mjs';
export function mockUpstream({ mode = 'native', delayMs = 500, identity = 'synthetic-upstream-a' } = {}) {
  let controlledMode = null, controlledDelay = delayMs;
  const observations = []; const metrics = { requests: 0, active: 0, aborted: 0, finished: 0 };
  const server = http.createServer(async (req, res) => {
    if (req.url.startsWith('/__synthetic/')) {
      if (req.url === '/__synthetic/metrics' && req.method === 'GET') { send(res, 200, { ...metrics, observations: observations.map(o => ({ path: o.path, model: o.body.model, identity_matches: o.headers.authorization === `Bearer ${identity}` || o.headers['x-api-key'] === identity, tool_ids: (o.body.input ?? []).filter?.(b => b.type === 'function_call_output').map(b => b.call_id) ?? [] })) }); return; }
      if (req.url === '/__synthetic/config' && req.method === 'POST') { const b = await readJSON(req, 4096); if (!['native', 'large', 'reset', 'partial-reset', 'truncate', 'malformed', 'slow-body', 'slow-headers', 'terminal-error'].includes(b.mode) && !/^http-(400|401|403|404|429|500|502|503)$/.test(b.mode)) { send(res, 400, { error: 'invalid_synthetic_mode' }); return; } controlledMode = b.mode; controlledDelay = Math.min(5000, Math.max(0, Number(b.delayMs) || delayMs)); send(res, 200, { configured: true }); return; }
      if (req.url === '/__synthetic/reset' && req.method === 'POST' && metrics.active === 0) { observations.length = 0; for (const k of Object.keys(metrics)) metrics[k] = 0; send(res, 200, { reset: true }); return; }
      send(res, 409, { error: 'synthetic_control_denied' }); return;
    }
    metrics.requests++; metrics.active++;
    res.on('close', () => { metrics.active--; if (!res.writableFinished) metrics.aborted++; else metrics.finished++; });
    try {
      const body = await readJSON(req);
      observations.push({ path: req.url, headers: req.headers, body });
      const selected = controlledMode ?? (typeof mode === 'function' ? mode(body) : mode);
      if (/^http-\d{3}$/.test(selected)) { res.setHeader('retry-after', '2'); send(res, Number(selected.slice(5)), { error: { message: 'synthetic-provider-credential-sentinel', type: 'upstream_failure' } }); return; }
      if (selected === 'reset') { res.destroy(); return; }
      if (selected === 'slow-headers') { await new Promise(r => setTimeout(r, controlledDelay)); if (res.destroyed) return; }
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      if (selected === 'slow-body') { res.write(': waiting\n\n'); await new Promise(r => setTimeout(r, controlledDelay)); if (res.destroyed) return; }
      if (selected === 'malformed') { res.end('event: response.completed\ndata: {broken\n\n'); return; }
      const messages = req.url === '/v1/messages';
      if (selected === 'terminal-error') { const type = messages ? 'error' : 'response.failed'; res.end(`event: ${type}\ndata: ${JSON.stringify({ type, error: { type: 'synthetic_failure' } })}\n\n`); return; }
      const toolResult = messages ? body.messages?.flatMap(m => Array.isArray(m.content) ? m.content : []).find(b => b.type === 'tool_result') : body.input?.find?.(b => b.type === 'function_call_output');
      const content = JSON.stringify({ identity, model: body.model, toolResult: toolResult ?? null, unicode: 'Кошелёк 金額 🙂', padding: selected === 'large' ? '金🙂'.repeat(50000) : '' });
      const chunks = messages ? [
        { type: 'message_start', message: { id: 'synthetic-message', type: 'message', role: 'assistant', content: [], model: body.model } },
        { type: 'content_block_start', index: 0, content_block: toolResult ? { type: 'text', text: '' } : { type: 'tool_use', id: 'synthetic-tool-1', name: 'Read', input: {} } },
        { type: 'content_block_delta', index: 0, delta: toolResult ? { type: 'text_delta', text: content } : { type: 'input_json_delta', partial_json: '{"file_path":"wallet.mjs"}' } },
        { type: 'content_block_stop', index: 0 }, { type: 'message_delta', delta: { stop_reason: toolResult ? 'end_turn' : 'tool_use' } }, { type: 'message_stop' }
      ] : [
        { type: 'response.created', response: { id: 'synthetic-response', status: 'in_progress' } },
        toolResult ? { type: 'response.output_text.delta', delta: content } : { type: 'response.output_item.added', item: { type: 'function_call', id: 'synthetic-item', call_id: 'synthetic-call-1', name: 'read', arguments: '{"file":"wallet.mjs"}' } },
        { type: 'response.completed', response: { id: 'synthetic-response', status: 'completed', output: [] } }
      ];
      if (selected === 'truncate') chunks.pop();
      const bytes = Buffer.from(chunks.map(e => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join(''));
      // Deliberately split UTF-8 code points and SSE lines at byte boundaries.
      for (let i = 0; i < bytes.length; i += 127) {
        if (res.destroyed) return;
        if (!res.write(bytes.subarray(i, i + 127))) await Promise.race([once(res, 'drain'), once(res, 'close')]);
      }
      if (selected === 'partial-reset') { res.destroy(); return; }
      res.end();
    } catch { if (!res.destroyed) res.destroy(); }
  });
  return { server, observations, metrics };
}
if (process.argv[1]?.endsWith('/mock-upstream.mjs')) mockUpstream({ mode: process.env.SYNTHETIC_MODE ?? 'native', identity: process.env.SYNTHETIC_IDENTITY ?? 'synthetic-upstream-a' }).server.listen(8081, '0.0.0.0');
