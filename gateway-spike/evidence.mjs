// Only fixed vocabulary escapes the ephemeral client home; no raw agent transcript.
export function normalizeEvidence(agent, events, review, provider) {
  let read = false, failed = false;
  for (const e of events) {
    if (agent === 'codex') {
      if (e.type === 'turn.failed' || e.type === 'error') failed = true;
      const i = e.item;
      if (e.type === 'item.completed' && i?.type === 'command_execution' && i.exit_code === 0 && i.status === 'completed' && typeof i.aggregated_output === 'string' && i.aggregated_output.includes('export function withdraw') && i.aggregated_output.includes('account.balance -= amount')) read = true;
    } else {
      if (e.type === 'result' && (e.is_error || e.subtype !== 'success')) failed = true;
      // A completed Read tool round trip must include actual wallet source.
      if (e.type === 'user') for (const block of e.message?.content ?? []) {
        if (block.type === 'tool_result' && !block.is_error && JSON.stringify(block.content).includes('export function withdraw') && JSON.stringify(block.content).includes('account.balance -= amount')) {
          const tool = events.flatMap(x => x.type === 'assistant' ? x.message?.content ?? [] : []).find(x => x.type === 'tool_use' && x.id === block.tool_use_id && x.name === 'Read' && /wallet\.mjs$/.test(x.input?.file_path ?? ''));
          if (tool) read = true;
        }
      }
    }
  }
  const finding = /wallet\.mjs/i.test(review) && /withdraw/i.test(review) && /negative/i.test(review) && /(increase|creat|money|balance)/i.test(review);
  if (failed || !read || !finding) throw Error('Review did not prove successful file read and required finding');
  return { schema: 1, provider, agent, tool_read_verified: true, finding: { file: 'fixture/wallet.mjs', issue: 'negative withdrawal increases balance' }, result: 'passed' };
}
