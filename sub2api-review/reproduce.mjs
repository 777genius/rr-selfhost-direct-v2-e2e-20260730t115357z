// Read-only imports; no listening sockets, credentials, provider calls or engine execution.
import assert from 'node:assert/strict';
import { Readable, Writable } from 'node:stream';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createBroker } from '../sub2api-spike/broker.mjs';
import { mockUpstream } from '../sub2api-spike/mock-upstream.mjs';
import { financialEvidence } from '../sub2api-spike/evidence.mjs';
import { normalizedReceipt } from '../sub2api-spike/receipts.mjs';
import { writeFile } from 'node:fs/promises';
class Capture extends Writable {
  constructor() { super({ autoDestroy: false }); this.chunks = []; this.statusCode = 200; this.headers = {}; }
  _write(chunk, encoding, done) { this.chunks.push(Buffer.from(chunk)); done(); }
  setHeader(name, value) { this.headers[name] = value; }
  writeHead(status, headers = {}) { this.statusCode = status; Object.assign(this.headers, headers); this.headersSent = true; return this; }
  get text() { return Buffer.concat(this.chunks).toString(); }
}
async function invoke(server, method, url, body = {}, capability = '') {
  const req = Readable.from([Buffer.from(JSON.stringify(body))]);
  Object.assign(req, { method, url, headers: { authorization: `Bearer ${capability}`, 'content-type': 'application/json' } });
  const res = new Capture();
  await server.listeners('request')[0](req, res);
  return res;
}
const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-independent-review-'));
const facts = [], originalFetch = globalThis.fetch;
let server;
try {
  const forwarded = [];
  globalThis.fetch = async (url, options) => {
    forwarded.push({ url, body: JSON.parse(options.body), authorization: options.headers.authorization });
    return new Response('data: {"type":"error","error":{"message":"synthetic-provider-key-echo"}}\n\n', { headers: { 'content-type': 'text/event-stream' } });
  };
  server = await createBroker({ ledgerPath: join(dir, 'ledger.json'), verifyOIDC: async () => ({ runID: '17', attempt: '1', expires: Date.now() + 60000 }), resolveWorkspace: () => 'a', scopes: { 'mimo:messages': { protocol: 'messages', model: 'mimo-v2.6-pro', baseURL: 'http://synthetic.invalid', workspaces: { a: { key: 'synthetic-private-engine-key', groupID: 1 } } } } });
  const grant = await invoke(server, 'POST', '/grant', { provider: 'mimo', protocol: 'messages' }, 'synthetic-oidc');
  const capability = JSON.parse(grant.text).capability;
  assert.match(capability, /^[A-Za-z0-9_-]{43}$/);
  assert.deepEqual(Object.keys(JSON.parse(grant.text)).sort(), ['capability', 'expires', 'model']);
  assert.equal(grant.text.includes('synthetic-private-engine-key'), false);
  const query = await invoke(server, 'POST', '/anthropic/v1/messages?beta=true', { messages: [] }, capability);
  assert.equal(query.statusCode, 404); assert.equal(forwarded.length, 0);
  facts.push({ id: 'R01', observed: 'Claude Messages beta=true -> 404 route_denied; no upstream effect' });
  const legitimate = { messages: [{ role: 'assistant', content: [{ type: 'tool_use', id: 't1', name: 'inspect', input: { account: { balance: 100 }, workspace: 'application-data' } }] }] };
  const nested = await invoke(server, 'POST', '/v1/messages', legitimate, capability);
  assert.equal(nested.statusCode, 400); assert.match(nested.text, /routing_denied/); assert.equal(forwarded.length, 0);
  facts.push({ id: 'R03', observed: 'Legitimate tool_use.input.account/workspace -> 400 routing_denied' });
  const echoed = await invoke(server, 'POST', '/v1/messages', { messages: [], client_metadata: { benign: true } }, capability);
  assert.equal(echoed.statusCode, 200); assert.match(echoed.text, /synthetic-provider-key-echo/);
  facts.push({ id: 'R08', observed: 'Broker streams HTTP200 SSE error credential sentinel unchanged; engine redaction not exercised' });
  const mock = mockUpstream();
  const messages = await invoke(mock.server, 'POST', '/v1/messages?beta=true', { model: 'mimo-v2.6-pro', messages: [] });
  assert.match(messages.text, /response\.completed/); assert.doesNotMatch(messages.text, /message_stop/);
  facts.push({ id: 'R02', observed: 'Actual engine Messages URL beta=true makes mock emit Responses SSE' });
  const partial = mockUpstream({ mode: 'partial-reset' });
  const reset = await invoke(partial.server, 'POST', '/v1/responses', { model: 'mimo-v2.6-pro', input: [{ type: 'function_call_output', call_id: 'c1', output: 'synthetic' }] });
  assert.match(reset.text, /response\.completed/);
  facts.push({ id: 'R06', observed: 'partial-reset constructs response.completed before destroying connection; wire delivery unproven' });
  const implementation = await readFile(new URL('../sub2api-spike/fixture/wallet.mjs', import.meta.url), 'utf8');
  const events = [
    { type: 'item.completed', item: { type: 'command_execution', command: '/bin/bash -lc \'cat wallet.mjs\'', aggregated_output: implementation, exit_code: 0, status: 'completed' } },
    { type: 'item.completed', item: { type: 'command_execution', command: 'cat BUSINESS_RULES.md', aggregated_output: 'A withdrawal must be positive', exit_code: 0, status: 'completed' } },
    { type: 'turn.completed' }
  ];
  const review = JSON.stringify({ findings: [{ file: 'wallet.mjs', function: 'withdraw', summary: 'Negative withdrawal increases balance', example: { initial_balance: 100, amount: -10, final_balance: 110 } }] });
  assert.equal(financialEvidence('codex', events, review, 'mimo').rules_read_verified, true);
  events[1].item.command = '/bin/bash -lc \'cat BUSINESS_RULES.md\'';
  assert.throws(() => financialEvidence('codex', events, review, 'mimo'), /Missing separate rules read/);
  facts.push({ id: 'R05', observed: 'Successful shell-wrapped rules read rejected; same plain command accepted' });
  const childCode = 'import {readFileSync} from "node:fs"; const own=process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN !== undefined; const visible=readFileSync(`/proc/${process.ppid}/environ`).includes(Buffer.from("ACTIONS_ID_TOKEN_REQUEST_TOKEN=synthetic-parent-only-oidc")); console.log(JSON.stringify({inherited:own,parent_visible:visible}));';
  const parentCode = 'import {spawnSync} from "node:child_process"; const p=spawnSync(process.execPath,["--input-type=module","-e",'+JSON.stringify(childCode)+'],{env:{LANG:"C.UTF-8"},encoding:"utf8"}); process.stdout.write(p.stdout); if(p.status) process.exit(p.status);';
  const syntheticParent = spawnSync(process.execPath, ['--input-type=module', '-e', parentCode], { env: { LANG: 'C.UTF-8', ACTIONS_ID_TOKEN_REQUEST_TOKEN: 'synthetic-parent-only-oidc' }, encoding: 'utf8' });
  assert.equal(syntheticParent.status, 0);
  const parentEvidence = JSON.parse(syntheticParent.stdout);
  assert.deepEqual(parentEvidence, { inherited: false, parent_visible: true });
  facts.push({ id: 'R07', observed: 'Synthetic-only same-UID child with stripped env can read parent OIDC token via procfs; no real credentials examined' });
  const receiptFile = join(dir, 'receipt.json');
  const receipt = { schema: 1, operator_reviewed: true, evidence_kind: 'contract', versions: { harness_git_sha: 'a'.repeat(40), harness_tree_sha256: 'b'.repeat(64), sub2api_source_sha: '96f4c115c9749078f90cbf210a01d39baf3f53b6', node: process.version }, results: [] };
  await writeFile(receiptFile, JSON.stringify(receipt));
  assert.equal((await normalizedReceipt(receiptFile, 'b'.repeat(64))).versions.harness_git_sha, 'a'.repeat(40));
  facts.push({ id: 'R09', observed: 'Receipt validator accepts arbitrary syntactically valid harness SHA; expected checkpoint equality is not checked' });
  console.log(JSON.stringify({ status: 'PASS', meaning: 'Defect reproduction assertions passed; no E2E claim', node: process.version, sockets: 0, provider_requests: 0, facts }, null, 2));
} finally {
  globalThis.fetch = originalFetch;
  if (server) server.emit('close');
  await rm(dir, { recursive: true, force: true });
}
