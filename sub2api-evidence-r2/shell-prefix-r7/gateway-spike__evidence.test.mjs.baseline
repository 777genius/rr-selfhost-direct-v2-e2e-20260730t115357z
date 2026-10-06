import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeEvidence } from './evidence.mjs';
const review = JSON.stringify({findings:[{file:'wallet.mjs',function:'withdraw',summary:'Negative withdrawal increases balance.',example:{initial_balance:100,amount:-10,final_balance:110}}]});
const source = 'export function withdraw(account, amount) { account.balance -= amount; }';
const command = { type: 'item.completed', item: { type: 'command_execution', command: '/bin/bash -lc \'cat wallet.mjs\'', status: 'completed', exit_code: 0, aggregated_output: source } };
test('finding alone, failed/incomplete tool execution and terminal error cannot be evidence', () => {
  for (const events of [[], [{ ...command, item: { ...command.item, exit_code: 1 } }], [{ ...command, type: 'item.started' }], [command, { type: 'turn.failed' }], [command, { type: 'error' }]]) assert.throws(() => normalizeEvidence('codex', events, review, 'mimo'));
  assert.throws(() => normalizeEvidence('codex', [command], 'Nothing wrong.', 'mimo'));
});
test('Codex evidence emits fixed normalized fields without transcript or review contents', () => {
  const e = normalizeEvidence('codex', [command], review, 'mimo');
  assert.deepEqual(e, { schema: 1, provider: 'mimo', agent: 'codex', tool_read_verified: true, finding: { file: 'fixture/wallet.mjs', issue: 'negative withdrawal increases balance' }, result: 'passed' });
  assert.equal(normalizeEvidence('codex', [{...command,item:{...command.item,command:"/bin/bash -c 'cat wallet.mjs'"}}], review, 'mimo').tool_read_verified, true);
});
// Red when an echo command or a non-finding narrative can masquerade as a read/finding.
test('echo-only output and denials cannot prove a discovered financial bug', () => {
  assert.throws(() => normalizeEvidence('codex', [{...command,item:{...command.item,command:'echo "cat wallet.mjs"'}}], review, 'mimo'));
  assert.throws(() => normalizeEvidence('codex', [command], 'wallet.mjs withdraw has no negative amount issue and does not increase balance.', 'mimo'));
  assert.throws(() => normalizeEvidence('codex', [command], JSON.stringify({findings:[]}), 'mimo'));
  const wrongExample=JSON.parse(review);wrongExample.findings[0].example.final_balance=90;
  assert.throws(() => normalizeEvidence('codex', [command], JSON.stringify(wrongExample), 'mimo'));
});
test('Messages agent evidence requires matching successful Read tool result', () => {
  const call = { type: 'assistant', message: { content: [{ type: 'tool_use', id: 'read-1', name: 'Read', input: { file_path: '/fixture/wallet.mjs' } }] } };
  const result = { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 'read-1', content: source }] } };
  assert.equal(normalizeEvidence('claude', [call, result, { type: 'result', subtype: 'success' }], review, 'mimo').tool_read_verified, true);
  assert.throws(() => normalizeEvidence('claude', [result], review, 'mimo'));
  assert.throws(() => normalizeEvidence('claude', [call, result, { type: 'result', is_error: true }], review, 'mimo'));
});
