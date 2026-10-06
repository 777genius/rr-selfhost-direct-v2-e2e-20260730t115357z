import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';
import { cleanAgentEnv, requireControl, readControlInput, agentIdentity } from './runner-isolation.mjs';
// Red oracle: the old same-UID caller is accepted as trusted control.
test('uid1001 Actions service and agent cannot serve as control parent', () => {
  assert.throws(() => requireControl({ uid: 1001, gid: 1001 }));
  assert.throws(() => requireControl(agentIdentity));
  assert.throws(() => requireControl({ uid: 0, gid: 1001 }));
  assert.doesNotThrow(() => requireControl({ uid: 0, gid: 0 }));
});
// Red oracle: ambient OIDC/Actions/provider keys enter the actual spawn env
// builder, or a caller widens it through the explicit child configuration.
test('clean child environment rejects control tokens and arbitrary overrides', () => {
  const old = process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN;
  process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN = 'synthetic-oidc';
  try {
    const env = cleanAgentEnv('/agent', { SPIKE_RUN_CAPABILITY: 'synthetic-run-only' });
    assert.deepEqual(Object.keys(env).sort(), ['HOME', 'LANG', 'PATH', 'SPIKE_RUN_CAPABILITY', 'TMPDIR']);
    for (const key of ['ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'GITHUB_TOKEN', 'NODE_OPTIONS', 'PATH', 'HOME', 'OPENAI_API_KEY']) assert.throws(() => cleanAgentEnv('/agent', { [key]: 'synthetic-control' }));
  } finally { if (old === undefined) delete process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN; else process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN = old; }
});
const valid = { provider: 'mimo', agent: 'codex', oidcURL: 'https://test.actions.githubusercontent.com/token', oidcToken: 'synthetic-only', workflowSHA: 'a'.repeat(40), runID: '1', runAttempt: '1' };
const parse = value => readControlInput(Readable.from([Buffer.from(JSON.stringify(value))]));
// Red oracle: the fixed launcher accepts code/path/env input or malformed trust
// metadata that could redirect OIDC bearer delivery away from GitHub.
test('fixed control contract validates selectors and token destination', async () => {
  assert.deepEqual(await parse(valid), valid);
  for (const override of [{ command: 'arbitrary' }, { uid: '0' }, { oidcURL: 'https://evil.example/token' }, { oidcURL: 'https://user@test.actions.githubusercontent.com/token' }, { oidcURL: 'https://test.actions.githubusercontent.com:444/token' }, { provider: 'openrouter', agent: 'claude' }, { workflowSHA: 'main' }, { runID: '0' }]) await assert.rejects(parse({ ...valid, ...override }));
});
// Red oracle: unbounded stdin lets a runner feed arbitrary control workload.
test('fixed control input has a hard byte limit', async () => {
  await assert.rejects(readControlInput(Readable.from([Buffer.alloc(16385)])), /Control input limit/);
});
