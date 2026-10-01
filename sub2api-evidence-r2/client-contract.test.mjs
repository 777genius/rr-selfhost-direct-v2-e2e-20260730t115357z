// Local caller contract: synthetic agent I/O, real independent Node reproduction.
// This is not a coordinator/container/provider E2E or a real-Actions receipt.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
const execute = promisify(execFile);
const clientURL = new URL('../sub2api-spike/run-client.mjs', import.meta.url);
const fixture = fileURLToPath(new URL('../sub2api-spike/fixture/', import.meta.url));
const negative = { initial_balance: 100, amount: -10, final_balance: 110 };
const fractional = { initial_balance: 100, amount: 0.5, final_balance: 99.5 };
const document = { findings: [negative, fractional].map(example => ({ file: 'wallet.mjs', function: 'withdraw', summary: 'Invalid withdrawal is accepted', example })) };
const nodeExpression = 'import { withdraw } from "./wallet.mjs"; const examples = [{initial_balance:100,amount:-10},{initial_balance:100,amount:0.5}]; console.log(JSON.stringify(examples.map(({initial_balance,amount}) => ({initial_balance,amount,final_balance:withdraw({balance:initial_balance},amount).balance}))));';
const command = (cmd, output) => ({ type: 'item.completed', item: { type: 'command_execution', command: cmd, aggregated_output: output, exit_code: 0, status: 'completed' } });
async function run(options = {}) {
  const source = await readFile(process.env.RUN_CLIENT_SOURCE ?? clientURL, 'utf8');
  const wallet = await readFile(new URL('../sub2api-spike/fixture/wallet.mjs', import.meta.url), 'utf8');
  const rules = await readFile(new URL('../sub2api-spike/fixture/BUSINESS_RULES.md', import.meta.url), 'utf8');
  const sha = 'b'.repeat(40), receipts = [], sealed = [], effects = [], errors = [], key = randomUUID();
  const events = options.events ?? [command('cat wallet.mjs', wallet), command('cat BUSINESS_RULES.md', rules),
    command(`node --input-type=module -e '${nodeExpression}'`, options.output ?? JSON.stringify([negative, fractional])), { type: 'turn.completed' }];
  const p = { versions: { node: '24.21.0' }, version: process.version, stdout: { write: value => receipts.push(JSON.parse(value)) } };
  const io = {
    process: p, console: { error: message => errors.push(message) }, mkdir: async () => {}, chown: async () => {}, rm: async () => {}, writeFile: async () => {}, readFile: async () => sha,
    requireControl: () => {}, readControlInput: async () => ({ runID: '123', runAttempt: '2', workflowSHA: sha, provider: 'mimo', agent: 'codex', oidcURL: 'https://example.actions.githubusercontent.com/token', oidcToken: 'synthetic' }),
    privateControlHome: async () => '/synthetic/control', agentHome: async () => '/synthetic/agent', cleanAgentEnv: () => ({}), agentIdentity: { uid: 1002, gid: 1002 },
    sealedPath: async path => { sealed.push(path); if (options.sealDenied) throw Error('unsealed'); }, verifyFixture: async () => {}, verifyTools: async () => {},
    safeAgentFile: async () => options.review ?? JSON.stringify(document),
    fetch: async url => ({ ok: true, json: async () => String(url).includes('/grant') ? { runID: '123', attempt: '2', workflowSHA: sha, provider: 'mimo', protocol: 'responses', model: 'mimo-v2.6-pro', capability: 's'.repeat(43) } : { value: 'synthetic' } }),
    spawnAgent: async (binary, args, { onLine }) => {
      effects.push(binary);
      if (args[0] === '--version') return 'codex-cli 0.159.2';
      if (binary === 'node') return (await execute(process.execPath, args, { cwd: fixture, timeout: 5000 })).stdout;
      for (const event of events) onLine(JSON.stringify(event));
      if (options.agentFailed) throw Error('agent failed');
      return '';
    },
  };
  globalThis[key] = io;
  let injected = `const { ${Object.keys(io).join(', ')} } = globalThis[${JSON.stringify(key)}];\n`;
  for (const line of source.split('\n')) {
    if (/^import .*from '(node:fs\/promises|\.\/runner-isolation.mjs)'/.test(line)) continue;
    const relocated = line.startsWith('import ') ? line.replace(/from '(\.\/[^']+)'/g, (_, path) => `from '${new URL(path, clientURL).href}'`) : line;
    injected += relocated.replaceAll('import.meta.url', JSON.stringify(clientURL.href)) + '\n';
  }
  try { await import('data:text/javascript;base64,' + Buffer.from(injected).toString('base64')); }
  finally { delete globalThis[key]; }
  return { receipts, sealed, effects, errors, exitCode: p.exitCode, events };
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
