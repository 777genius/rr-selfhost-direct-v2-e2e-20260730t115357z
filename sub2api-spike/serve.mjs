import { readFile } from 'node:fs/promises';
import { createBroker } from './broker.mjs';
import { sub2OIDCVerifier } from './oidc.mjs';
import { AdminAPI, customerAdapter, testCustomerServer, providerProfiles } from './customer.mjs';
if (Number(process.versions.node.split('.')[0]) !== 24) throw Error('Node 24 required');
const config = JSON.parse(await readFile(process.argv[2], 'utf8'));
// Trusted server-only file; never mount into Actions. No caller picks a URL/key.
for (const [name, scope] of Object.entries(config.scopes)) {
  const expected = providerProfiles[name];
  if (!expected || scope.model !== expected.model || scope.protocol !== name.split(':')[1] || scope.baseURL !== 'http://sub2api:8080') throw Error('Invalid private native scope');
  for (const [workspace, b] of Object.entries(scope.workspaces)) {
    if (b.groupID !== config.workspaces[workspace]?.groups?.[name]) throw Error('Group metadata mismatch');
    b.key = (await readFile(b.keyFile, 'utf8')).trim(); if (!b.key) throw Error('Missing private key');
  }
}
const workspaces = config.workspaces;
const resolveWorkspace = claims => config.runBindings?.[`${claims.runID}:${claims.attempt}`];
const isWorkspaceActive = workspace => !workspaces[workspace]?.suspended && workspaces[workspace]?.members?.[config.runUsers?.[workspace]];
const server = await createBroker({ ...config, verifyOIDC: sub2OIDCVerifier(config.oidc), resolveWorkspace, isWorkspaceActive, log: record => process.stdout.write(JSON.stringify(record) + '\n') });
if (config.customer && (!config.customer.listenHost || ['0.0.0.0', '::'].includes(config.customer.listenHost))) throw Error('Control binding required');
server.listen(8787, '0.0.0.0');
if (config.customer) {
  if (!config.customer.listenHost || ['0.0.0.0', '::'].includes(config.customer.listenHost)) throw Error('Customer listener must bind operator-approved control-network IP');
  const credentials = {};
  for (const [workspace, profiles] of Object.entries(config.customer.credentialFiles)) {
    credentials[workspace] = {}; for (const [scope, path] of Object.entries(profiles)) credentials[workspace][scope] = async () => (await readFile(path, 'utf8')).trim();
  }
  const admin = new AdminAPI({ baseURL: config.customer.baseURL, adminKey: (await readFile(config.customer.adminKeyFile, 'utf8')).trim() });
  const adapter = await customerAdapter({ statePath: config.customer.statePath, admin, workspaces, credentialProfiles: credentials, onAuthorityChange: workspace => server.revokeWorkspace(workspace) });
  // Kept on private CONTROL network in operator topology. Never exposed to runner.
  testCustomerServer({ adapter, identities: config.customer.identities, testOnly: config.customer.testOnly }).listen(8788, config.customer.listenHost);
}
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => { server.close(); server.closeAllConnections(); process.exit(0); });
