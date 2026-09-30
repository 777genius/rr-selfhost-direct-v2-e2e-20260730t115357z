import { mkdtemp, mkdir, writeFile, readFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { normalizeEvidence } from './evidence.mjs';
if (Number(process.versions.node.split('.')[0]) !== 24) throw Error('Node 24 required');
const [provider, agent = 'codex'] = process.argv.slice(2);
if (!['mimo', 'openrouter'].includes(provider) || !['codex', 'claude'].includes(agent) || (agent === 'claude' && provider !== 'mimo')) throw Error('Unsupported provider/agent combination');
const broker = 'http://broker:8787';
const home = await mkdtemp(join(tmpdir(), 'gateway-spike-client-'));
const sourceFixture = resolve(dirname(fileURLToPath(import.meta.url)), 'fixture');
const fixture = '/opt/rr-gateway-spike-fixture'; // Operator-pinned read-only snapshot in the disposable runner image.
const env = { PATH: process.env.PATH, LANG: 'C.UTF-8', HOME: home, TMPDIR: home };
let phase = 'fixture', completed = false;
const prompt = 'Review the implementation and business rules in this directory. Actually read wallet.mjs and BUSINESS_RULES.md with tools. For Codex read the implementation in a separate tool call running exactly cat wallet.mjs, then read rules with cat BUSINESS_RULES.md; do not combine the commands. For Claude use Read. Identify material financial correctness issues. Do not modify files. Return only JSON with a findings array. Each finding has file, function, summary, and example containing numeric initial_balance, amount, and final_balance. Use an empty findings array if there are no issues. Choose your own concrete example for each issue and report the actual final_balance produced by the current implementation. For Codex run a local reproduction with tools to verify your example before reporting it.';
function execute(binary, args, onLine = () => {}) {
  return new Promise((resolvePromise, reject) => {
    const p = spawn(binary, args, { cwd: fixture, env, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '', pending = '', diagnostic = '', size = 0;
    const timer = setTimeout(() => { p.kill('SIGTERM'); setTimeout(() => p.kill('SIGKILL'), 5000).unref(); }, 12 * 60 * 1000); timer.unref();
    p.stdout.on('data', b => { size += b.length; if (size > 16 * 1024 * 1024) { p.kill('SIGKILL'); reject(Error('Agent output too large')); return; } output += b; pending += b; const lines = pending.split('\n'); pending = lines.pop(); for (const line of lines) onLine(line); });
    // Retain failures privately in the disposable runner, never in Actions logs/artifacts.
    p.stderr.on('data', b => { if (diagnostic.length < 65536) diagnostic += b.toString().slice(0, 65536 - diagnostic.length); });
    p.on('error', e => { clearTimeout(timer); reject(e); });
    p.on('close', async code => { clearTimeout(timer); if (pending) onLine(pending); if (code !== 0) {
      try { await writeFile(join(home, 'private-events.jsonl'), output, { mode: 0o600 }); await writeFile(join(home, 'private-stderr.txt'), diagnostic, { mode: 0o600 }); } catch {}
      reject(Error('Agent command failed; inspect ephemeral runtime privately'));
    } else resolvePromise(output); });
  });
}
try {
  if (process.getuid() === 0) throw Error('Unprivileged disposable runner required');
  const directory = await stat(fixture);
  if (directory.uid !== 0 || directory.mode & 0o222) throw Error('Fixture directory must be sealed');
  for (const file of ['wallet.mjs', 'BUSINESS_RULES.md']) {
    const info = await stat(join(fixture, file));
    if (info.uid !== 0 || info.mode & 0o222 || !(await readFile(join(fixture, file))).equals(await readFile(join(sourceFixture, file)))) throw Error('Sealed fixture must match checked-out source');
  }
  phase = 'version';
  const version = (await execute(agent, ['--version'])).trim();
  const expected = agent === 'codex' ? '0.159.2' : '2.1.285';
  if (!version.includes(expected)) throw Error('Installed client version does not match pinned canary');
  phase = 'oidc'; const oidcURL = new URL(process.env.ACTIONS_ID_TOKEN_REQUEST_URL);
  if (oidcURL.protocol !== 'https:' || !oidcURL.hostname.endsWith('.actions.githubusercontent.com') || !process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN) throw Error('Missing trusted GitHub OIDC runtime');
  oidcURL.searchParams.set('audience', 'review-router-gateway-spike');
  const oidc = await fetch(oidcURL, { headers: { authorization: `Bearer ${process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN}` }, signal: AbortSignal.timeout(10000), redirect: 'error' });
  if (!oidc.ok) throw Error('GitHub OIDC failed');
  const { value } = await oidc.json();
  phase = 'grant'; const grant = await fetch(`${broker}/grant`, { method: 'POST', headers: { authorization: `Bearer ${value}`, 'content-type': 'application/json' }, body: JSON.stringify({ provider, protocol: agent === 'codex' ? 'responses' : 'messages' }), signal: AbortSignal.timeout(15000), redirect: 'error' });
  if (!grant.ok) throw Error('Broker grant failed');
  const { capability, model } = await grant.json();
  if (!/^[A-Za-z0-9_-]{43}$/.test(capability) || typeof model !== 'string') throw Error('Invalid grant response');
  console.log(`::add-mask::${capability}`);
  const events = []; const collect = line => { try { events.push(JSON.parse(line)); } catch { /* Non-JSON diagnostic is never evidence. */ } };
  phase = 'agent'; let raw, review;
  if (agent === 'codex') {
    env.CODEX_HOME = join(home, 'codex'); env.SPIKE_RUN_CAPABILITY = capability; await mkdir(env.CODEX_HOME);
    const config = `model = ${JSON.stringify(model)}\nmodel_provider = "spike"\nweb_search = "disabled"\n[model_providers.spike]\nname = "Run gateway"\nbase_url = "${broker}/openai/v1"\nenv_key = "SPIKE_RUN_CAPABILITY"\nwire_api = "responses"\nrequires_openai_auth = false\nrequest_max_retries = 0\nstream_max_retries = 0\nsupports_websockets = false\n`;
    await writeFile(join(env.CODEX_HOME, 'config.toml'), config, { mode: 0o600 });
    // Outer disposable container is the sandbox; fixture is root-owned and immutable to this UID.
    raw = await execute('codex', ['--ask-for-approval', 'never', 'exec', '--sandbox', 'danger-full-access', '--skip-git-repo-check', '--json', '--output-last-message', join(home, 'review.txt'), prompt], collect);
    review = await readFile(join(home, 'review.txt'), 'utf8');
  } else {
    env.CLAUDE_CONFIG_DIR = join(home, 'claude'); await mkdir(env.CLAUDE_CONFIG_DIR);
    Object.assign(env, { ANTHROPIC_BASE_URL: `${broker}/anthropic`, ANTHROPIC_AUTH_TOKEN: capability, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1' });
    // Read-only tool allowlist; CLI/protocol compatibility still needs an operator canary.
    raw = await execute('claude', ['--print', '--verbose', '--output-format', 'stream-json', '--model', model, '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', prompt], collect);
    review = events.findLast(e => e.type === 'result')?.result ?? '';
    await writeFile(join(home, 'review.txt'), review, { mode: 0o600 });
  }
  await writeFile(join(home, 'events.jsonl'), raw, { mode: 0o600 });
  phase = 'evidence'; const evidence = { ...normalizeEvidence(agent, events, review, provider), client_version: expected, transport: agent === 'codex' ? 'responses' : 'messages' };
  const output = resolve('..', 'evidence'); // Fixed workspace sibling when workflow uses gateway-spike cwd.
  await mkdir(output, { recursive: true }); await writeFile(join(output, 'result.json'), JSON.stringify(evidence, null, 2) + '\n');
  console.log('Verified tool read and financial finding; normalized evidence saved.');
  completed = true;
} catch {
  console.error(`Spike failed at ${phase}; no raw transcript published. Operator must inspect private disposable runtime before retry.`); process.exitCode = 1;
} finally { if (completed) await rm(home, { recursive: true, force: true }); }
