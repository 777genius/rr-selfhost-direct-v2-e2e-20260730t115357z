import { mkdir, writeFile, readFile, rm, chown } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { bindGrantedRun } from './granted-run.mjs';
import { requireControl, readControlInput, privateControlHome, agentHome, cleanAgentEnv, spawnAgent, safeAgentFile, verifyFixture, verifyTools, agentIdentity, sealedPath } from './runner-isolation.mjs';
import { financialEvidence, parseFindingDocument, codexNumericEvidence } from './evidence.mjs';
if (Number(process.versions.node.split('.')[0]) !== 24) throw Error('Node 24 required');
requireControl();
const runtime = await readControlInput();
if (runtime.workflowSHA !== (await readFile('/opt/rr-sub2-harness/reviewed-workflow.sha', 'utf8')).trim()) throw Error('Reviewed workflow SHA mismatch');
const { provider, agent } = runtime;
const broker = 'http://broker:8787';
let controlHome, home;
const fixture = '/opt/rr-gateway-spike-fixture';
let env;
let phase = 'fixture', completed = false;
const prompt = 'Review the implementation and business rules in this directory. Actually read wallet.mjs and BUSINESS_RULES.md with tools. For Codex read the implementation in a separate tool call running exactly cat wallet.mjs, then read rules with cat BUSINESS_RULES.md; do not combine the commands. For Claude use Read. Identify material financial correctness issues. Do not modify files. Return only JSON with a findings array. Each finding has file, function, summary, and example containing numeric initial_balance, amount, and final_balance. Use an empty findings array if there are no issues. Choose your own concrete example for each issue and report the actual final_balance produced by the current implementation. For Codex run a local reproduction with tools using node to import withdraw from ./wallet.mjs, and emit JSON with numeric initial_balance, amount, final_balance; verify your example before reporting it.';
const execute = (binary, args, onLine = () => {}) => spawnAgent(binary, args, { cwd: fixture, env, onLine });
async function configDirectory(path) { await mkdir(path, { mode: 0o700 }); await chown(path, agentIdentity.uid, agentIdentity.gid); }
try {
  phase = 'oidc'; const oidcURL = new URL(runtime.oidcURL);
  if (oidcURL.protocol !== 'https:' || !oidcURL.hostname.endsWith('.actions.githubusercontent.com') || !runtime.oidcToken) throw Error('Missing trusted GitHub OIDC runtime');
  oidcURL.searchParams.set('audience', 'review-router-gateway-spike');
  const oidc = await fetch(oidcURL, { headers: { authorization: `Bearer ${runtime.oidcToken}` }, signal: AbortSignal.timeout(10000), redirect: 'error' });
  if (!oidc.ok) throw Error('GitHub OIDC failed');
  const { value } = await oidc.json();
  phase = 'grant'; const grant = await fetch(`${broker}/grant`, { method: 'POST', headers: { authorization: `Bearer ${value}`, 'content-type': 'application/json' }, body: JSON.stringify({ provider, protocol: agent === 'codex' ? 'responses' : 'messages' }), signal: AbortSignal.timeout(15000), redirect: 'error' });
  if (!grant.ok) throw Error('Broker grant failed');
  const granted = await grant.json();
  const identity = bindGrantedRun(granted, { runID: runtime.runID, attempt: runtime.runAttempt, workflowSHA: runtime.workflowSHA, provider, agent });
  const { capability, model } = granted;
  if (!/^[A-Za-z0-9_-]{43}$/.test(capability) || typeof model !== 'string') throw Error('Invalid grant response');
  phase = 'fixture';
  // Fixed launcher verifies harness.sha256 before Node imports; also deny writable
  // installed paths here. Seal the binder and all transitive imports in that manifest.
  for (const path of ['./run-client.mjs', './granted-run.mjs', './runner-isolation.mjs', './evidence.mjs', '../gateway-spike/evidence.mjs']) await sealedPath(fileURLToPath(new URL(path, import.meta.url)));
  controlHome = await privateControlHome(); home = await agentHome(controlHome); env = cleanAgentEnv(home);
  await verifyFixture(fixture); await verifyTools();
  phase = 'version';
  const version = (await execute(agent, ['--version'])).trim();
  const expected = agent === 'codex' ? '0.159.2' : '2.1.285';
  if (!(agent === 'codex' ? /^codex-cli 0\.159\.2$/ : /^2\.1\.285 \(Claude Code\)$/).test(version)) throw Error('Installed client version does not match pinned canary');

  const events = []; const collect = line => { try { events.push(JSON.parse(line)); } catch { /* Non-JSON diagnostic is never evidence. */ } };
  phase = 'agent'; let raw, review;
  if (agent === 'codex') {
    env.CODEX_HOME = join(home, 'codex'); env.SPIKE_RUN_CAPABILITY = capability; await configDirectory(env.CODEX_HOME);
    const thinking = provider === 'mimo' ? 'model_reasoning_effort = \"high\"\n' : '';
    const config = `${thinking}model = ${JSON.stringify(model)}\nmodel_provider = "spike"\nweb_search = "disabled"\n[model_providers.spike]\nname = "Run gateway"\nbase_url = "${broker}/v1"\nenv_key = "SPIKE_RUN_CAPABILITY"\nwire_api = "responses"\nrequires_openai_auth = false\nrequest_max_retries = 0\nstream_max_retries = 0\nsupports_websockets = false\n`;
    await writeFile(join(env.CODEX_HOME, 'config.toml'), config, { mode: 0o600 });
    await chown(join(env.CODEX_HOME, 'config.toml'), agentIdentity.uid, agentIdentity.gid);
    // Outer disposable container is the sandbox; fixture is root-owned and immutable to this UID.
    raw = await execute('codex', ['--ask-for-approval', 'never', 'exec', '--sandbox', 'danger-full-access', '--skip-git-repo-check', '--json', '--output-last-message', join(home, 'review.txt'), prompt], collect);
    review = await safeAgentFile(join(home, 'review.txt'));
  } else {
    env.CLAUDE_CONFIG_DIR = join(home, 'claude'); await configDirectory(env.CLAUDE_CONFIG_DIR);
    Object.assign(env, { ANTHROPIC_BASE_URL: `${broker}/anthropic`, ANTHROPIC_AUTH_TOKEN: capability, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1' });
    // Read-only tool allowlist; CLI/protocol compatibility still needs an operator canary.
    raw = await execute('claude', ['--print', '--verbose', '--output-format', 'stream-json', '--permission-mode', 'default', '--model', model, '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--', prompt], collect);
    review = events.findLast(e => e.type === 'result')?.result ?? '';

  }
  // Transcripts stay in memory; no capability-bearing raw artifact is persisted.
  phase = 'evidence'; let parsed; try { parsed = parseFindingDocument(review); } catch { throw Error('Malformed final JSON'); }
  const numeric = parsed.findings?.find(f => f.file === 'wallet.mjs' && f.function === 'withdraw' && f.example?.amount < 0)?.example;
  if (!numeric) throw Error('Missing numeric example');
  const expression = `import { withdraw } from './wallet.mjs'; const x = ${JSON.stringify(numeric)}; const a = {balance:x.initial_balance}; const out=withdraw(a,x.amount); if(out.balance!==x.final_balance || a.balance!==x.final_balance) process.exit(1); console.log(JSON.stringify({reproduced:true}));`;
  const reproduction = await execute('node', ['--input-type=module', '-e', expression]);
  if (JSON.parse(reproduction).reproduced !== true) throw Error('Independent reproduction failed');
  if (agent === 'codex' && !events.some(e => codexNumericEvidence(e, numeric))) throw Error('Codex did not prove own numeric local reproduction');
  const evidence = { ...financialEvidence(agent, events, review, provider), id: agent === 'claude' ? 'A03' : provider === 'mimo' ? 'A01' : 'A02', evidence_kind: 'real-Actions', independent_numeric_reproduction: true, workflow_sha: identity.workflowSHA, run_id: identity.runID, run_attempt: identity.attempt, provider: identity.provider, agent, node: process.version, client_version: expected, transport: identity.protocol };
  // Only positive-projected evidence crosses back to the uid1001 workflow.
  process.stdout.write(JSON.stringify(evidence) + '\n');
  completed = true;
} catch {
  console.error(`Spike failed at ${phase}; inspect effects privately before retry.`); process.exitCode = 1;
} finally { if (completed) await rm(controlHome, { recursive: true, force: true }); }
