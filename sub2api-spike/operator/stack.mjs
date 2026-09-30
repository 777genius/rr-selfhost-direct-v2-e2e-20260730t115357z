// TRUSTED coordinator only; finite own-project operations. NEVER executed by worker.
import { spawnSync } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { checkImages } from './check-images.mjs';
checkImages(process.env);
const compose = resolve('sub2api-spike/operator/compose.yaml');
const prefix = ['compose', '--project-name', 'rr-sub2-spike-20260930', '--file', compose];
const command = process.argv[2];
const operations = {
  'up-synthetic': ['--profile', 'synthetic', 'up', '-d', 'postgres', 'redis', 'sub2api', 'mock-a', 'mock-b'],
  'up-broker': ['up', '-d', 'broker'],
  'restart-engine': ['restart', 'sub2api'],
  'restart-broker': ['restart', 'broker'],
  'stop-postgres': ['stop', 'postgres'],
  'start-postgres': ['start', 'postgres'],
  'stop-redis': ['stop', 'redis'],
  'start-redis': ['start', 'redis'],
  'inventory': ['ps', '--format', 'json'],
  'teardown': ['--profile', 'synthetic', 'down', '--volumes', '--remove-orphans']
};
if (!operations[command]) throw Error('Unknown owned operation');
const config = spawnSync('docker', [...prefix, '--profile', 'synthetic', 'config', '--format', 'json'], { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
if (config.status !== 0) throw Error('OWN_CONFIG_INVALID');
const c = JSON.parse(config.stdout); if (c.name !== 'rr-sub2-spike-20260930') throw Error('WRONG_PROJECT');
for (const s of Object.values(c.services)) {
  if (s.ports?.length || s.privileged || s.network_mode === 'host' || s.pid === 'host' || s.volumes?.some(v => /docker\.sock|\/\.ssh|\/\.aws|\/\.codex|\/\.claude/.test(v.source ?? ''))) throw Error('UNSAFE_OWN_COMPOSE');
}
for (const resource of [...Object.values(c.networks), ...Object.values(c.volumes)]) if (!resource.name.startsWith('rr-sub2-spike-20260930-') || resource.external) throw Error('UNOWNED_RESOURCE');
const started = Date.now(); const r = spawnSync('docker', [...prefix, ...operations[command]], { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
// Captured raw config/process output stays private; only bounded metadata receipt escapes.
const receipt = { schema: 1, evidence_kind: 'synthetic-container', operation: command, exit_code: r.status, duration_ms: Date.now() - started, no_published_ports_in_config: true, limitation: 'Mechanical owned-stack operation only; does not prove gateway recovery, custody or public-network isolation.' };
await writeFile(process.argv[3] ?? `/tmp/rr-sub2-spike-20260930-${command}.json`, JSON.stringify(receipt, null, 2) + '\n'); if (r.status !== 0) process.exitCode = 1;
