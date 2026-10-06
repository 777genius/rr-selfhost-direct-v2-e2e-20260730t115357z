// Independent operator check. Run directly as trusted root in the derived
// disposable image, never through the workflow's fixed canary sudo entry.
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { requireControl, agentHome, spawnAgent, cleanAgentEnv, trustedPATH, agentIdentity, verifyFixture, verifyTools, safeAgentFile } from '../runner-isolation.mjs';
requireControl();
const control = await mkdtemp('/tmp/rr-sub2-containment-');
let receipt = { schema: 1, evidence_kind: 'operator-uid-containment', status: 'FAIL' };
try {
  await verifyFixture('/opt/rr-gateway-spike-fixture'); await verifyTools();
  const sentinel = join(control, 'sentinel');
  await writeFile(sentinel, randomBytes(32), { mode: 0o600 });
  const home = await agentHome(control);
  // Paths and PID are harmless test inputs; sentinel content is never exported.
  const probe = `
    const fs = require('node:fs');
    const denied = path => { try { fs.readFileSync(path); return false; } catch(e) { return ['EACCES','EPERM'].includes(e.code); } };
    const groups = process.getgroups();
    const uid = process.getuid(), gid = process.getgid();
    const fixture = fs.readFileSync('wallet.mjs','utf8');
    fs.writeFileSync(process.env.HOME + '/tool-output', 'normal tool IO');
    fs.symlinkSync(${JSON.stringify(sentinel)}, process.env.HOME + '/hostile-review');
    console.log(JSON.stringify({uid, gid, groups, parent_environment_denied: denied('/proc/${process.pid}/environ'), sentinel_denied: denied(${JSON.stringify(sentinel)}), tool_io: fixture.includes('withdraw') && fs.readFileSync(process.env.HOME+'/tool-output','utf8')==='normal tool IO', clean_env: Object.keys(process.env).sort()}));
  `;
  const result = JSON.parse(await spawnAgent('node', ['-e', probe], { cwd: '/opt/rr-gateway-spike-fixture', env: cleanAgentEnv(home), timeoutMs: 10000 }));
  if (result.uid !== agentIdentity.uid || result.gid !== agentIdentity.gid || result.groups.some(g => g !== agentIdentity.gid) || !result.parent_environment_denied || !result.sentinel_denied || !result.tool_io || JSON.stringify(result.clean_env) !== JSON.stringify(['HOME','LANG','PATH','TMPDIR'])) throw Error('Containment oracle failed');
  if (await safeAgentFile(join(home, 'tool-output')) !== 'normal tool IO') throw Error('Control read of normal tool IO failed');
  let symlinkRejected = false;
  try { await safeAgentFile(join(home, 'hostile-review')); } catch { symlinkRejected = true; }
  if (!symlinkRejected) throw Error('Privileged output reader followed a hostile symlink');
  // Independent hostile real-child negative control must detect same-UID custody.
  const { spawn } = await import('node:child_process');
  const sameUID = await new Promise((resolve, reject) => {
    const p = spawn('/usr/local/bin/node', ['-e', `const fs=require('node:fs'); fs.readFileSync('/proc/${process.pid}/environ'); fs.readFileSync(${JSON.stringify(sentinel)}); console.log('readable');`], { env: { PATH: trustedPATH }, stdio: ['ignore','pipe','ignore'] });
    let out = ''; p.stdout.on('data', b => out += b); p.on('error', reject); p.on('close', code => resolve(code === 0 && out.trim() === 'readable'));
  });
  if (!sameUID) throw Error('Negative control did not reproduce R07');
  receipt = { ...receipt, status: 'PASS', ...result, same_uid_negative_control_readable: true, fixture_pinned: true, hostile_output_symlink_rejected: true };
} catch { process.exitCode = 1; }
finally {
  await rm(control, { recursive: true, force: true });
  // stdout contains booleans/UIDs/environment NAMES only. No runtime token values.
  process.stdout.write(JSON.stringify(receipt) + '\n');
}
