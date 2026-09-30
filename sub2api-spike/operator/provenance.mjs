// Bind normalized operator receipts to the independently reviewed mechanical SHA.
import { readFile, readdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { checkImages } from './check-images.mjs';
export async function harnessDigest(root = '.') {
  const files = [];
  async function walk(dir) { for (const e of await readdir(dir, { withFileTypes: true })) { const p = join(dir,e.name); if (e.isDirectory()) { if (!['issues','evidence'].includes(e.name)) await walk(p); } else if (/\.(mjs|sh|yaml)$/.test(e.name) || e.name === 'broker.config.example.json') files.push(p); } }
  await walk(join(root, 'sub2api-spike')); files.push(join(root, '.github/workflows/sub2api-gateway-spike.yml'));
  const h = createHash('sha256'); for (const path of files.sort()) { h.update(path.replace(`${root}/`, '')); h.update('\0'); h.update(await readFile(path)); h.update('\0'); }
  return h.digest('hex');
}
if (process.argv[1]?.endsWith('/provenance.mjs')) {
  const images = checkImages(process.env);
  const sha = process.argv[2]; if (!/^[a-f0-9]{40}$/.test(sha ?? '')) throw Error('Reviewed exported mechanical git SHA required');
  const receipt = { ...images, harness_git_sha: sha, harness_tree_sha256: await harnessDigest(), source_pin_verified: false, operator_reviewed: true, client_versions: { codex: '0.159.2', claude: '2.1.285' }, limitation: 'Client version fields are expected pins, not execution evidence. Coordinator must add measured container versions and independently source-verified immutable engine digest.' };
  await writeFile(process.argv[3], JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
}
