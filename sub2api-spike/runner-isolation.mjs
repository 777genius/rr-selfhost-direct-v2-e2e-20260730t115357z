import { spawn } from 'node:child_process';
import { constants } from 'node:fs';
import { open, lstat, realpath, mkdir, chown, mkdtemp, readFile } from 'node:fs/promises';
import { join, dirname, resolve } from 'node:path';
import { createHash } from 'node:crypto';
export const agentIdentity = Object.freeze({ uid: 1002, gid: 1002 });
export const trustedPATH = '/usr/local/bin:/usr/bin:/bin';
const fixtureHashes = Object.freeze({
  'wallet.mjs': 'c47fcdfb32c95bf1ede68c01a3705084a658ecbd2882ab21ca4e8cc5fc658f71',
  'BUSINESS_RULES.md': '1a9837e5e95ee86f22eb171c7bc9ee1226c55ff859973ad573417feb6aae43a5'
});
export function requireControl(identity = { uid: process.getuid(), gid: process.getgid() }) {
  if (identity.uid !== 0 || identity.gid !== 0) throw Error('Root trusted control launcher required');
}
export async function sealedPath(path) {
  const absolute = resolve(path);
  if (await realpath(absolute) !== absolute) throw Error('Sealed path cannot contain symlinks');
  for (let current = absolute; ; current = dirname(current)) {
    const info = await lstat(current);
    if (info.uid !== 0 || info.mode & 0o022 || info.isSymbolicLink()) throw Error('Root ownership and no group/other writes required');
    if (dirname(current) === current) break;
  }
}
export async function verifyTools() {
  await sealedPath('/usr/local/bin');
  for (const binary of ['node', 'codex', 'claude']) await sealedPath(await realpath(`/usr/local/bin/${binary}`));
}
export async function verifyFixture(fixture) {
  await sealedPath(fixture);
  const directory = await lstat(fixture);
  if (!directory.isDirectory() || directory.mode & 0o222) throw Error('Fixture directory must be sealed');
  for (const [name, hash] of Object.entries(fixtureHashes)) {
    const path = join(fixture, name); await sealedPath(path); const info = await lstat(path);
    if (!info.isFile() || info.mode & 0o222 || createHash('sha256').update(await readFile(path)).digest('hex') !== hash) throw Error('Pinned fixture mismatch');
  }
}
export function cleanAgentEnv(home, extra = {}) {
  const allowed = new Set(['CODEX_HOME', 'SPIKE_RUN_CAPABILITY', 'CLAUDE_CONFIG_DIR', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', 'DISABLE_TELEMETRY', 'DISABLE_ERROR_REPORTING']);
  if (Object.keys(extra).some(k => !allowed.has(k))) throw Error('Agent environment field denied');
  return { PATH: trustedPATH, LANG: 'C.UTF-8', HOME: home, TMPDIR: home, ...extra };
}
export async function agentHome(controlHome) {
  requireControl(); const home = join(controlHome, 'agent');
  // Root container directory must allow traversal but never directory listing.
  const { chmod } = await import('node:fs/promises'); await chmod(controlHome, 0o711);
  await mkdir(home, { mode: 0o700 }); await chown(home, agentIdentity.uid, agentIdentity.gid); return home;
}
export async function privateControlHome() {
  requireControl(); return mkdtemp('/tmp/rr-sub2-control-');
}
export async function safeAgentFile(path, limit = 1024 * 1024) {
  // A model-controlled symlink must never make the root parent read a secret.
  const h = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const s = await h.stat();
    if (!s.isFile() || s.uid !== agentIdentity.uid || s.nlink !== 1 || s.size > limit) throw Error('Invalid agent output file');
    const bytes = Buffer.alloc(limit + 1); const { bytesRead } = await h.read(bytes, 0, bytes.length, 0);
    if (bytesRead > limit) throw Error('Agent output limit'); return bytes.subarray(0, bytesRead).toString('utf8');
  } finally { await h.close(); }
}
export async function spawnAgent(binary, args, { cwd, env, onLine = () => {}, timeoutMs = 720000, limit = 16 * 1024 * 1024 }) {
  requireControl();
  if (!['codex', 'claude', 'node'].includes(binary)) throw Error('Agent executable denied');
  // Root fixed PATH and installed tools must be sealed by the image operator.
  return new Promise((resolvePromise, reject) => {
    const p = spawn(binary, args, { cwd, env, uid: agentIdentity.uid, gid: agentIdentity.gid, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '', pending = '', size = 0, failure;
    const kill = () => { if (p.pid) { try { process.kill(-p.pid, 'SIGKILL'); } catch {} } };
    const timer = setTimeout(() => { failure = Error('Agent timeout'); kill(); }, timeoutMs); timer.unref();
    p.stdout.on('data', b => {
      size += b.length; if (size > limit) { failure = Error('Agent output too large'); kill(); return; }
      output += b; pending += b; const lines = pending.split('\n'); pending = lines.pop();
      try { for (const line of lines) onLine(line); } catch { failure = Error('Agent event rejected'); kill(); }
    });
    // Never print raw agent stderr or command lines, including on failure.
    p.stderr.resume();
    p.on('error', () => { clearTimeout(timer); reject(Error('Agent launch failed')); });
    p.on('close', code => {
      clearTimeout(timer); kill();
      try { if (pending) onLine(pending); } catch { failure = Error('Agent event rejected'); }
      if (failure || code !== 0) reject(failure ?? Error('Agent command failed')); else resolvePromise(output);
    });
  });
}
export async function readControlInput(stream = process.stdin) {
  let n = 0; const chunks = [];
  for await (const chunk of stream) { n += chunk.length; if (n > 16384) throw Error('Control input limit'); chunks.push(chunk); }
  const input = JSON.parse(Buffer.concat(chunks));
  const keys = ['provider', 'agent', 'oidcURL', 'oidcToken', 'workflowSHA', 'runID', 'runAttempt'];
  if (!input || Object.keys(input).some(k => !keys.includes(k)) || keys.some(k => typeof input[k] !== 'string')) throw Error('Control input fields');
  if (!['mimo', 'openrouter'].includes(input.provider) || !['codex', 'claude'].includes(input.agent) || input.agent === 'claude' && input.provider !== 'mimo') throw Error('Unsupported provider/agent');
  const url = new URL(input.oidcURL);
  if (url.protocol !== 'https:' || !url.hostname.endsWith('.actions.githubusercontent.com') || url.port || url.username || url.password || url.hash || !input.oidcToken || !/^[a-f0-9]{40}$/.test(input.workflowSHA) || !/^[1-9][0-9]*$/.test(input.runID) || !/^[1-9][0-9]*$/.test(input.runAttempt)) throw Error('Invalid trusted runtime');
  return input;
}
