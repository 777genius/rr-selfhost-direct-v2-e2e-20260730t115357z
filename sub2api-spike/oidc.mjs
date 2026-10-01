// The baseline verifier remains imported and unchanged. Its fixed workflow cannot
// validate the new signed workflow claim; the new verifier reuses its immutable
// issuer/audience/repository constants and implements the same RS256 boundary.
import { oidcVerifier, issuer, audience, repository, workflowRef as legacyRef } from '../gateway-spike/oidc.mjs';
import { createPublicKey, verify } from 'node:crypto';
export { oidcVerifier as baselineOIDCVerifier };
export const workflowRef = `${repository}/.github/workflows/sub2api-gateway-spike.yml@refs/heads/main`;
export function sub2OIDCVerifier({ ownerID, workflowSHA, clock = Date.now, jwks } = {}) {
  if (String(ownerID) !== '13103045' || !/^[a-f0-9]{40}$/.test(workflowSHA) || workflowRef === legacyRef) throw Error('Invalid OIDC policy');
  let cached, until = 0;
  const keys = jwks ?? (async () => {
    if (clock() < until) return cached;
    const r = await fetch(`${issuer}/.well-known/jwks`, { redirect: 'error', signal: AbortSignal.timeout(10000) });
    if (!r.ok) throw Error('JWKS unavailable'); cached = await r.json(); until = clock() + 300000; return cached;
  });
  return async token => {
    if (typeof token !== 'string' || token.length > 16384) throw Error('Invalid OIDC');
    const p = token.split('.'); if (p.length !== 3 || p.some(x => !/^[A-Za-z0-9_-]+$/.test(x))) throw Error('Invalid OIDC');
    const [h, c] = p.slice(0, 2).map(x => JSON.parse(Buffer.from(x, 'base64url')));
    if (h.alg !== 'RS256' || typeof h.kid !== 'string' || !h.kid) throw Error('Invalid algorithm');
    const matching = (await keys()).keys.filter(k => k.kid === h.kid && k.kty === 'RSA' && (!k.alg || k.alg === 'RS256') && (!k.use || k.use === 'sig'));
    if (matching.length !== 1 || !verify('RSA-SHA256', Buffer.from(`${p[0]}.${p[1]}`), createPublicKey({ key: matching[0], format: 'jwk' }), Buffer.from(p[2], 'base64url'))) throw Error('Invalid signature');
    const now = clock() / 1000;
    if (![c.exp, c.nbf, c.iat].every(Number.isFinite) || c.exp <= now || c.nbf > now || c.iat > now || c.iat > c.exp || c.nbf >= c.exp) throw Error('Invalid time');
    const expected = { iss: issuer, aud: audience, repository, repository_id: '1317214237', repository_owner_id: String(ownerID), workflow_sha: workflowSHA, workflow_ref: workflowRef, ref: 'refs/heads/main', event_name: 'workflow_dispatch' };
    for (const [k, v] of Object.entries(expected)) if (c[k] !== v) throw Error('Invalid scope');
    if (typeof c.run_id !== 'string' || !/^[1-9]\d*$/.test(c.run_id) || !(typeof c.run_attempt === 'string' && /^[1-9]\d*$/.test(c.run_attempt) || Number.isSafeInteger(c.run_attempt) && c.run_attempt > 0)) throw Error('Invalid run');
    return { runID: c.run_id, attempt: String(c.run_attempt), workflowSHA: c.workflow_sha, expires: c.exp * 1000 };
  };
}
