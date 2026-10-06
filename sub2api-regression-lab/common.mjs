import { readFile, writeFile } from 'node:fs/promises';
export const SOURCE = '96f4c115c9749078f90cbf210a01d39baf3f53b6';
export const ORIGINAL = 'weishaw/sub2api@sha256:2e3b7fab1e84d2e862cde664d09c1ae84fc897093357cf200cbeb0f64b2f2390';
export const MiB = 1048576;
export const mono = () => Number(process.hrtime.bigint()) / 1e6;
export const sleep = ms => new Promise(r => setTimeout(r, Math.max(0, ms)));
export function must(ok, code) { if (!ok) throw Object.assign(new Error(code), { labCode: code }); }
export async function jsonFile(path) { return JSON.parse(await readFile(path, 'utf8')); }
export async function save(path, data, exclusive = false) {
  await writeFile(path, JSON.stringify(data, null, 2) + '\n', { mode: 0o600, flag: exclusive ? 'wx' : 'w' });
}
export function validateConfig(c) {
  must(/^v24\./.test(process.version), 'NODE24_REQUIRED');
  must(/^[a-z0-9-]{1,36}$/.test(c.run_id), 'RUN_ID_INVALID');
  must(c.admin_bearer?.length >= 24 && c.control_token?.length >= 24, 'PRIVATE_AUTH_MISSING');
  must(c.mock_url === 'http://mock:8099' && c.engine_url === 'http://sub2api:8080', 'PRIVATE_URLS_ONLY');
  must(c.deployment?.source_sha === SOURCE, 'SOURCE_PIN_MISMATCH');
  must(/^[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}$/.test(c.deployment.image), 'IMMUTABLE_IMAGE_REQUIRED');
  must(/^[a-z0-9-]{1,64}$/.test(c.deployment.instance), 'INSTANCE_REQUIRED');
  must(c.deployment.cgroup_limit_bytes === 768 * MiB, 'CGROUP_LIMIT_REQUIRED');
  must(['original', 'patched'].includes(c.deployment.variant), 'VARIANT_REQUIRED');
  must(/^[a-f0-9]{64}$/.test(c.deployment.source_manifest_sha256), 'SOURCE_MANIFEST_REQUIRED');
  if (c.deployment.variant === 'original') must(c.deployment.image === ORIGINAL && c.deployment.patch_sha256 === null, 'ORIGINAL_PIN_MISMATCH');
  else must(/^[a-f0-9]{64}$/.test(c.deployment.patch_sha256) && c.deployment.image !== ORIGINAL, 'PATCH_PIN_REQUIRED');
  must(Object.keys(c.sentinels ?? {}).sort().join() === 'messages,responses', 'SENTINEL_LABELS_INVALID');
  must(Object.values(c.sentinels).every(x => /^rr-synthetic-[a-f0-9]{48}$/.test(x)) && new Set(Object.values(c.sentinels)).size === 2, 'SYNTHETIC_ONLY');
  return c;
}
export function verifyDeployment(expected, observed) {
  for (const key of ['source_sha', 'image', 'instance', 'variant', 'patch_sha256', 'source_manifest_sha256', 'cgroup_limit_bytes'])
    must(expected[key] === observed[key], 'DEPLOYED_PIN_MISMATCH');
  must(observed.inspected === true && Number.isSafeInteger(observed.engine_pid) && observed.engine_pid > 0 && observed.clock === 'linux-CLOCK_MONOTONIC', 'DEPLOYMENT_OBSERVATION_REQUIRED');
  return { ...expected, engine_pid: observed.engine_pid, clock: observed.clock };
}
export async function loadConfig(path = '/private/lab.json') {
  const c = validateConfig(await jsonFile(path));
  c.observed = verifyDeployment(c.deployment, await jsonFile('/private/deployed.json'));
  return c;
}
export async function fetchJSON(url, method = 'GET', body, headers = {}, deadline = Infinity) {
  must(mono() < deadline, 'BATCH_DEADLINE');
  const r = await fetch(url, { method, headers: { 'content-type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(Math.max(1, Math.ceil(Math.min(5000, deadline - mono())))) });
  must(r.ok, 'CONTROL_OR_ADMIN_REJECTED');
  const bytes = await r.arrayBuffer(); must(bytes.byteLength <= 2 * MiB, 'CONTROL_OR_ADMIN_LIMIT');
  const data = JSON.parse(Buffer.from(bytes));
  must(data.code === undefined || data.code === 0, 'ADMIN_API_REJECTED'); return data.data ?? data;
}
export function control(c, action, body) {
  return fetchJSON(`${c.mock_url}/__lab/${action}`, body === undefined ? 'GET' : 'POST', body, { 'x-lab-control': c.control_token }, c.deadline);
}
export function admin(c, path, method = 'GET', body, bearer = c.admin_bearer) {
  return fetchJSON(`${c.engine_url}/api/v1${path}`, method, body, { authorization: `Bearer ${bearer}` }, c.deadline);
}
