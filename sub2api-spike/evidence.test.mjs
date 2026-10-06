import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { codexNumericEvidence, financialEvidence, nativeEvents } from './evidence.mjs';
import { withdraw } from '../gateway-spike/fixture/wallet.mjs';
const negative = { initial_balance: 100, amount: -10, final_balance: 110 };
const fractional = { initial_balance: 100, amount: 0.5, final_balance: 99.5 };
const nodeCommand = 'node --input-type=module -e "import { withdraw } from \'./wallet.mjs\'; /* reproduction */"';
const quoteWord = (value, quote = "'") => quote === "'"
  ? "'" + value.replaceAll("'", "'\\''") + "'"
  : '"' + value.replace(/["\\$`]/g, char => '\\' + char) + '"';
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
    assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), `/bin/${shell} -${flag} ${quoteWord(nodeCommand, quote)}`), negative), true);
  }
});
test('numeric proof admits only supported shell prefixes, flags and one Node eval command', () => {
  const output = JSON.stringify(negative);
  for (const prefix of ['/bin', '/usr/bin']) for (const shell of ['bash', 'sh', 'zsh']) for (const flag of ['c', 'lc']) for (const quote of ["'", '"']) {
    assert.equal(codexNumericEvidence(numericEvent(output, `${prefix}/${shell} -${flag} ${quoteWord(nodeCommand, quote)}`), negative), true);
  }
  const invalid = ['bash', '/usr/local/bin/bash', '/tmp/bin/bash', '/usr/bin/bash-evil', '/usr/bin/../bin/bash', '/usr/bin/env bash', '/bin/fish'];
  for (const path of invalid) assert.equal(codexNumericEvidence(numericEvent(output, `${path} -lc ${quoteWord(nodeCommand)}`), negative), false);
  for (const flag of ['--login -c', '-lic', '-l -c', '-c -x', '-lc --']) assert.equal(codexNumericEvidence(numericEvent(output, `/usr/bin/bash ${flag} '${nodeCommand}'`), negative), false);
  for (const command of [`${nodeCommand}; echo ok`, `${nodeCommand} && true`, `${nodeCommand} | cat`, `${nodeCommand} > output`, `node --require ./wallet.mjs -e 'withdraw()'`, 'node /tmp/wallet.mjs withdraw', `node --eval 'withdraw wallet.mjs'`, `node -e 'withdraw wallet.mjs' extra`, `node\n-e 'withdraw wallet.mjs'`, `node -e "withdraw wallet.mjs $(echo injected)"`, `node -e "withdraw wallet.mjs \\\\$(echo injected)"`, `node -e "withdraw wallet.mjs \u0060echo injected\u0060"`, 'echo node withdraw wallet.mjs']) {
    for (const wrapped of [command, `/usr/bin/bash -lc ${quoteWord(command)}`]) assert.equal(codexNumericEvidence(numericEvent(output, wrapped), negative), false, wrapped);
  }
});
test('supported shell numeric proof still rejects incomplete, nonzero, mismatch and stdout prefixes', () => {
  const event = numericEvent(JSON.stringify(negative), `/usr/bin/bash -lc ${quoteWord(nodeCommand)}`);
  for (const mutation of [{ exit_code: 1 }, { exit_code: '0' }, { status: 'in_progress' }, { status: 'failed' }, { type: 'reasoning' }, { aggregated_output: `stdout: ${JSON.stringify(negative)}` }, { aggregated_output: `log\n${JSON.stringify(negative)}` }]) {
    assert.equal(codexNumericEvidence({ ...event, item: { ...event.item, ...mutation } }, negative), false);
  }
  assert.equal(codexNumericEvidence({ ...event, type: 'item.started' }, negative), false);
  for (const key of Object.keys(negative)) assert.equal(codexNumericEvidence(event, { ...negative, [key]: negative[key] + 1 }), false);
});
test('separate rules and wallet reads admit both prefixes and all three supported shells only', () => {
  const read = (cmd, output) => numericEvent(output, cmd);
  const review = JSON.stringify({ findings: [{ file: 'wallet.mjs', function: 'withdraw', summary: 'negative withdrawal increases balance', example: negative }] });
  const wallet = 'export function withdraw\naccount.balance -= amount', rules = 'withdraw must be strictly positive';
  const validate = (w, r) => financialEvidence('codex', [w, r, { type: 'turn.completed' }], review, 'mimo');
  const direct = [read('cat wallet.mjs', wallet), read('cat BUSINESS_RULES.md', rules)];
  assert.equal(validate(...direct).rules_read_verified, true);
  for (const prefix of ['/bin', '/usr/bin']) for (const shell of ['bash', 'sh', 'zsh']) for (const flag of ['c', 'lc']) for (const quote of ["'", '"']) {
    const events = [read(`${prefix}/${shell} -${flag} ${quote}cat wallet.mjs${quote}`, wallet), read(`${prefix}/${shell} -${flag} ${quote}cat BUSINESS_RULES.md${quote}`, rules)];
    assert.equal(validate(...events).rules_read_verified, true);
  }
  for (const [index, file] of [[0, 'wallet.mjs'], [1, 'BUSINESS_RULES.md']]) {
    for (const cmd of [`cat ./${file}`, `cat /tmp/${file}`, `cat -n ${file}`, `cat ${file}; true`, `cat ${file} && true`, `cat ${file} | cat`, `cat ${file} > output`, `echo cat ${file}`, `/usr/local/bin/bash -lc 'cat ${file}'`, `/usr/bin/env bash -lc 'cat ${file}'`, `/bin/fish -c 'cat ${file}'`, `/usr/bin/bash -lic 'cat ${file}'`, `/usr/bin/bash -lc 'cat ${file}' extra`, `/usr/bin/bash -lc 'cat ${file}\"`]) {
      const events = structuredClone(direct); events[index].item.command = cmd;
      assert.throws(() => validate(...events), undefined, cmd);
    }
    for (const mutation of [{ exit_code: 1 }, { exit_code: '0' }, { status: 'in_progress' }, { status: 'failed' }, { aggregated_output: 'read failed' }]) {
      const events = structuredClone(direct); Object.assign(events[index].item, mutation); assert.throws(() => validate(...events));
    }
    const events = structuredClone(direct); events[index].type = 'item.started'; assert.throws(() => validate(...events));
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

// Strings below are classifier input only, never shell execution.
test('R8 all six known shell paths decode escaped and concatenated POSIX words', () => {
  const expression = `import { withdraw } from './wallet.mjs'; const value = "a; b"; withdraw({balance:100}, -10);`;
  const direct = `node --input-type=module -e ${quoteWord(expression)}`;
  assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), direct), negative), true);
  for (const prefix of ['/bin', '/usr/bin']) for (const shell of ['bash', 'sh', 'zsh']) for (const flag of ['c', 'lc']) {
    for (const word of [quoteWord(direct), quoteWord(direct, '"'), `''${quoteWord(direct)}""`, quoteWord(direct).replace("'\\''", `'"'"'`)]) {
      const command = `${prefix}/${shell} -${flag} ${word}`;
      assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), command), negative), true, command);
    }
  }
});
test('R8 structural outer word rejects breakouts, extra argv and active syntax', () => {
  const valid = `node -e 'withdraw wallet.mjs; const x = "nested;JS";'`;
  for (const word of [quoteWord(valid) + ' extra', quoteWord(valid) + '; true', quoteWord(valid) + ' && true', quoteWord(valid) + '|cat', quoteWord(valid) + '>out', quoteWord(valid) + '\ntrue', '"' + valid, "'" + valid, `"${valid} $HOME"`, `"${valid} $(echo injected)"`, `"${valid} \u0060echo injected\u0060"`, quoteWord(valid) + '$HOME', quoteWord(valid) + '*', quoteWord(valid) + '#comment', quoteWord(valid) + '\\', quoteWord(valid) + '\0']) {
    const command = `/usr/bin/bash -lc ${word}`;
    assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), command), negative), false, command);
  }
});
test('R8 inner eval has exactly one literal word and allows nested JS semicolons', () => {
  const expression = `import { withdraw } from './wallet.mjs'; console.log("a;b"); withdraw({balance:100}, -10);`;
  const known = [`node -e ${quoteWord(expression)}`, `node --input-type=module -e ${quoteWord(expression, '"')}`, `node -e 'withdraw '\"wallet.mjs\"`, `node -e 'withdraw '\\'wallet.mjs\\'`, `node -e 'withdraw wallet.mjs $literal \u0060literal\u0060'`];
  for (const command of known) for (const input of [command, `/usr/bin/bash -lc ${quoteWord(command)}`, `/bin/sh -c ${quoteWord(command, '"')}`]) {
    assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), input), negative), true, input);
  }
  const evalCommand = known[0];
  for (const command of [evalCommand + '; echo injected', evalCommand + ' && true', evalCommand + ' | cat', evalCommand + ' extra', evalCommand + '\ntrue', `node -e 'withdraw wallet.mjs';'ignored'`, `node -e 'withdraw wallet.mjs' > out`, `node -e "withdraw wallet.mjs $HOME"`, `node -e "withdraw wallet.mjs $(true)"`, `node -e "withdraw wallet.mjs \u0060true\u0060"`, `node -e $'withdraw wallet.mjs'`, `node -e 'withdraw wallet.mjs'"`, 'node -e withdraw\\ wallet.mjs', '/usr/bin/node -e ' + quoteWord(expression), `node --input-type=module --eval ${quoteWord(expression)}`]) {
    for (const input of [command, `/usr/bin/bash -lc ${quoteWord(command)}`]) assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), input), negative), false, input);
  }
});
test('R8 observed argv rendering admits genuine projected wallet reproduction', () => {
  const projection = JSON.parse(readFileSync(new URL('../sub2api-evidence-r2/shell-prefix-r7/actual-command-projection.json', import.meta.url), 'utf8'));
  const observed = projection[2];
  for (const quote of ["'", '"']) {
    const command = `${observed.command[0]} ${observed.command[1]} ${quoteWord(observed.command[2], quote)}`;
    assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(observed.numeric), command), observed.numeric), true);
    for (const mutation of [{ exit_code: 1 }, { exit_code: '0' }, { status: 'in_progress' }, { aggregated_output: 'prefix ' + JSON.stringify(observed.numeric) }, { aggregated_output: JSON.stringify({ ...observed.numeric, final_balance: 1249 }) }]) {
      const event = numericEvent(JSON.stringify(observed.numeric), command);
      assert.equal(codexNumericEvidence({ ...event, item: { ...event.item, ...mutation } }, observed.numeric), false);
    }
  }
});
test('R8 heredoc compatibility boundary rejects even literal delimiter forms', () => {
  for (const command of ["node --input-type=module <<'NODE'\nimport { withdraw } from './wallet.mjs';\nNODE", "node <<'NODE'\nwithdraw wallet.mjs\nNODE", "node <<'NODE'\nwithdraw wallet.mjs\nWRONG", "node <<NODE\nwithdraw wallet.mjs\nNODE", "node <<'NODE'\nwithdraw wallet.mjs\nNODE\necho injected"]) {
    for (const input of [command, `/usr/bin/bash -lc ${quoteWord(command)}`]) assert.equal(codexNumericEvidence(numericEvent(JSON.stringify(negative), input), negative), false);
  }
});
