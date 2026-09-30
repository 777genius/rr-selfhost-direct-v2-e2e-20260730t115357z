import { normalizeEvidence } from '../gateway-spike/evidence.mjs';
export { normalizeEvidence };
export function parseFindingDocument(review) {
  const parsed = JSON.parse(review.trim().replace(/^```(?:json)?\s*\n([\s\S]*)\n```$/, '$1'));
  return Array.isArray(parsed) ? { findings: parsed } : parsed;
}
// Transport evidence remains separate from genuine client tool/financial proof.
export async function nativeEvents(response, protocol, { maxBytes = 2 * 1024 * 1024 } = {}) {
  if (!response.ok || !response.headers.get('content-type')?.includes('text/event-stream')) throw Error('Native HTTP failure');
  const decoder = new TextDecoder('utf-8', { fatal: true }); let total = 0, pending = '', terminal = false; const events = [];
  for await (const chunk of response.body) {
    total += chunk.byteLength; if (total > maxBytes) throw Error('Stream evidence limit');
    pending = (pending + decoder.decode(chunk, { stream: true })).replace(/\r\n/g, '\n');
    let i;
    while ((i = pending.indexOf('\n\n')) >= 0) {
      const block = pending.slice(0, i); pending = pending.slice(i + 2);
      const data = block.split('\n').filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n');
      if (!data) continue;
      let event; try { event = JSON.parse(data); } catch { throw Error('Malformed SSE'); }
      if (terminal) throw Error('Events after terminal');
      if (['error', 'response.failed', 'response.incomplete'].includes(event.type) || event.error) throw Error('Native error terminal');
      if (protocol === 'responses' && event.type === 'response.completed') { if (event.response?.status !== 'completed') throw Error('Failed completion'); terminal = true; }
      if (protocol === 'messages' && event.type === 'message_stop') terminal = true;
      events.push(event);
    }
  }
  pending += decoder.decode();
  if (pending.trim() || !terminal) throw Error('Missing terminal event');
  return events;
}
export function financialEvidence(agent, events, review, provider) {
  const normalized = normalizeEvidence(agent, events, JSON.stringify(parseFindingDocument(review)), provider);
  const exactRulesRead = command => typeof command === 'string' && (/^cat BUSINESS_RULES\.md$/.test(command.trim()) || /^\/bin\/(?:bash|sh|zsh) -(?:lc|c) (['"])cat BUSINESS_RULES\.md\1$/.test(command.trim()));
  const rulesRead = agent === 'codex' ? events.some(e => e.type === 'item.completed' && e.item?.type === 'command_execution' && exactRulesRead(e.item.command) && e.item.exit_code === 0 && e.item.status === 'completed' && e.item.aggregated_output?.includes('strictly positive') && e.item.aggregated_output?.includes('withdraw')) : events.some(e => e.type === 'user' && e.message?.content?.some(b => b.type === 'tool_result' && !b.is_error && JSON.stringify(b.content).includes('strictly positive') && events.some(a => a.type === 'assistant' && a.message?.content?.some(t => t.type === 'tool_use' && t.id === b.tool_use_id && t.name === 'Read' && /BUSINESS_RULES\.md$/.test(t.input?.file_path ?? '')))));
  const terminal = agent === 'codex' ? events.some(e => e.type === 'turn.completed') : events.some(e => e.type === 'result' && e.subtype === 'success' && !e.is_error);
  if (!rulesRead || !terminal) throw Error('Missing separate rules read or successful terminal');
  return { ...normalized, rules_read_verified: true, terminal_verified: true };
}
