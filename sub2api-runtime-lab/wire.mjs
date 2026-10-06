// Synthetic native wire fixtures; no provider traffic or Chat Completions bridging.
export const TEXT = 'Привет 世界 🧪 café';
export const CALL = 'call_rr_lab_exact_01';
export const TOOL = 'toolu_rr_lab_exact_01';
export const models = { responses: 'gpt-4.1', messages: 'claude-sonnet-4-5' };
const event = (type, body) => `event: ${type}\ndata: ${JSON.stringify({ type, ...body })}\n\n`;
export function responses(tool = false, failed = false) {
  const item = tool
    ? { id: 'fc_rr_lab_01', type: 'function_call', call_id: CALL, name: 'echo', arguments: JSON.stringify({ text: TEXT }), status: 'completed' }
    : { id: 'msg_rr_lab_01', type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: TEXT, annotations: [] }] };
  const base = { id: 'resp_rr_lab_01', object: 'response', created_at: 1790798400, model: models.responses, output: [], status: 'in_progress' };
  const out = [event('response.created', { response: base, sequence_number: 0 }), event('response.in_progress', { response: base, sequence_number: 1 }),
    event('response.output_item.added', { output_index: 0, item: { ...item, status: 'in_progress', ...(tool ? { arguments: '' } : { content: [] }) }, sequence_number: 2 })];
  if (tool) {
    out.push(event('response.function_call_arguments.delta', { item_id: item.id, output_index: 0, delta: item.arguments, sequence_number: 3 }));
    out.push(event('response.function_call_arguments.done', { item_id: item.id, output_index: 0, arguments: item.arguments, sequence_number: 4 }));
  } else {
    out.push(event('response.content_part.added', { item_id: item.id, output_index: 0, content_index: 0, part: { type: 'output_text', text: '', annotations: [] }, sequence_number: 3 }));
    out.push(event('response.output_text.delta', { item_id: item.id, output_index: 0, content_index: 0, delta: TEXT, sequence_number: 4 }));
    out.push(event('response.output_text.done', { item_id: item.id, output_index: 0, content_index: 0, text: TEXT, sequence_number: 5 }));
    out.push(event('response.content_part.done', { item_id: item.id, output_index: 0, content_index: 0, part: item.content[0], sequence_number: 6 }));
  }
  out.push(event('response.output_item.done', { output_index: 0, item, sequence_number: 7 }));
  out.push(event(failed ? 'response.failed' : 'response.completed', { sequence_number: 8, response: { ...base, status: failed ? 'failed' : 'completed', output: [item], error: failed ? { code: 'synthetic_failure', message: 'synthetic terminal failure' } : null, usage: { input_tokens: 10, output_tokens: 12, total_tokens: 22, input_tokens_details: { cached_tokens: 0 }, output_tokens_details: { reasoning_tokens: 0 } } } }));
  return out;
}
export function messages(tool = false, failed = false) {
  const block = tool ? { type: 'tool_use', id: TOOL, name: 'echo', input: {} } : { type: 'text', text: '' };
  return [event('message_start', { message: { id: 'msg_rr_lab_01', type: 'message', role: 'assistant', model: models.messages, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 0 } } }),
    event('content_block_start', { index: 0, content_block: block }),
    event('content_block_delta', { index: 0, delta: tool ? { type: 'input_json_delta', partial_json: JSON.stringify({ text: TEXT }) } : { type: 'text_delta', text: TEXT } }),
    event('content_block_stop', { index: 0 }),
    ...(failed ? [event('error', { error: { type: 'api_error', message: 'synthetic terminal failure' } })] : [event('message_delta', { delta: { stop_reason: tool ? 'tool_use' : 'end_turn', stop_sequence: null }, usage: { output_tokens: 12 } }), event('message_stop', {})])];
}
// Inspect downstream bytes, including HTTP 200 failed terminals. No exceptions become success.
export function inspectSSE(bytes, protocol) {
  const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  let malformed = false;
  const events = [];
  for (const block of text.replaceAll('\r\n', '\n').split('\n\n')) {
    const data = block.split('\n').filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n');
    if (!data || data === '[DONE]') continue;
    try { events.push(JSON.parse(data)); } catch { malformed = true; }
  }
  const failed = events.some(x => ['error', 'response.failed', 'response.incomplete', 'response.error'].includes(x.type) || ['failed', 'incomplete'].includes(x.response?.status));
  const terminal = protocol === 'responses' ? events.some(x => x.type === 'response.completed' && x.response?.status === 'completed') : events.some(x => x.type === 'message_stop') && events.some(x => x.type === 'message_delta' && ['end_turn', 'tool_use'].includes(x.delta?.stop_reason));
  const calls = events.flatMap(x => [x.item?.call_id, x.content_block?.id, ...(x.response?.output ?? []).map(y => y.call_id)]).filter(Boolean);
  const deltas = events.map(x => typeof x.delta === 'string' ? x.delta : x.delta?.text ?? '').join('');
  return { terminal, failed, malformed, calls, utf8: deltas.includes(TEXT), event_types: [...new Set(events.map(x => x.type).filter(Boolean))], success: terminal && !failed && !malformed };
}
