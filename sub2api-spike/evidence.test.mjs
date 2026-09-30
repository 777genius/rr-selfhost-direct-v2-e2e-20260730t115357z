import test from 'node:test';
import assert from 'node:assert/strict';
import { financialEvidence, nativeEvents } from './evidence.mjs';
import { withdraw } from '../gateway-spike/fixture/wallet.mjs';
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
