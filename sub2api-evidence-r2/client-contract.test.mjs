// Local caller contract: synthetic agent I/O, real independent Node reproduction.
// This is not a coordinator/container/provider E2E or a real-Actions receipt.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { randomUUID } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve, join } from 'node:path';
import { tmpdir } from 'node:os';
const execute = promisify(execFile);
const actualProjection = JSON.parse(await readFile(new URL('./numeric-jsonl-fixture.json', import.meta.url), 'utf8'));
const actualRows = actualProjection.observations[0].rows;
const actualDocument = { findings: actualRows.map(example => ({ file: 'wallet.mjs', function: 'withdraw', summary: 'Invalid withdrawal is accepted', example })) };
const actualNodeExpression = `import { withdraw } from "./wallet.mjs"; for (const {initial_balance,amount} of ${JSON.stringify(actualRows)}) console.log(JSON.stringify({initial_balance,amount,final_balance:withdraw({balance:initial_balance},amount).balance}));`;
const clientURL = new URL('../sub2api-spike/run-client.mjs', import.meta.url);
const fixture = fileURLToPath(new URL('../sub2api-spike/fixture/', import.meta.url));
const negative = { initial_balance: 100, amount: -10, final_balance: 110 };
const fractional = { initial_balance: 100, amount: 0.5, final_balance: 99.5 };
const document = { findings: [negative, fractional].map(example => ({ file: 'wallet.mjs', function: 'withdraw', summary: 'Invalid withdrawal is accepted', example })) };
const nodeExpression = 'import { withdraw } from "./wallet.mjs"; const examples = [{initial_balance:100,amount:-10},{initial_balance:100,amount:0.5}]; console.log(JSON.stringify(examples.map(({initial_balance,amount}) => ({initial_balance,amount,final_balance:withdraw({balance:initial_balance},amount).balance}))));';
const command = (cmd, output) => ({ type: 'item.completed', item: { type: 'command_execution', command: cmd, aggregated_output: output, exit_code: 0, status: 'completed' } });
async function run(options = {}) {
  const sourceURL = process.env.RUN_CLIENT_SOURCE ? pathToFileURL(resolve(process.env.RUN_CLIENT_SOURCE)) : clientURL;
  const source = await readFile(sourceURL, 'utf8');
  const wallet = await readFile(new URL('../sub2api-spike/fixture/wallet.mjs', import.meta.url), 'utf8');
  const rules = await readFile(new URL('../sub2api-spike/fixture/BUSINESS_RULES.md', import.meta.url), 'utf8');
  const sha = 'b'.repeat(40), receipts = [], sealed = [], effects = [], errors = [], independentExits = [], agentCalls = [], writes = [], key = randomUUID();
  const events = options.events ?? [command('cat wallet.mjs', wallet), command('cat BUSINESS_RULES.md', rules),
    command(`node --input-type=module -e '${options.nodeExpression ?? nodeExpression}'`, options.output ?? JSON.stringify([negative, fractional])), { type: 'turn.completed' }];
  const p = { versions: { node: '24.21.0' }, version: process.version, stdout: { write: value => { if (options.writeFailed) throw Error('synthetic private write detail'); receipts.push(JSON.parse(value)); } } };
  const io = {
    process: p, console: { error: message => errors.push(message) }, mkdir: async () => {}, chown: async () => {}, rm: async () => {}, writeFile: async (path, body) => writes.push({ path, body }), readFile: async () => sha,
    requireControl: () => {}, readControlInput: async () => ({ runID: '123', runAttempt: '2', workflowSHA: sha, provider: 'mimo', agent: 'codex', oidcURL: 'https://example.actions.githubusercontent.com/token', oidcToken: 'synthetic' }),
    privateControlHome: async () => '/synthetic/control', agentHome: async () => '/synthetic/agent', cleanAgentEnv: () => ({}), agentIdentity: { uid: 1002, gid: 1002 },
    sealedPath: async path => { sealed.push(path); if (options.sealDenied) throw Error('unsealed'); }, verifyFixture: async () => {}, verifyTools: async () => {},
    safeAgentFile: async () => options.review ?? JSON.stringify(document),
    fetch: async url => ({ ok: true, json: async () => String(url).includes('/grant') ? { runID: '123', attempt: '2', workflowSHA: sha, provider: 'mimo', protocol: 'responses', model: 'mimo-v2.6-pro', capability: 's'.repeat(43) } : { value: 'synthetic' } }),
    spawnAgent: async (binary, args, { onLine }) => {
      effects.push(binary);
      if (args[0] === '--version') return 'codex-cli 0.159.2';
      if (binary === 'node') {
        if (options.independentOutput !== undefined) return options.independentOutput;
        if (options.independentFailed) throw Error('synthetic private independent error');
        try { const result = await execute(process.execPath, args, { cwd: fixture, timeout: 5000 }); independentExits.push(0); return result.stdout; }
        catch (error) { independentExits.push(error.code); throw error; }
      }
      agentCalls.push(args);
      for (const event of events) onLine(JSON.stringify(event));
      if (options.agentFailed) throw Error('agent failed');
      return '';
    },
  };
  globalThis[key] = io;
  let injected = `const { ${Object.keys(io).join(', ')} } = globalThis[${JSON.stringify(key)}];\n`;
  for (const line of source.split('\n')) {
    if (/^import .*from '(node:fs\/promises|\.\/runner-isolation.mjs)'/.test(line)) continue;
    const relocated = line.startsWith('import ') ? line.replace(/from '(\.\/[^']+)'/g, (_, path) => `from '${new URL(path, sourceURL).href}'`) : line;
    injected += relocated.replaceAll('import.meta.url', JSON.stringify(sourceURL.href)) + '\n';
  }
  try { await import('data:text/javascript;base64,' + Buffer.from(injected).toString('base64')); }
  finally { delete globalThis[key]; }
  return { receipts, sealed, effects, errors, independentExits, exitCode: p.exitCode, events, agentCalls, writes };
}
for (const [shape, output] of [['object', JSON.stringify(negative)], ['canary-shaped array', JSON.stringify([negative, fractional])]]) {
  test(`caller accepts ${shape} with real independent reproduction`, async () => {
    const result = await run({ output });
    assert.equal(result.exitCode, undefined, JSON.stringify({ errors: result.errors, effects: result.effects }));
    assert.equal(result.receipts.length, 1);
    assert.equal(result.effects.filter(binary => binary === 'node').length, 1);
    for (const gate of ['tool_read_verified', 'rules_read_verified', 'terminal_verified', 'independent_numeric_reproduction']) assert.equal(result.receipts[0][gate], true);
    assert.ok(result.sealed.includes(fileURLToPath(new URL('../sub2api-spike/evidence.mjs', import.meta.url))));
    assert.equal(Object.hasOwn(result.receipts[0], 'capability'), false);
  });
}
test('caller accepts actual local Node wallet execution emitting both numeric examples', async () => {
  const { stdout } = await execute(process.execPath, ['--input-type=module', '-e', nodeExpression], { cwd: fixture, timeout: 5000 });
  assert.deepEqual(JSON.parse(stdout), [negative, fractional]);
  const result = await run({ output: stdout });
  assert.equal(result.exitCode, undefined);
  assert.equal(result.receipts.length, 1);
});
test('caller accepts actual run36869316283 JSONL from local wallet plus independent reproduction', async () => {
  const { stdout } = await execute(process.execPath, ['--input-type=module', '-e', actualNodeExpression], { cwd: fixture, timeout: 5000 });
  assert.equal(stdout, actualRows.map(row => JSON.stringify(row)).join('\n') + '\n');
  const result = await run({ output: stdout, review: JSON.stringify(actualDocument), nodeExpression: actualNodeExpression });
  assert.equal(result.exitCode, undefined, JSON.stringify(result.errors));
  assert.equal(result.receipts.length, 1);
  assert.equal(result.effects.filter(binary => binary === 'node').length, 1);
  assert.deepEqual(result.independentExits, [0]);
  for (const gate of ['tool_read_verified', 'rules_read_verified', 'terminal_verified', 'independent_numeric_reproduction']) assert.equal(result.receipts[0][gate], true);
  assert.equal(Object.hasOwn(result.receipts[0], 'capability'), false);
  assert.deepEqual(result.sealed, ['./run-client.mjs', './granted-run.mjs', './runner-isolation.mjs', './evidence.mjs', '../gateway-spike/evidence.mjs'].map(path => fileURLToPath(new URL(path, clientURL))));
});
test('caller denies invalid JSONL lines and exact numeric mismatches', async () => {
  const valid = actualRows.map(row => JSON.stringify(row)).join('\n');
  const outputs = ['prose', '{broken', '[]', JSON.stringify(actualRows), JSON.stringify({ ...actualRows[1], amount: '25.5' }), JSON.stringify(actualRows[1]).replace('974.5', '1e999')].map(line => `${valid}\n${line}`);
  outputs.push([{ ...actualRows[0], final_balance: 1049 }, actualRows[1]].map(row => JSON.stringify(row)).join('\n'));
  for (const output of outputs) {
    const result = await run({ output, review: JSON.stringify(actualDocument), nodeExpression: actualNodeExpression });
    assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []);
  }
  const wrong = { findings: [{ ...actualDocument.findings[0], example: { ...actualRows[0], final_balance: 1049 } }] };
  const result = await run({ output: [wrong.findings[0].example, actualRows[1]].map(row => JSON.stringify(row)).join('\n'), review: JSON.stringify(wrong), nodeExpression: actualNodeExpression });
  assert.deepEqual(result.independentExits, [1]);
  assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []);
});
test('caller retains reads, terminal, genuine final and successful tool requirements with JSONL', async () => {
  const options = { output: actualRows.map(row => JSON.stringify(row)).join('\n'), review: JSON.stringify(actualDocument), nodeExpression: actualNodeExpression };
  const { events } = await run(options);
  const mutate = (index, changes) => events.map((event, i) => i === index ? { ...event, item: { ...event.item, ...changes } } : event);
  const cases = [mutate(2, { exit_code: 1 }), mutate(2, { status: 'failed' }), mutate(2, { command: 'echo withdraw wallet.mjs' }), events.filter((_, i) => i !== 0), events.filter((_, i) => i !== 1), events.filter(event => event.type !== 'turn.completed'), [...events, { type: 'turn.failed' }]];
  for (const selection of cases) { const result = await run({ ...options, events: selection }); assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []); }
  for (const review of ['', 'reasoning about the wallet', '{bad', '{"findings":[]}']) {
    const result = await run({ ...options, review }); assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []);
  }
});
test('caller denies bad own proof and independent reproduction mismatch', async () => {
  for (const output of ['PASS', '{broken', JSON.stringify([{ ...negative, final_balance: 109 }]), JSON.stringify([{ ...negative, amount: '-10' }])]) {
    const result = await run({ output }); assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []);
  }
  const wrong = { findings: [{ ...document.findings[0], example: { ...negative, final_balance: 109 } }] };
  const result = await run({ review: JSON.stringify(wrong), output: JSON.stringify(wrong.findings[0].example) });
  assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []);
});
test('caller denies failed tools, wrong commands, missing separate reads and unsuccessful terminals', async () => {
  const { events } = await run();
  const mutated = (index, changes) => events.map((event, i) => i === index ? { ...event, item: { ...event.item, ...changes } } : event);
  const cases = [mutated(2, { exit_code: 1 }), mutated(2, { status: 'failed' }), mutated(2, { command: 'echo withdraw wallet.mjs' }), mutated(0, { exit_code: 1 }), mutated(1, { exit_code: 1 }), mutated(0, { command: 'cat wallet.mjs BUSINESS_RULES.md' }), events.filter((_, i) => i !== 0), events.filter((_, i) => i !== 1), events.filter(event => event.type !== 'turn.completed'), [...events, { type: 'turn.failed' }]];
  for (const selection of cases) { const result = await run({ events: selection }); assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []); }
});
test('caller denies reasoning-only final, malformed final, agent failure and unsealed import', async () => {
  for (const options of [{ review: '' }, { review: 'reasoning about the wallet' }, { review: '{bad' }, { review: '{"findings":[]}' }, { agentFailed: true }, { sealDenied: true }]) {
    const result = await run(options); assert.equal(result.exitCode, 1); assert.deepEqual(result.receipts, []);
    if (options.sealDenied) assert.deepEqual(result.effects, []);
  }
});

