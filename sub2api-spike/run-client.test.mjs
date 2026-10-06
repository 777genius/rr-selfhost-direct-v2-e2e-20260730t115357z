// Execute the actual top-level caller with in-process I/O substitutes. No root,
// auth home, agent binary, socket or provider is used; synthetic events are tests.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
const sha = 'b'.repeat(40);
const runtime = { runID: '123', runAttempt: '2', workflowSHA: sha, provider: 'mimo', agent: 'codex', oidcURL: 'https://example.actions.githubusercontent.com/token', oidcToken: 'synthetic' };
const grant = { runID: '123', attempt: '2', workflowSHA: sha, provider: 'mimo', protocol: 'responses', model: 'mimo-v2.6-pro', capability: 's'.repeat(43) };
const document = { findings: [{ file: 'wallet.mjs', function: 'withdraw', summary: 'Negative withdrawal increases balance', example: { initial_balance: 50, amount: -7, final_balance: 57 } }] };
const command = (cmd, output) => ({ type: 'item.completed', item: { type: 'command_execution', command: cmd, aggregated_output: output, exit_code: 0, status: 'completed' } });
async function run({ override = {}, selection = {}, terminal = true, finding = document, sealDenied = false } = {}) {
  const effects = [], receipts = [], files = [], key = randomUUID();
  const source = await readFile(process.env.CONSUMER_CLIENT_SOURCE ?? new URL('./run-client.mjs', import.meta.url), 'utf8');
  const wallet = await readFile(new URL('./fixture/wallet.mjs', import.meta.url), 'utf8');
  const rules = await readFile(new URL('./fixture/BUSINESS_RULES.md', import.meta.url), 'utf8');
  const p = { versions: { node: '24.21.0' }, version: 'v24.21.0', stdout: { write: text => receipts.push(JSON.parse(text)) } };
  const io = {
    mkdir: async () => effects.push('mkdir'), chown: async () => {}, rm: async () => {},
    writeFile: async (path, body) => { files.push({ path, body }); effects.push('write'); },
    readFile: async () => sha,
  };
  const runner = {
    requireControl: () => {}, readControlInput: async () => ({ ...runtime, ...selection }),
    privateControlHome: async () => { effects.push('control-home'); return '/synthetic/control'; },
    agentHome: async () => { effects.push('agent-home'); return '/synthetic/agent'; },
    cleanAgentEnv: () => ({}), agentIdentity: { uid: 1002, gid: 1002 },
    sealedPath: async () => { if (sealDenied) throw Error('UNSEALED'); }, verifyFixture: async () => {}, verifyTools: async () => {},
    safeAgentFile: async () => JSON.stringify(finding),
    spawnAgent: async (binary, args, options) => {
      effects.push(`spawn:${binary}:${args[0]}`);
      if (args[0] === '--version') return binary === 'claude' ? '2.1.285 (Claude Code)' : 'codex-cli 0.159.2';
      if (binary === 'node') return '{"reproduced":true}';
      if (binary === 'claude') {
        for (const [id, path, content] of [['w', 'wallet.mjs', wallet], ['r', 'BUSINESS_RULES.md', rules]]) {
          options.onLine(JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', id, name: 'Read', input: { file_path: path } }] } }));
          options.onLine(JSON.stringify({ type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: id, content }] } }));
        }
        options.onLine(JSON.stringify({ type: 'result', subtype: terminal ? 'success' : 'error', is_error: !terminal, result: JSON.stringify(finding) }));
        return '';
      }
      for (const event of [command('cat wallet.mjs', wallet), command('cat BUSINESS_RULES.md', rules),
        command('node -e "import withdraw from wallet.mjs"', JSON.stringify(document.findings[0].example)),
        ...(terminal ? [{ type: 'turn.completed' }] : [{ type: 'turn.failed' }])]) options.onLine(JSON.stringify(event));
      return '';
    }
  };
  globalThis[key] = { ...io, ...runner, process: p, console: { error: () => {} }, fetch: async url => ({ ok: true, json: async () => String(url).includes('/grant') ? { ...grant, ...override } : { value: 'synthetic' } }) };
  let injected = `const { ${Object.keys(globalThis[key]).join(', ')} } = globalThis[${JSON.stringify(key)}];\n`;
  for (const line of source.split('\n')) {
    if (/^import .*from '(node:fs\/promises|\.\/runner-isolation.mjs)'/.test(line)) continue;
    injected += line.replaceAll('import.meta.url', JSON.stringify(new URL('./run-client.mjs', import.meta.url).href)).replace(/from '(\.\/[^']+)'/g, (_, path) => `from '${new URL(path, import.meta.url).href}'`) + '\n';
  }
  try { await import('data:text/javascript;base64,' + Buffer.from(injected).toString('base64')); }
  finally { delete globalThis[key]; }
  return { effects, receipts, files, exitCode: p.exitCode };
}
// Prior caller ignores all five returned identity fields and runs --version first.
test('BR04 integrated mismatches deny before any agent effects and receipt', async () => {
  for (const override of [{ runID: '124' }, { attempt: '3' }, { workflowSHA: 'c'.repeat(40) }, { provider: 'openrouter' }, { protocol: 'messages' }, { attempt: 2 }, { runID: undefined }]) {
    const r = await run({ override });
    assert.equal(r.exitCode, 1);
    assert.deepEqual(r.effects, []);
    assert.deepEqual(r.receipts, []);
  }
  const r = await run({ selection: { agent: 'claude' } });
  assert.deepEqual(r.effects, []); assert.deepEqual(r.receipts, []); assert.equal(r.exitCode, 1);
});
test('BR04 integrated valid binding projects exact identity and preserves high reasoning', async () => {
  const r = await run(); assert.equal(r.exitCode, undefined); assert.equal(r.receipts.length, 1);
  const receipt = r.receipts[0];
  for (const [k, value] of Object.entries({ run_id: '123', run_attempt: '2', workflow_sha: sha, provider: 'mimo', agent: 'codex', transport: 'responses', result: 'passed', tool_read_verified: true, rules_read_verified: true, terminal_verified: true, independent_numeric_reproduction: true })) assert.equal(receipt[k], value);
  assert.ok(r.files.some(x => x.path.endsWith('/config.toml') && x.body.includes('model_reasoning_effort = "high"')));
  assert.equal(Object.hasOwn(receipt, 'capability'), false);
});
test('BR04 model metadata cannot authorize mismatched run', async () => {
  const r = await run({ override: { runID: '124', model: 'mimo-v2.6-pro', verified: true, identity: runtime } });
  assert.equal(r.exitCode, 1); assert.deepEqual(r.effects, []); assert.deepEqual(r.receipts, []);
});
test('BR04 receipt still requires successful terminal and numeric financial finding', async () => {
  for (const options of [{ terminal: false }, { finding: { findings: [] } }, { finding: { findings: [{ ...document.findings[0], example: { initial_balance: 50, amount: -7, final_balance: 51 } }] } }]) {
    const r = await run(options); assert.equal(r.exitCode, 1); assert.deepEqual(r.receipts, []);
  }
});

