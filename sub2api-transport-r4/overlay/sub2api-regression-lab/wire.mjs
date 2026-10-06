import { MiB, must, mono } from './common.mjs';
export const models = { responses: 'gpt-4.1', messages: 'claude-sonnet-4-5' };
export const TEXT = 'Привет 世界 🧪 café ';
export const CALL = 'call_rr_transport_01', TOOL = 'toolu_rr_transport_01';
export const event = (type, fields) => Buffer.from(`event: ${type}\ndata: ${JSON.stringify({ type, ...fields })}\n\n`);
export function payload(protocol, id, toolResult = false) {
  const text = `rrlab:${id} ${TEXT}`;
  const params = { type: 'object', properties: { text: { type: 'string' } }, required: ['text'], additionalProperties: false };
  if (protocol === 'responses') return { model: models.responses, stream: true, max_output_tokens: 128,
    tools: [{ type: 'function', name: 'echo', description: 'Synthetic echo', parameters: params }],
    input: [{ role: 'user', content: text }, ...(toolResult ? [
      { type: 'function_call', id: 'fc_lab', call_id: CALL, name: 'echo', arguments: JSON.stringify({ text: TEXT }) },
      { type: 'function_call_output', call_id: CALL, output: TEXT }] : [])] };
  return { model: models.messages, stream: true, max_tokens: 128,
    tools: [{ name: 'echo', description: 'Synthetic echo', input_schema: params }], messages: [
      { role: 'user', content: text }, ...(toolResult ? [
        { role: 'assistant', content: [{ type: 'tool_use', id: TOOL, name: 'echo', input: { text: TEXT } }] },
        { role: 'user', content: [{ type: 'tool_result', tool_use_id: TOOL, content: TEXT }] }] : [])] };
}
// All semantic output is bounded, even when comments make the stream 64 MiB.
// The terminal contains the actual text/tool data; no empty final answer shortcut.
export function fixture(protocol, { tool = false, near = false } = {}) {
  const text = TEXT.repeat(300); // one independently valid >4 KiB text-delta frame
  const args = JSON.stringify({ text: near ? 'x'.repeat(1952 * 1024) : TEXT });
  const input = JSON.parse(args);
  if (protocol === 'responses') {
    let seq = 0;
    const e = (type, data) => event(type, { sequence_number: seq++, ...data });
    const base = { id: 'resp_lab', object: 'response', created_at: 1790812800, model: models.responses, status: 'in_progress', output: [] };
    const msg = { id: 'msg_lab', type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text, annotations: [] }] };
    const fn = { id: 'fc_lab', type: 'function_call', status: 'completed', call_id: CALL, name: 'echo', arguments: args };
    const out = [e('response.created', { response: base }), e('response.in_progress', { response: base })];
    if (!tool) out.push(e('response.output_item.added', { output_index: 0, item: { ...msg, status: 'in_progress', content: [] } }),
      e('response.content_part.added', { item_id: msg.id, output_index: 0, content_index: 0, part: { type: 'output_text', text: '', annotations: [] } }),
      e('response.output_text.delta', { item_id: msg.id, output_index: 0, content_index: 0, delta: text }));
    const early = out.length;
    if (!tool) out.push(e('response.output_text.done', { item_id: msg.id, output_index: 0, content_index: 0, text }),
      e('response.content_part.done', { item_id: msg.id, output_index: 0, content_index: 0, part: msg.content[0] }),
      e('response.output_item.done', { output_index: 0, item: msg }));
    if (tool || near) {
      const index = tool ? 0 : 1;
      out.push(e('response.output_item.added', { output_index: index, item: { ...fn, status: 'in_progress', arguments: '' } }),
        e('response.function_call_arguments.delta', { item_id: fn.id, output_index: index, delta: args }),
        e('response.function_call_arguments.done', { item_id: fn.id, output_index: index, arguments: args }),
        e('response.output_item.done', { output_index: index, item: fn }));
    }
    out.push(e('response.completed', { response: { ...base, status: 'completed', output: tool ? [fn] : near ? [msg, fn] : [msg],
      usage: { input_tokens: 10, output_tokens: 20, total_tokens: 30 } } }));
    return { frames: out, early };
  }
  const out = [event('message_start', { message: { id: 'msg_lab', type: 'message', role: 'assistant', model: models.messages,
    content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 0 } } })];
  if (!tool) out.push(event('content_block_start', { index: 0, content_block: { type: 'text', text: '' } }),
    event('content_block_delta', { index: 0, delta: { type: 'text_delta', text } }));
  const early = out.length;
  if (!tool) out.push(event('content_block_stop', { index: 0 }));
  if (tool || near) {
    const index = tool ? 0 : 1;
    out.push(event('content_block_start', { index, content_block: { type: 'tool_use', id: TOOL, name: 'echo', input: {} } }),
      event('content_block_delta', { index, delta: { type: 'input_json_delta', partial_json: args } }), event('content_block_stop', { index }));
  }
  out.push(event('message_delta', { delta: { stop_reason: tool || near ? 'tool_use' : 'end_turn', stop_sequence: null }, usage: { output_tokens: 20 } }), event('message_stop', {}));
  return { frames: out, early };
}
// Streaming discard inspector. At most one frame retained; comments are discarded.
export class Inspector {
  constructor(protocol, onAck = () => {}) {
    this.protocol = protocol; this.onAck = onAck; this.pending = Buffer.alloc(0);
    this.summary = { bytes: 0, frames: 0, comments: 0, text_delta_bytes: 0, ack_ms: null, ack_frame_bytes: 0,
      terminal_ms: null, failed: false, malformed: false, tool_id: null, max_frame_bytes: 0 };
    this.started = false; this.stopReason = false;
  }
  push(chunk) {
    this.summary.bytes += chunk.length;
    this.pending = Buffer.concat([this.pending, chunk]);
    while (true) {
      const lf = this.pending.indexOf('\n\n'), cr = this.pending.indexOf('\r\n\r\n');
      const i = lf < 0 ? cr : cr < 0 ? lf : Math.min(lf, cr);
      if (i < 0) break;
      const size = i + (i === cr ? 4 : 2); must(size <= 2 * MiB, 'FRAME_LIMIT');
      const raw = this.pending.subarray(0, size); this.pending = size === this.pending.length ? Buffer.alloc(0) : this.pending.subarray(size);
      this.summary.max_frame_bytes = Math.max(this.summary.max_frame_bytes, size);
      const text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
      const data = text.split(/\r?\n/).filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n');
      if (!data) { this.summary.comments++; continue; }
      if (data === '[DONE]') continue;
      const e = JSON.parse(data); this.summary.frames++;
      if (e.type === 'response.created' || e.type === 'message_start') this.started = true;
      must(this.started, 'START_MISSING');
      if (['error', 'response.failed', 'response.error', 'response.incomplete'].includes(e.type) || e.error || e.response?.error) this.summary.failed = true;
      const delta = e.type === 'response.output_text.delta' ? e.delta : e.type === 'content_block_delta' && e.delta?.type === 'text_delta' ? e.delta.text : null;
      if (typeof delta === 'string') {
        this.summary.text_delta_bytes += Buffer.byteLength(delta);
        if (size > 4096 && this.summary.ack_ms === null) {
          this.summary.ack_ms = mono(); this.summary.ack_frame_bytes = size; this.onAck(this.summary.ack_ms, size);
        }
      }
      if (e.item?.call_id === CALL) this.summary.tool_id = CALL;
      if (e.content_block?.id === TOOL) this.summary.tool_id = TOOL;
      if (e.type === 'message_delta' && ['end_turn', 'tool_use'].includes(e.delta?.stop_reason)) this.stopReason = true;
      if (this.protocol === 'responses' ? e.type === 'response.completed' && e.response?.status === 'completed' && e.response.output?.length > 0 : e.type === 'message_stop' && this.stopReason)
        this.summary.terminal_ms = mono();
    }
    must(this.pending.length <= 2 * MiB, 'FRAME_LIMIT');
  }
  finish() { this.summary.malformed ||= this.pending.length > 0; return this.summary; }
}
