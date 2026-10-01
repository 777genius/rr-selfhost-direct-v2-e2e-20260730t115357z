import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { codexNumericEvidence, financialEvidence, nativeEvents } from './evidence.mjs';
import { withdraw } from '../gateway-spike/fixture/wallet.mjs';
const negative = { initial_balance: 100, amount: -10, final_balance: 110 };
const fractional = { initial_balance: 100, amount: 0.5, final_balance: 99.5 };
const nodeCommand = 'node --input-type=module -e "import { withdraw } from \'./wallet.mjs\'; /* reproduction */"';
const numericEvent = (output, command = nodeCommand) => ({ type: 'item.completed', item: { type: 'command_execution', command, exit_code: 0, status: 'completed', aggregated_output: output } });
const actualProjection = JSON.parse(readFileSync(new URL('../sub2api-evidence-r2/numeric-jsonl-fixture.json', import.meta.url), 'utf8'));
const actualRows = actualProjection.observations[0].rows;
const actualJSONL = actualRows.map(row => JSON.stringify(row)).join('\n');
test('numeric proof accepts actual run36869316283 strict JSONL matching either exact example', () => {
  assert.equal(actualProjection.run_id, '36869316283');
  assert.equal(actualProjection.observations[0].root_format, 'strict-JSONL');
  assert.equal(actualProjection.observations[0].successful_node_wallet_reproduction, true);
  for (const example of actualRows) {
    assert.equal(codexNumericEvidence(numericEvent(actualJSONL), example), true);
    assert.equal(codexNumericEvidence(numericEvent(` \r\n${actualJSONL.replaceAll('\n', '\r\n\t\r\n')}\r\n `), example), true);
    assert.equal(codexNumericEvidence(numericEvent([...actualRows].reverse().map(row => JSON.stringify(row)).join('\n')), example), true);
  }
});
test('strict JSONL consumes every nonblank line as a complete finite numeric object', () => {
  const invalidLines = ['prose', '{broken', 'null', 'true', '100', '"text"', '[]', JSON.stringify(actualRows), '{}', JSON.stringify({ example: actualRows[0] }), ...JSON.stringify(actualRows[0], null, 2).split('\n')];
  for (const key of Object.keys(actualRows[0])) {
    for (const value of [String(actualRows[1][key]), null, true]) invalidLines.push(JSON.stringify({ ...actualRows[1], [key]: value }));
    const missing = { ...actualRows[1] }; delete missing[key]; invalidLines.push(JSON.stringify(missing));
    for (const value of ['1e999', '-1e999', 'NaN', 'Infinity']) invalidLines.push(JSON.stringify(actualRows[1]).replace(`"${key}":${actualRows[1][key]}`, `"${key}":${value}`));
  }
  for (const line of invalidLines) for (const output of [`${line}\n${actualJSONL}`, `${actualJSONL}\n${line}`, `${JSON.stringify(actualRows[0])}\n${line}\n${JSON.stringify(actualRows[1])}`]) {
    assert.equal(codexNumericEvidence(numericEvent(output), actualRows[0]), false, output);
  }
  // A one-line observation remains accepted through the whole-object path.
  const single = actualProjection.observations[1].rows[0];
  assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(single)), single), true);
});
test('strict JSONL compares all three finite fields in one exact example', () => {
  for (const key of Object.keys(actualRows[0])) {
    const rows = [{ ...actualRows[0], [key]: actualRows[0][key] + 1 }, actualRows[1]];
    assert.equal(codexNumericEvidence(numericEvent(rows.map(row => JSON.stringify(row)).join('\n')), actualRows[0]), false);
    assert.equal(codexNumericEvidence(numericEvent(actualJSONL), { ...actualRows[0], [key]: String(actualRows[0][key]) }), false);
  }
  const split = Object.keys(actualRows[0]).map(key => ({ ...actualRows[0], [key]: actualRows[0][key] + 1 }));
  assert.equal(codexNumericEvidence(numericEvent(split.map(row => JSON.stringify(row)).join('\n')), actualRows[0]), false);
});
test('strict JSONL retains completed command admission and successful exit gates', () => {
  const event = numericEvent(actualJSONL);
  for (const mutation of [{ type: 'reasoning' }, { type: 'agent_message' }, { status: 'failed' }, { status: 'in_progress' }, { exit_code: 1 }, { exit_code: '0' }, { command: 'echo withdraw wallet.mjs' }, { command: 'cd /tmp && ' + nodeCommand }]) {
    assert.equal(codexNumericEvidence({ ...event, item: { ...event.item, ...mutation } }, actualRows[0]), false);
  }
  assert.equal(codexNumericEvidence({ ...event, type: 'item.started' }, actualRows[0]), false);
});
test('numeric proof accepts the existing complete JSON object', () => {
  assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative)), negative), true);
  assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative, null, 2)), negative), true);
});
test('numeric proof accepts canary two-object JSON array matching either reported example', () => {
  const event = numericEvent(JSON.stringify([negative, fractional]));
  assert.equal(codexNumericEvidence(event, negative), true);
  assert.equal(codexNumericEvidence(event, fractional), true);
  assert.equal(codexNumericEvidence(numericEvent(JSON.stringify([fractional, negative])), negative), true);
  assert.equal(codexNumericEvidence(numericEvent(JSON.stringify([null, negative, 'irrelevant'], null, 2)), negative), true);
});
test('numeric proof preserves existing direct and shell-wrapped Node command matching', () => {
  for (const shell of ['bash', 'sh', 'zsh']) for (const flag of ['c', 'lc']) for (const quote of ["'", '"']) {
    assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), `/bin/${shell} -${flag} ${quote}${nodeCommand}${quote}`), negative), true);
  }
});
test('numeric proof requires exact finite numbers in all three actual fields', () => {
  for (const key of Object.keys(negative)) for (const value of [negative[key] + 1, String(negative[key]), null, true]) {
    const wrong = { ...negative, [key]: value };
    for (const output of [wrong, [fractional, wrong]]) assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(output)), negative), false);
  }
  for (const key of Object.keys(negative)) {
    const missing = { ...negative }; delete missing[key];
    assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(missing)), negative), false);
    const overflow = JSON.stringify(negative).replace(`"${key}":${negative[key]}`, `"${key}":1e999`);
    assert.equal(codexNumericEvidence(numericEvent(overflow), { ...negative, [key]: Infinity }), false);
  }
  assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative)), { ...negative, amount: '-10' }), false);
});
test('numeric proof parses the complete output and never scans fragments or nested objects', () => {
  const json = JSON.stringify(negative);
  for (const output of ['', '{bad', 'PASS', `log\n${json}`, `${json}\nlog`, `\u0060\u0060\u0060json\n${json}\n\u0060\u0060\u0060`, 'null', 'true', '100', JSON.stringify(json), '[]', '{}', JSON.stringify({ example: negative }), JSON.stringify([[negative]]), JSON.stringify([{ example: negative }])]) {
    assert.equal(codexNumericEvidence(numericEvent(output), negative), false, output);
  }
  assert.equal(codexNumericEvidence(numericEvent(` \n${json}\n `), negative), true);
});
test('numeric proof rejects failed or incomplete tools, reasoning, and wrong commands', () => {
  const event = numericEvent(JSON.stringify(negative));
  for (const type of ['item.started', 'turn.completed', 'reasoning', 'error']) assert.equal(codexNumericEvidence({ ...event, type }, negative), false);
  for (const mutation of [{ type: 'reasoning' }, { type: 'agent_message' }, { status: 'failed' }, { status: 'in_progress' }, { status: undefined }, { exit_code: 1 }, { exit_code: '0' }, { exit_code: undefined }, { command: null }, { aggregated_output: negative }]) {
    assert.equal(codexNumericEvidence({ ...event, item: { ...event.item, ...mutation } }, negative), false);
  }
  for (const command of ['cat wallet.mjs', 'echo withdraw wallet.mjs', 'node -e "console.log(1)"', 'node -e "withdraw()"', 'cd /tmp && ' + nodeCommand, '/usr/bin/' + nodeCommand, 'bash -lc ' + nodeCommand]) {
    assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), command), negative), false);
  }
  assert.equal(codexNumericEvidence(null, negative), false);
});
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
