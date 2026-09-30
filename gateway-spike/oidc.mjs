import { createPublicKey, verify } from 'node:crypto';
export const issuer = 'https://token.actions.githubusercontent.com';
export const audience = 'review-router-gateway-spike';
export const repository = '777genius/rr-selfhost-direct-v2-e2e-20260730t115357z';
export const workflowRef = `${repository}/.github/workflows/provider-gateway-spike.yml@refs/heads/main`;
export function oidcVerifier({ ownerID, workflowSHA, clock = Date.now, jwks } = {}) {
  if (String(ownerID) !== '13103045' || !/^[a-f0-9]{40}$/.test(workflowSHA)) throw Error('Invalid owner or workflow SHA');
  let cached, until = 0;
  const getKeys = jwks ?? (async () => {
    if (clock() < until) return cached;
    const r = await fetch(`${issuer}/.well-known/jwks`, { signal: AbortSignal.timeout(10000), redirect: 'error' });
    if (!r.ok) throw Error('JWKS unavailable');
    cached = await r.json(); until = clock() + 300000; return cached;
  });
  return async token => {
    if (typeof token !== 'string' || token.length > 16384) throw Error('Invalid OIDC');
    const parts = token.split('.');
    if (parts.length !== 3 || parts.some(p => !/^[A-Za-z0-9_-]+$/.test(p))) throw Error('Invalid OIDC');
    const [header, claims] = parts.slice(0, 2).map(p => JSON.parse(Buffer.from(p, 'base64url')));
    if (header.alg !== 'RS256' || typeof header.kid !== 'string' || !header.kid) throw Error('Invalid algorithm');
    const keys = (await getKeys()).keys.filter(k => k.kid === header.kid && k.kty === 'RSA' && (!k.alg || k.alg === 'RS256') && (!k.use || k.use === 'sig'));
    if (keys.length !== 1 || !verify('RSA-SHA256', Buffer.from(`${parts[0]}.${parts[1]}`), createPublicKey({ key: keys[0], format: 'jwk' }), Buffer.from(parts[2], 'base64url'))) throw Error('Invalid signature');
    const now = clock() / 1000;
    if (![claims.exp, claims.nbf, claims.iat].every(Number.isFinite) || claims.exp <= now || claims.nbf > now || claims.iat > now || claims.iat > claims.exp || claims.nbf >= claims.exp) throw Error('Invalid time');
    const expected = { iss: issuer, aud: audience, repository_id: '1317214237', repository, repository_owner_id: String(ownerID), workflow_ref: workflowRef, workflow_sha: workflowSHA, ref: 'refs/heads/main', event_name: 'workflow_dispatch' };
    for (const [k, v] of Object.entries(expected)) if (claims[k] !== v) throw Error('Invalid scope');
    if (typeof claims.run_id !== 'string' || !/^[1-9]\d*$/.test(claims.run_id) || !((typeof claims.run_attempt === 'string' && /^[1-9]\d*$/.test(claims.run_attempt)) || (Number.isSafeInteger(claims.run_attempt) && claims.run_attempt > 0))) throw Error('Invalid run');
    return { runID: claims.run_id, attempt: String(claims.run_attempt), expires: claims.exp * 1000 };
  };
}