const safeFailure = (result, phase) => {
  assert.equal(result.exitCode, 1);
  assert.deepEqual(result.receipts, []);
  assert.deepEqual(result.errors, [`Spike failed at ${phase}; inspect effects privately before retry.`]);
};
test('observed run36879127384 usr-bin-bash argv regression with locally reproduced stdout', async () => {
  const projection = JSON.parse(await readFile(new URL('./shell-prefix-r7/actual-command-projection.json', import.meta.url), 'utf8'));
  const diagnosis = JSON.parse(await readFile(new URL('./shell-prefix-r7/actual-agent-projection.json', import.meta.url), 'utf8'));
  assert.equal(diagnosis.run_id, '36879127384'); assert.equal(diagnosis.failure_phase, 'evidence_tool_numeric');
  const observed = projection[2], example = diagnosis.finding_examples[0];
  assert.deepEqual(observed.command.slice(0, 2), ['/usr/bin/bash', '-lc']);
  assert.deepEqual(observed.numeric, example); assert.equal(observed.output_is_single_json, true);
  // The supplied projection is argv/metadata, not captured CLI stdout. Execute
  // only its Node expression locally; derive a CLI-style command string for tests.
  const expression = /^node --input-type=module -e "([\s\S]*)"$/.exec(observed.command[2])[1];
  const { stdout } = await execute(process.execPath, ['--input-type=module', '-e', expression], { cwd: fixture, timeout: 5000 });
  assert.equal(stdout, JSON.stringify(example) + '\n'); assert.equal(Buffer.byteLength(stdout), observed.output_bytes);
  const render = row => `${row.command[0]} ${row.command[1]} '${row.command[2].replaceAll("'", "'\\''")}'`;
  const events = [command(render(projection[0]), await readFile(new URL('../sub2api-spike/fixture/wallet.mjs', import.meta.url), 'utf8')), command(render(projection[1]), await readFile(new URL('../sub2api-spike/fixture/BUSINESS_RULES.md', import.meta.url), 'utf8')), command(render(observed), stdout), { type: 'turn.completed' }];
  const review = JSON.stringify({ findings: [{ file: 'wallet.mjs', function: 'withdraw', summary: 'negative withdrawal increases balance', example }] });
  const result = await run({ events, review });
  assert.equal(result.exitCode, undefined, JSON.stringify(result.errors)); assert.deepEqual(result.independentExits, [0]); assert.equal(result.receipts.length, 1);
  for (const gate of ['tool_read_verified', 'rules_read_verified', 'terminal_verified', 'independent_numeric_reproduction']) assert.equal(result.receipts[0][gate], true);
  for (const [index, mutation, phase] of [[2, { exit_code: 1 }, 'evidence_tool_numeric'], [2, { status: 'in_progress' }, 'evidence_tool_numeric'], [2, { aggregated_output: `stdout: ${stdout}` }, 'evidence_tool_numeric'], [2, { aggregated_output: JSON.stringify({ ...example, final_balance: 1249 }) }, 'evidence_tool_numeric'], [0, { command: "/usr/bin/bash -lc 'cat wallet.mjs BUSINESS_RULES.md'" }, 'evidence_agent_contract'], [1, { command: "/usr/bin/bash -lc 'cat BUSINESS_RULES.md; true'" }, 'evidence_agent_contract']]) {
    safeFailure(await run({ events: events.map((e, i) => i === index ? { ...e, item: { ...e.item, ...mutation } } : e), review }), phase);
  }
  safeFailure(await run({ events: events.slice(0, 3), review }), 'evidence_agent_contract');
  safeFailure(await run({ events, review: JSON.stringify({ findings: [{ file: 'wallet.mjs', function: 'withdraw', summary: 'wrong', example: { ...example, final_balance: 1249 } }] }) }), 'evidence_independent_reproduction');
});
// Behavioral phase regressions: the unmodified caller reports only "evidence".
test('caller diagnoses parse failures with fixed stderr and no private output', async () => {
  for (const review of ['private-agent-output private-key private-reasoning', '{bad', 'null']) {
    safeFailure(await run({ review }), 'evidence_parse');
  }
});
test('caller diagnoses absent or nonfinite numeric examples before local execution', async () => {
  const invalid = ['{}', '{"findings":[]}', '{"findings":{}}'];
  for (const key of Object.keys(negative)) {
    for (const value of [String(negative[key]), null, true]) invalid.push(JSON.stringify({ findings: [{ ...document.findings[0], example: { ...negative, [key]: value } }] }));
    invalid.push(JSON.stringify({ findings: [{ ...document.findings[0], example: negative }] }).replace(`"${key}":${negative[key]}`, `"${key}":1e999`));
  }
  for (const review of invalid) {
    const result = await run({ review }); safeFailure(result, 'evidence_numeric_example');
    assert.equal(result.effects.includes('node'), false);
  }
});
test('caller diagnoses independent wallet rejection and private subprocess failures', async () => {
  const wrong = { findings: [{ ...document.findings[0], example: { ...negative, final_balance: 109 } }] };
  const result = await run({ review: JSON.stringify(wrong), output: JSON.stringify(wrong.findings[0].example) });
  safeFailure(result, 'evidence_independent_reproduction'); assert.deepEqual(result.independentExits, [1]);
  for (const options of [{ independentFailed: true }, { independentOutput: 'private-node-output private-key' }, { independentOutput: '{"reproduced":false}' }]) {
    safeFailure(await run(options), 'evidence_independent_reproduction');
  }
});
test('caller diagnoses exact own numeric matching and completed zero-exit admission', async () => {
  const { events } = await run();
  for (const output of ['private-agent-output private-key private-reasoning', JSON.stringify({ ...negative, final_balance: 109 }), JSON.stringify({ ...negative, amount: '-10' })]) {
    safeFailure(await run({ output }), 'evidence_tool_numeric');
  }
  for (const changes of [{ exit_code: 1 }, { exit_code: '0' }, { status: 'failed' }, { type: 'reasoning' }, { command: 'echo withdraw wallet.mjs' }]) {
    safeFailure(await run({ events: events.map((event, i) => i === 2 ? { ...event, item: { ...event.item, ...changes } } : event) }), 'evidence_tool_numeric');
  }
});
test('caller diagnoses final finding, separate exact reads and genuine terminal contract', async () => {
  const { events } = await run();
  for (const selection of [events.filter((_, i) => i !== 0), events.filter((_, i) => i !== 1), events.filter(e => e.type !== 'turn.completed'), [...events, { type: 'turn.failed', error: 'private-terminal-error private-key' }], events.map((event, i) => i === 0 ? { ...event, item: { ...event.item, command: 'cat wallet.mjs BUSINESS_RULES.md' } } : event)]) {
    safeFailure(await run({ events: selection }), 'evidence_agent_contract');
  }
  safeFailure(await run({ review: JSON.stringify({ findings: [{ ...document.findings[0], summary: '' }] }) }), 'evidence_agent_contract');
});
test('caller diagnoses evidence write without leaking private write error', async () => {
  safeFailure(await run({ writeFailed: true }), 'evidence_write');
});
test('caller delivers green receipt with minimal standalone Node output contract and HIGH model', async () => {
  const expression = `import { withdraw } from "./wallet.mjs"; const initial_balance=100, amount=-10; const final_balance=withdraw({balance:initial_balance},amount).balance; console.log(JSON.stringify({initial_balance,amount,final_balance}));`;
  const { stdout } = await execute(process.execPath, ['--input-type=module', '-e', expression], { cwd: fixture, timeout: 5000 });
  assert.deepEqual(JSON.parse(stdout), negative);
  const result = await run({ output: stdout, nodeExpression: expression });
  assert.equal(result.exitCode, undefined); assert.deepEqual(result.errors, []); assert.equal(result.receipts.length, 1);
  assert.deepEqual(result.independentExits, [0]);
  const prompt = result.agentCalls[0].at(-1);
  for (const text of ['ONE standalone complete JSON object', 'initial_balance, amount, final_balance', 'negative withdrawal finding', 'no prose or extra output', 'matching the final numeric example', 'exactly cat wallet.mjs', 'cat BUSINESS_RULES.md']) assert.ok(prompt.includes(text), text);
  const config = result.writes.find(write => write.path.endsWith('/config.toml')).body;
  assert.ok(config.includes('model_reasoning_effort = "high"'));
  assert.ok(config.includes('model = "mimo-v2.6-pro"'));
  assert.equal(Object.hasOwn(result.receipts[0], 'capability'), false);
});
test('RUN_CLIENT_SOURCE binds evidence and its transitive imports to selected source', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-selected-source-'));
  const previous = process.env.RUN_CLIENT_SOURCE;
  try {
    await mkdir(join(dir, 'sub2api-spike')); await mkdir(join(dir, 'gateway-spike'));
    for (const name of ['run-client.mjs', 'granted-run.mjs', 'evidence.mjs']) await writeFile(join(dir, 'sub2api-spike', name), await readFile(new URL(`../sub2api-spike/${name}`, import.meta.url)));
    // A distinct transitive validator makes accidental imports of the default
    // source observable. No production predicate or fixture is changed.
    await writeFile(join(dir, 'gateway-spike/evidence.mjs'), 'export function normalizeEvidence() { throw Error("private selected transitive detail"); }');
    process.env.RUN_CLIENT_SOURCE = join(dir, 'sub2api-spike/run-client.mjs');
    const result = await run(); safeFailure(result, 'evidence_agent_contract');
    assert.ok(result.sealed.includes(join(dir, 'sub2api-spike/evidence.mjs')));
    assert.ok(result.sealed.includes(join(dir, 'gateway-spike/evidence.mjs')));
    assert.deepEqual(result.independentExits, [0]);
  } finally {
    if (previous === undefined) delete process.env.RUN_CLIENT_SOURCE; else process.env.RUN_CLIENT_SOURCE = previous;
    await rm(dir, { recursive: true, force: true });
  }
});
