// Deliberate small setup delta from portable run.mjs; public AdminAPI transport reused.
import { randomBytes } from 'node:crypto';
import { admin, save } from '../sub2api-regression-lab/common.mjs';
import { models } from '../sub2api-regression-lab/wire.mjs';
import { limits, requireFact } from './contracts.mjs';
export async function setup(c, spec, journal) {
  const name = `rr-${spec.id}`, platform = spec.protocol === 'responses' ? 'openai' : 'anthropic';
  const create = async (kind, body, bearer) => {
    journal.intent = { kind, name }; await save(journal.path, journal);
    const obj = await admin(c, kind === 'keys' ? '/keys' : `/admin/${kind}`, 'POST', body, bearer);
    requireFact(Number.isSafeInteger(obj.id) && obj.id > 0, 'CREATED_ID_MISSING');
    journal.resources.push({ kind, id: obj.id }); journal.intent = null; await save(journal.path, journal); return obj;
  };
  const group = await create('groups', { name, platform, is_exclusive: true, subscription_type: 'standard', rate_multiplier: 1,
    fallback_group_id: null, fallback_group_id_on_invalid_request: null });
  const extra = { openai_disable_capability_probe: true, ...(spec.protocol === 'responses'
    ? { openai_responses_mode: 'force_responses', openai_passthrough: true } : { anthropic_passthrough: true }),
    ...(spec.optin ? { native_api_key_cancel_on_disconnect: true } : {}) };
  const concurrency = limits(spec.lane);
  const account = await create('accounts', { name, platform, type: 'apikey', concurrency: concurrency.account,
    priority: 1, group_ids: [group.id], upstream_billing_probe_enabled: false,
    credentials: { api_key: c.sentinels[spec.protocol], base_url: spec.protocol === 'responses' ? `${c.mock_url}/v1` : c.mock_url,
      pool_mode: true, pool_mode_retry_count: 0, model_mapping: { [models[spec.protocol]]: models[spec.protocol] } }, extra });
  const password = randomBytes(24).toString('hex'), email = `${name}@example.invalid`;
  const user = await create('users', { email, password, username: name, role: 'user', balance: 1000,
    concurrency: concurrency.user, allowed_groups: [group.id], restrict_public_groups: true });
  const auth = await admin(c, '/auth/login', 'POST', { email, password });
  requireFact(typeof auth.access_token === 'string', 'USER_LOGIN_FAILED');
  journal.user_token = auth.access_token; await save(journal.path, journal);
  const key = await create('keys', { name, group_id: group.id, expires_in_days: 1 }, auth.access_token);
  requireFact(typeof key.key === 'string' && key.key.length > 10, 'PRIVATE_KEY_CREATE_FAILED');
  // Keep custody in /private only; the identical native key is used for all requests.
  journal.native_key = key.key; await save(journal.path, journal);
  const g = await admin(c, `/admin/groups/${group.id}`), a = await admin(c, `/admin/accounts/${account.id}`),
    u = await admin(c, `/admin/users/${user.id}`), k = await admin(c, `/keys/${key.id}`, 'GET', undefined, auth.access_token);
  const groups = a.group_ids ?? a.groups?.map(x => x.id);
  requireFact(g.name === name && g.is_exclusive === true && !g.fallback_group_id && !g.fallback_group_id_on_invalid_request &&
    a.name === name && a.status === 'active' && a.platform === platform && a.type === 'apikey' &&
    a.concurrency === concurrency.account && groups?.length === 1 && groups[0] === group.id &&
    u.id === user.id && u.concurrency === concurrency.user && k.id === key.id && k.group_id === group.id && k.user_id === user.id,
    'DEDICATED_NATIVE_BINDING');
  requireFact(a.extra?.openai_disable_capability_probe === true &&
    (spec.optin ? a.extra?.native_api_key_cancel_on_disconnect === true : !Object.hasOwn(a.extra ?? {}, 'native_api_key_cancel_on_disconnect')),
    'TRUSTED_OPTIN_NOT_PERSISTED_OR_DEFAULT_CHANGED');
  return { key: key.key, ids: { user: user.id, account: account.id, key: key.id }, group: group.id };
}
export async function cleanup(c, journal) {
  let failures = 0;
  for (const r of [...journal.resources].reverse()) {
    try {
      await admin(c, r.kind === 'keys' ? `/keys/${r.id}` : `/admin/${r.kind}/${r.id}`, 'DELETE', undefined,
        r.kind === 'keys' ? journal.user_token : c.admin_bearer);
      journal.resources = journal.resources.filter(x => x !== r); await save(journal.path, journal);
    } catch { failures++; }
  }
  return { failures, ambiguous_intent: journal.intent !== null, remaining: journal.resources.map(({ kind, id }) => ({ kind, id })) };
}
