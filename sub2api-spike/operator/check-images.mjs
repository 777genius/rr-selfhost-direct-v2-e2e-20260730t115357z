import { writeFile } from 'node:fs/promises';
export function checkImages(env) {
  const result = {};
  for (const name of ['SUB2API_IMAGE', 'POSTGRES_IMAGE', 'REDIS_IMAGE', 'NODE_IMAGE']) {
    if (!/^[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}$/.test(env[name] ?? '')) throw Error(`Immutable digest required: ${name}`);
    result[name] = env[name];
  }
  if (Number(process.versions.node.split('.')[0]) !== 24) throw Error('Node24 required');
  return { schema: 1, images: result, node: process.version, claimed_sub2api_sha: '96f4c115c9749078f90cbf210a01d39baf3f53b6', pin_verified: false, limitation: 'Operator must independently map image digest to tagged source; digest syntax alone does not prove source provenance.' };
}
if (process.argv[1]?.endsWith('/check-images.mjs')) {
  const result = checkImages(process.env);
  if (process.argv[2]) await writeFile(process.argv[2], JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
  else console.log(JSON.stringify(result));
}
