// COORDINATOR ONLY. Stop inference/routing and revoke grants before invocation.
// No seed retry, foreign-ID compensation, state editing or name-only adoption.
import { AdminAPI, customerAdapter } from '../sub2api-spike/customer.mjs';
import { loadFixtureConfiguration, privateFile } from '../sub2api-spike/operator/live-setup.mjs';
const fixtures = await loadFixtureConfiguration('/private');
const approval = JSON.parse(await privateFile('/private', 'cleanup-control.json'));
if (approval.owner !== fixtures.owner || approval.routingStopped !== true || approval.grantsRevoked !== true || approval.engineInferenceBlocked !== true) throw Error('COORDINATOR_CLEANUP_CONTROL_REQUIRED');
const workspaces = JSON.parse(await privateFile('/private', 'roundtrip-workspaces.json'));
for (const [workspace, w] of Object.entries(workspaces)) {
  if (!['a', 'b'].includes(workspace) || w.fixtureOwner !== fixtures.owner ||
      w.groupName !== `rr-sub2-spike-20260930-${fixtures.owner}-${workspace}-responses` ||
      !Number.isSafeInteger(w.groups?.['mimo:responses']) || w.groups['mimo:responses'] < 1) throw Error('WORKSPACE_JOURNAL_DENIED');
}
const admin = new AdminAPI({ baseURL: 'http://sub2api:8080', adminKey: (await privateFile('/private', 'admin.key')).trim(), installation: fixtures.installation });
const adapter = await customerAdapter({ statePath: '/state/customer-roundtrip.json', admin, workspaces, quarantineTemplates: fixtures.quarantineTemplates, credentialProfiles: {} });
// Isolated retirement controller only. Startup may fence interrupted promotion;
// coordinator has explicitly stopped/revoked all routing before clearing it here.
for (const w of Object.values(workspaces)) w.suspended = false;
for (const intent of await adapter.recovery()) await adapter.reconcile({ workspace: intent.workspace, user: 'owner' }, intent.id, 'retire');
for (const workspace of Object.keys(workspaces)) {
  const identity = { workspace, user: 'owner' };
  for (const account of await adapter.operate(identity, 'list')) await adapter.operate(identity, 'delete', account.id);
}
if ((await adapter.recovery()).length) throw Error('OWNED_RETIREMENT_INCOMPLETE');
// No successful client/model receipt is produced. Coordinator stops the engine,
// runs guarded template-cleanup.sql, then tears down only the dedicated stack.
