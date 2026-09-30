import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync } from 'node:crypto';
import { token, verifier, workflowSHA, jwks } from './test-support.mjs';
import { baselineOIDCVerifier } from './oidc.mjs';
// Regression: a valid new-workflow signature must grant a scoped run; changing
// workflow validation must not weaken the original workflow verifier.
test('B01 signed new workflow accepted; baseline verifier remains strict', async () => {
  const c = await verifier()(token()); assert.equal(c.runID, '123'); assert.equal(c.attempt, '1');
  await assert.rejects(baselineOIDCVerifier({ ownerID: '13103045', workflowSHA, jwks })(token()), /scope/);
});
// Regression: forged RSA, unknown kid, ambiguous keys and alg confusion authorize.
test('B02 forged signature unknown key invalid algorithm denied', async () => {
  const bad = generateKeyPairSync('rsa', { modulusLength: 2048 }).privateKey;
  for (const s of [token({}, {}, bad), token({}, { kid: 'unknown' }), token({}, { alg: 'HS256' }), 'invalid']) await assert.rejects(verifier()(s));
});
// Regression: malformed or omitted immutable claims/time would authorize a run.
test('B03 B04 B05 immutable identity scope and time denial', async () => {
  for (const change of [{ iss: 'wrong' }, { aud: ['review-router-gateway-spike'] }, { repository: 'other' }, { repository_id: '1' }, { repository_owner_id: '1' }, { workflow_ref: 'other' }, { workflow_sha: 'b'.repeat(40) }, { ref: 'refs/heads/other' }, { event_name: 'pull_request' }, { run_id: null }, { run_attempt: 0 }, { exp: 1 }, { nbf: 9999999999 }, { iat: 'bad' }]) await assert.rejects(verifier()(token(change)));
});
