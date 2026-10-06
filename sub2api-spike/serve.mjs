import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { createBroker } from './broker.mjs';
import { sub2OIDCVerifier } from './oidc.mjs';
import { AdminAPI, customerAdapter, testCustomerServer, providerProfiles, requireProbeInstallation } from './customer.mjs';

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
// Structural validation only. The existing adapter validates template DTOs and
// ownership through the actual AdminAPI before any credential-bearing mutation.
function validateTemplates(templates, workspaces) {
  if (!object(templates)) throw Error('Invalid quarantine templates');
  for (const [workspace, profiles] of Object.entries(templates)) {
    if (!Object.hasOwn(workspaces, workspace) || !object(profiles)) throw Error('Invalid quarantine templates');
    for (const [scope, id] of Object.entries(profiles)) {
      if (!Object.hasOwn(providerProfiles, scope) || !Number.isSafeInteger(id) || id < 1) throw Error('Invalid quarantine templates');
    }
  }
}
async function listen(server, port, host) {
  await new Promise((resolve, reject) => {
    const failed = error => { server.off('listening', ready); reject(error); };
    const ready = () => { server.off('error', failed); resolve(); };
    server.once('error', failed); server.once('listening', ready);
    server.listen(port, host);
  });
}
async function close(server) {
  if (!server) return;
  await new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
}

export async function boot(config, { brokerPort = 8787, customerPort = 8788 } = {}) {
  if (Number(process.versions.node.split('.')[0]) !== 24) throw Error('Node 24 required');
  // Trusted operator-custodied server-only file; never mount into Actions.
  // These declarations do not independently authenticate the installed engine.
  const workspaces = config.workspaces;
  const customer = config.customer;
  if (customer) {
    if (!customer.listenHost || ['0.0.0.0', '::'].includes(customer.listenHost)) throw Error('Control binding required');
    requireProbeInstallation(customer.installation);
    validateTemplates(customer.quarantineTemplates === undefined ? {} : customer.quarantineTemplates, workspaces);
    for (const [workspace, policy] of Object.entries(workspaces)) {
      if (policy.quarantineTemplates !== undefined) validateTemplates({ [workspace]: policy.quarantineTemplates }, workspaces);
    }
  }
  for (const [name, scope] of Object.entries(config.scopes)) {
    const expected = providerProfiles[name];
    if (!expected || scope.model !== expected.model || scope.protocol !== name.split(':')[1] || scope.baseURL !== 'http://sub2api:8080') throw Error('Invalid private native scope');
    for (const [workspace, b] of Object.entries(scope.workspaces)) {
      if (b.groupID !== workspaces[workspace]?.groups?.[name]) throw Error('Group metadata mismatch');
      b.key = (await readFile(b.keyFile, 'utf8')).trim(); if (!b.key) throw Error('Missing private key');
    }
  }
  const resolveWorkspace = claims => config.runBindings?.[`${claims.runID}:${claims.attempt}`];
  const isWorkspaceActive = workspace => !workspaces[workspace]?.suspended && workspaces[workspace]?.members?.[config.runUsers?.[workspace]];
  const verifyOIDC = sub2OIDCVerifier(config.oidc);
  let server, control;
  const pendingRevocations = new Set();
  const shutdown = async () => { await Promise.all([close(control), close(server)]); };
  try {
    if (customer) {
      const credentials = {};
      for (const [workspace, profiles] of Object.entries(customer.credentialFiles)) {
        credentials[workspace] = {};
        for (const [scope, path] of Object.entries(profiles)) credentials[workspace][scope] = async () => (await readFile(path, 'utf8')).trim();
      }
      const admin = new AdminAPI({ baseURL: customer.baseURL, adminKey: (await readFile(customer.adminKeyFile, 'utf8')).trim(), installation: customer.installation });
      const adapter = await customerAdapter({ statePath: customer.statePath, admin, workspaces, credentialProfiles: credentials, quarantineTemplates: customer.quarantineTemplates,
        onAuthorityChange: workspace => server ? server.revokeWorkspace(workspace) : pendingRevocations.add(workspace) });
      // Complete adapter recovery and synthetic control validation before broker
      // construction (which persists its ledger), and before either listener.
      control = testCustomerServer({ adapter, identities: customer.identities, testOnly: customer.testOnly });
    }
    server = await createBroker({ ...config, verifyOIDC, resolveWorkspace, isWorkspaceActive, log: record => process.stdout.write(JSON.stringify(record) + '\n') });
    for (const workspace of pendingRevocations) server.revokeWorkspace(workspace);
    await listen(server, brokerPort, '0.0.0.0');
    if (control) await listen(control, customerPort, customer.listenHost);
    return { server, control, shutdown };
  } catch (error) { await shutdown(); throw error; }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const config = JSON.parse(await readFile(process.argv[2], 'utf8'));
  const runtime = await boot(config);
  let stopping = false;
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, async () => {
    if (stopping) return; stopping = true;
    await runtime.shutdown(); process.exitCode = 0;
  });
}
