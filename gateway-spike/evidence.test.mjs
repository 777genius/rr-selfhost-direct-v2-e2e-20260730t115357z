import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeEvidence } from './evidence.mjs';
const review = 'wallet.mjs: withdraw accepts a negative amount and increases the balance.';
const source = 'export function withdraw(account, amount) { account.balance -= amount; }';
const command = { type: 'item.completed', item: { type: 'command_execution', status: 'completed', exit_code: 0, aggregated_output: source } };
test('finding alone, failed/incomplete tool execution and terminal error cannot be evidence', () => {
  for (const events of [[], [{ ...command, item: { ...command.item, exit_code: 1 } }], [{ ...command, type: 'item.started' }], [command, { type: 'turn.failed' }], [command, { type: 'error' }]]) assert.throws(() => normalizeEvidence('codex', events, review, 'mimo'));
  assert.throws(() => normalizeEvidence('codex', [command], 'Nothing wrong.', 'mimo'));
});
test('Codex evidence emits fixed normalized fields without transcript or review contents', () => {
  const e = normalizeEvidence('codex', [command], review + ' Unpublishable arbitrary diagnostic.', 'mimo');
  assert.deepEqual(e, { schema: 1, provider: 'mimo', agent: 'codex', tool_read_verified: true, finding: { file: 'fixture/wallet.mjs', issue: 'negative withdrawal increases balance' }, result: 'passed' });
});
test('Messages agent evidence requires matching successful Read tool result', () => {
  const call = { type: 'assistant', message: { content: [{ type: 'tool_use', id: 'read-1', name: 'Read', input: { file_path: '/fixture/wallet.mjs' } }] } };
  const result = { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 'read-1', content: source }] } };
  assert.equal(normalizeEvidence('claude', [call, result, { type: 'result', subtype: 'success' }], review, 'mimo').tool_read_verified, true);
  assert.throws(() => normalizeEvidence('claude', [result], review, 'mimo'));
  assert.throws(() => normalizeEvidence('claude', [call, result, { type: 'result', is_error: true }], review, 'mimo'));
});
