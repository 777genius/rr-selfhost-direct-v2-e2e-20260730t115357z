// Coordinator only; the worker never reads a bearer file or runs this script.
import { randomBytes } from 'node:crypto';
import { mkdir, readFile } from 'node:fs/promises';
import { save, validateConfig } from './common.mjs';
try {
  const [deploymentPath, bearerPath] = process.argv.slice(2);
  if (deploymentPath !== '/private/deployed.json' || bearerPath !== '/private/admin-bearer') throw Error();
  const d = JSON.parse(await readFile(deploymentPath, 'utf8'));
  const { source_sha, image, instance, variant, patch_sha256, source_manifest_sha256, cgroup_limit_bytes } = d;
  const random = () => randomBytes(24).toString('hex');
  const c = validateConfig({ run_id: `transport-${randomBytes(6).toString('hex')}`, admin_bearer: (await readFile(bearerPath, 'utf8')).trim(),
    control_token: random(), sentinels: { responses: `rr-synthetic-${random()}`, messages: `rr-synthetic-${random()}` },
    mock_url: 'http://mock:8099', engine_url: 'http://sub2api:8080',
    deployment: { source_sha, image, instance, variant, patch_sha256, source_manifest_sha256, cgroup_limit_bytes } });
  await mkdir('/private', { recursive: true, mode: 0o700 });
  await save('/private/lab.json', c, true);
} catch { process.stderr.write('PRIVATE_LAB_INIT_FAILED\n'); process.exitCode = 1; }