// Run the workflow's actual validator; mutations represent a misbound child receipt.
test('BR04 workflow rejects every mismatched receipt before publication', async () => {
  const { runInNewContext } = await import('node:vm');
  const workflow = await readFile(process.env.CONSUMER_WORKFLOW_SOURCE ?? new URL('../.github/workflows/sub2api-gateway-spike.yml', import.meta.url), 'utf8');
  const code = workflow.slice(workflow.indexOf('const result = JSON.parse(out);'), workflow.indexOf("await mkdir('evidence'"));
  const valid = { result: 'passed', run_id: '123', run_attempt: '2', workflow_sha: sha, provider: 'mimo', agent: 'codex', transport: 'responses', evidence_kind: 'real-Actions', tool_read_verified: true, rules_read_verified: true, terminal_verified: true, independent_numeric_reproduction: true };
  const validate = r => runInNewContext(code, { out: JSON.stringify(r), input: runtime });
  validate(valid);
  for (const [key, value] of Object.entries({ run_id: '124', run_attempt: '3', workflow_sha: 'c'.repeat(40), provider: 'openrouter', agent: 'claude', transport: 'messages', tool_read_verified: false, rules_read_verified: false, terminal_verified: false, independent_numeric_reproduction: false })) assert.throws(() => validate({ ...valid, [key]: value }));
});


test('BR04 caller projects both other supported native mappings', async () => {
  for (const [provider, agent, protocol, model] of [['openrouter', 'codex', 'responses', 'openai/gpt-4.1'], ['mimo', 'claude', 'messages', 'mimo-v2.6-pro']]) {
    const r = await run({ selection: { provider, agent }, override: { provider, protocol, model } });
    assert.equal(r.exitCode, undefined); assert.equal(r.receipts.length, 1);
    assert.equal(r.receipts[0].provider, provider); assert.equal(r.receipts[0].agent, agent); assert.equal(r.receipts[0].transport, protocol);
    assert.equal(r.receipts[0].run_id, '123'); assert.equal(r.receipts[0].run_attempt, '2'); assert.equal(r.receipts[0].workflow_sha, sha);
  }
});
test('BR04 unsealed import path aborts before agent effects and receipt', async () => {
  const r = await run({ sealDenied: true }); assert.equal(r.exitCode, 1); assert.deepEqual(r.effects, []); assert.deepEqual(r.receipts, []);
});
