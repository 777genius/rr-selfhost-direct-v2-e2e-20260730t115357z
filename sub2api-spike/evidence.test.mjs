import test from 'node:test';
import assert from 'node:assert/strict';
import { financialEvidence, nativeEvents } from './evidence.mjs';
import { withdraw } from '../gateway-spike/fixture/wallet.mjs';
test('A06 successful separate shell-wrapped rules read validates actual source and finding', () => {
  const command = (cmd, text) => ({ type: 'item.completed', item: { type: 'command_execution', command: cmd, exit_code: 0, status: 'completed', aggregated_output: text } });
  const review = JSON.stringify({ findings: [{ file: 'wallet.mjs', function: 'withdraw', summary: 'negative withdrawal increases balance', example: { initial_balance: 100, amount: -10, final_balance: 110 } }] });
  const events = [command("/bin/bash -lc 'cat wallet.mjs'", 'export function withdraw\naccount.balance -= amount'), command("/bin/bash -lc 'cat BUSINESS_RULES.md'", 'A withdrawal must be strictly positive'), { type: 'turn.completed' }];
  assert.equal(financialEvidence('codex', events, review, 'mimo').rules_read_verified, true);
  assert.equal(financialEvidence('codex', events, JSON.stringify(JSON.parse(review).findings), 'mimo').terminal_verified, true);
  events[1].item.aggregated_output = 'file read failed'; assert.throws(() => financialEvidence('codex', events, review, 'mimo'));
});
// Regression: malformed output or synthetic terminal/tool-only event counted as review.
test('A06 malformed and fabricated financial success fail inherited validator', () => {
  for (const review of ['{bad', '{"findings":[]}', '{"findings":[{"file":"wallet.mjs"}]}']) assert.throws(() => financialEvidence('codex', [], review, 'mimo'));
  const account = { balance: 100 }; const actual = withdraw(account, -10); assert.equal(actual.balance, 110); assert.equal(account.balance, 110);
});
// Regression: SSE delimiter CRLF or UTF-8 split corrupts/error event validates green.
test('A10 E04 streamed UTF8 and missing native terminal rejected', async () => {
  const bytes = Buffer.from('event: response.completed\ndata: {"type":"response.completed","response":{"status":"completed"},"note":"金🙂"}\n\n');
  let i = 0; const stream = new ReadableStream({ pull(c) { if (i === bytes.length) c.close(); else c.enqueue(bytes.subarray(i, ++i)); } });
  const response = new Response(stream, { headers: { 'content-type': 'text/event-stream' } }); assert.equal((await nativeEvents(response, 'responses'))[0].note, '金🙂');
  for (const body of ['data: {broken\n\n', 'data: {"type":"response.created"}\n\n', 'data: {"type":"response.failed"}\n\n']) await assert.rejects(nativeEvents(new Response(body, { headers: { 'content-type': 'text/event-stream' } }), 'responses'));
});
