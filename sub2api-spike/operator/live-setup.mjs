// COORDINATOR ONLY. Plan/verify an exclusive disposable fixture; no real-key POST.
import { randomBytes } from 'node:crypto';
import { lstat, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { AdminAPI, providerProfiles, requireProbeInstallation } from '../customer.mjs';
const prefix = 'rr-sub2-spike-20260930-';
const keys = Object.keys(providerProfiles);
const literal = s => "'" + s.replaceAll("'", "''") + "'";
export async function privateFile(dir, name) {
  const path = join(dir, name), info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink() || info.uid !== 0 || info.mode & 0o077 || info.nlink !== 1) throw Error('PRIVATE_FILE_DENIED');
  return readFile(path, 'utf8');
}
async function privateDirectory(dir) {
  if (process.getuid() !== 0 || process.getgid() !== 0 || await import('node:fs/promises').then(m => m.realpath(dir)) !== dir) throw Error('ROOT_PRIVATE_DIRECTORY_REQUIRED');
  const info = await lstat(dir);
  if (!info.isDirectory() || info.uid !== 0 || info.mode & 0o077) throw Error('ROOT_PRIVATE_DIRECTORY_REQUIRED');
}
export function templatePlan(owner) {
  if (!/^[a-f0-9]{32}$/.test(owner)) throw Error('FIXTURE_OWNER_INVALID');
  const templates = ['a', 'b'].flatMap(workspace => keys.map(key => {
    const [provider, protocol] = key.split(':'), profile = providerProfiles[key];
    return { workspace, key, name: `${prefix}${owner}-${workspace}-${provider}-${protocol}`, platform: profile.platform, type: 'apikey',
      status: 'inactive', schedulable: false, group_ids: [], concurrency: 2, priority: 1, rate_multiplier: 1,
      credentials: { api_key: `inert-${owner}-${workspace}`, base_url: 'https://fixture.invalid/v1', model_mapping: { [profile.model]: profile.model } },
      extra: { ...(profile.platform === 'openai' ? { openai_disable_capability_probe: true } : {}), rr_quarantine_template: { fixtureOwner: owner, workspace, provider, protocol } } };
  }));
  // Direct atomic seed while the engine/broker/runner are stopped. No handler,
  // default-group binding, transient active state or scheduled probe is invoked.
  const values = templates.map(t => `(${literal(t.name)},${literal(t.platform)},'apikey',${literal(JSON.stringify(t.credentials))}::jsonb,${literal(JSON.stringify(t.extra))}::jsonb,2,1,1,'inactive',false,false,NOW(),NOW())`).join(',\n');
  const sql = `\\set ON_ERROR_STOP on\nBEGIN;\nLOCK TABLE accounts, account_groups IN EXCLUSIVE MODE;\nDO $$ BEGIN IF EXISTS (SELECT 1 FROM accounts WHERE extra->'rr_quarantine_template'->>'fixtureOwner'=${literal(owner)}) THEN RAISE EXCEPTION 'OWNED_SEED_EXISTS_DO_NOT_RETRY'; END IF; END $$;\nWITH inserted AS (INSERT INTO accounts (name,platform,type,credentials,extra,concurrency,priority,rate_multiplier,status,schedulable,auto_pause_on_expired,created_at,updated_at) VALUES\n${values}\nRETURNING id,extra) SELECT jsonb_build_object('owner',${literal(owner)},'templates',jsonb_agg(jsonb_build_object('id',id,'workspace',extra->'rr_quarantine_template'->>'workspace','provider',extra->'rr_quarantine_template'->>'provider','protocol',extra->'rr_quarantine_template'->>'protocol'))) FROM inserted;\nCOMMIT;\n`;
  return { schema: 1, owner, templates, sql };
}
export function validateTemplate(a, t, owner) {
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const marker = a?.extra?.rr_quarantine_template;
  if (!Number.isSafeInteger(a?.id) || a.id < 1 || typeof a.name !== 'string' || !a.name.startsWith(prefix) ||
      a.platform !== t.platform || a.type !== 'apikey' || a.status !== 'inactive' || a.schedulable !== false ||
      !Object.hasOwn(a, 'credentials') || !(a.credentials === null || object(a.credentials)) || !object(a.extra) ||
      marker?.fixtureOwner !== owner || marker.workspace !== t.workspace || `${marker.provider}:${marker.protocol}` !== t.key ||
      ['group_ids', 'groups', 'account_groups'].some(k => Object.hasOwn(a, k) && (!Array.isArray(a[k]) || a[k].length !== 0)) ||
      a.platform === 'openai' && a.extra.openai_disable_capability_probe !== true) throw Error('INERT_TEMPLATE_DTO_DENIED');
  return a.id;
}
export async function loadFixtureConfiguration(dir = '/private') {
  await privateDirectory(dir);
  const f = JSON.parse(await privateFile(dir, 'fixtures.json'));
  requireProbeInstallation(f.installation);
  const plan = templatePlan(f.owner), ids = [];
  for (const t of plan.templates) {
    const id = f.quarantineTemplates?.[t.workspace]?.[t.key];
    if (!Number.isSafeInteger(id) || id < 1) throw Error('FIXTURE_ID_REQUIRED'); ids.push(id);
  }
  if (new Set(ids).size !== ids.length) throw Error('FIXTURE_ID_REUSED');
  return f;
}
export async function main(mode, directory) {
  const dir = resolve(directory ?? '/private'); await privateDirectory(dir);
  if (mode === 'plan') {
    const plan = templatePlan(randomBytes(16).toString('hex'));
    await writeFile(join(dir, 'template-plan.json'), JSON.stringify(plan, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
    await writeFile(join(dir, 'template-seed.sql'), plan.sql, { mode: 0o600, flag: 'wx' });
    return; // No server key or provider credential was read.
  }
  if (mode !== 'verify') throw Error('MODE_DENIED');
  const plan = JSON.parse(await privateFile(dir, 'template-plan.json'));
  const installation = JSON.parse(await privateFile(dir, 'installation.json')); requireProbeInstallation(installation);
  const admin = new AdminAPI({ baseURL: 'http://sub2api:8080', adminKey: (await privateFile(dir, 'admin.key')).trim(), installation });
  const observed = [];
  // Lost SQL acknowledgement: enumerate full DTOs by exact durable ownership;
  // do not reinsert or accept name-only recovery, ambiguous/missing sets deny.
  for (let page = 1; ; page++) {
    if (page > 100) throw Error('FIXTURE_SCAN_LIMIT');
    const data = await admin.call('GET', `/accounts?page=${page}&page_size=100&lite=false&search=${encodeURIComponent(`${prefix}${plan.owner}`)}`);
    if (!Array.isArray(data?.items) || !Number.isSafeInteger(data.total) || data.total < 0) throw Error('FULL_LIST_REQUIRED');
    observed.push(...data.items);
    if (page * 100 >= data.total) break;
  }
  const quarantineTemplates = {};
  for (const t of templatePlan(plan.owner).templates) {
    const matches = observed.filter(a => a.extra?.rr_quarantine_template?.fixtureOwner === plan.owner && a.extra.rr_quarantine_template.workspace === t.workspace && `${a.extra.rr_quarantine_template.provider}:${a.extra.rr_quarantine_template.protocol}` === t.key);
    if (matches.length !== 1 || matches[0].name !== t.name) throw Error('FIXTURE_RECOVERY_AMBIGUOUS');
    const id = validateTemplate(matches[0], t, plan.owner);
    const full = await admin.call('GET', `/accounts/${id}`);
    if (validateTemplate(full, t, plan.owner) !== id || full.name !== t.name) throw Error('FIXTURE_ID_DRIFT');
    (quarantineTemplates[t.workspace] ??= {})[t.key] = id;
  }
  const ids = Object.values(quarantineTemplates).flatMap(Object.values);
  if (new Set(ids).size !== ids.length) throw Error('FIXTURE_ID_REUSED');
  await writeFile(join(dir, 'fixtures.json'), JSON.stringify({ schema: 1, owner: plan.owner, installation, quarantineTemplates }, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  // Root/coordinator executes only after routing is stopped and owned copies are
  // retired through the adapter. Exact IDs AND marker AND inert state must match.
  const exactRows = templatePlan(plan.owner).templates.map(t => {
    const [provider, protocol] = t.key.split(':');
    return `(id=${quarantineTemplates[t.workspace][t.key]} AND platform=${literal(t.platform)} AND type='apikey' AND extra->'rr_quarantine_template'->>'workspace'=${literal(t.workspace)} AND extra->'rr_quarantine_template'->>'provider'=${literal(provider)} AND extra->'rr_quarantine_template'->>'protocol'=${literal(protocol)})`;
  }).join(' OR ');
  const guard = `(${exactRows}) AND extra->'rr_quarantine_template'->>'fixtureOwner'=${literal(plan.owner)} AND status='inactive' AND schedulable=false AND deleted_at IS NULL`;
  const cleanup = `\\set ON_ERROR_STOP on\nBEGIN;\nLOCK TABLE accounts, account_groups IN EXCLUSIVE MODE;\nDO $$ BEGIN IF (SELECT count(*) FROM accounts a WHERE ${guard} AND NOT EXISTS (SELECT 1 FROM account_groups g WHERE g.account_id=a.id)) <> ${ids.length} THEN RAISE EXCEPTION 'OWNED_CLEANUP_DENIED'; END IF; END $$;\nDELETE FROM accounts WHERE ${guard};\nCOMMIT;\n`;
  await writeFile(join(dir, 'template-cleanup.sql'), cleanup, { mode: 0o600, flag: 'wx' });
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { await main(process.argv[2], process.argv[3]); }
  catch { console.error('FIXTURE_SETUP_DENIED: inspect private journal; never automatically retry seed'); process.exitCode = 1; }
}
