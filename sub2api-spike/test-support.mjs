import { generateKeyPairSync, sign } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createBroker } from './broker.mjs';
import { sub2OIDCVerifier, workflowRef } from './oidc.mjs';
import { issuer, audience, repository } from '../gateway-spike/oidc.mjs';
import { mockUpstream } from './mock-upstream.mjs';
import { listen, stop } from './util.mjs';
const { publicKey, privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
export const workflowSHA = 'a'.repeat(40);
export const jwks = async () => ({ keys: [{ ...publicKey.export({ format: 'jwk' }), kid: 'synthetic-rsa', alg: 'RS256', use: 'sig' }] });
export function token(overrides = {}, header = {}, key = privateKey) {
  const now = Math.floor(Date.now() / 1000);
  const h = Buffer.from(JSON.stringify({ alg: 'RS256', kid: 'synthetic-rsa', ...header })).toString('base64url');
  const c = Buffer.from(JSON.stringify({ iss: issuer, aud: audience, repository, repository_id: '1317214237', repository_owner_id: '13103045', workflow_ref: workflowRef, workflow_sha: workflowSHA, ref: 'refs/heads/main', event_name: 'workflow_dispatch', run_id: '123', run_attempt: '1', exp: now + 600, nbf: now - 1, iat: now - 1, ...overrides })).toString('base64url');
  return `${h}.${c}.${sign('RSA-SHA256', Buffer.from(`${h}.${c}`), key).toString('base64url')}`;
}
export const verifier = () => sub2OIDCVerifier({ ownerID: '13103045', workflowSHA, jwks });
export async function rig(t, opts = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-spike-20260930-'));
  const upstream = mockUpstream(opts.mock); const upstreamURL = await listen(upstream.server);
  const scopes = Object.fromEntries(['responses', 'messages'].map(protocol => [`mimo:${protocol}`, { protocol, model: 'mimo-v2.6-pro', baseURL: upstreamURL, workspaces: { a: { key: 'synthetic-private-a', groupID: 1 }, b: { key: 'synthetic-private-b', groupID: 2 } } }]));
  const config = { ledgerPath: join(dir, 'ledger.json'), verifyOIDC: verifier(), scopes, resolveWorkspace: claims => claims.runID.startsWith('2') ? 'b' : 'a', ...opts.broker };
  const broker = await createBroker(config); const url = await listen(broker);
  t.after(async () => { await stop(broker); await stop(upstream.server); await rm(dir, { recursive: true, force: true }); });
  async function grant(protocol = 'responses', claims = {}, body = {}) {
    return fetch(`${url}/grant`, { method: 'POST', headers: { authorization: `Bearer ${token(claims)}`, 'content-type': 'application/json' }, body: JSON.stringify({ provider: 'mimo', protocol, ...body }) });
  }
  async function request(cap, body = {}, path = '/v1/responses', extra = {}) {
    return fetch(`${url}${path}`, { method: 'POST', headers: { authorization: `Bearer ${cap}`, 'content-type': 'application/json', ...extra }, body: JSON.stringify(body) });
  }
  return { dir, config, broker, url, upstream, grant, request };
}
