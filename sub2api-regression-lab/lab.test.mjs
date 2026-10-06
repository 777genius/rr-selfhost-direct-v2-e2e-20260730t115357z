import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { randomBytes } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createBroker } from '../sub2api-spike/broker.mjs';
import { createMock } from './mock.mjs';
import { Inspector, fixture, CALL, TOOL } from './wire.mjs';
import { request, success } from './client.mjs';
import { control, fetchJSON, mono, sleep, MiB, verifyDeployment, SOURCE, ORIGINAL } from './common.mjs';
import { cancellationVerdict, uncertaintyVerdict, telemetryVerdict } from './receipts.mjs';
const token = () => randomBytes(24).toString('hex');
async function listen(s, t) {
  await new Promise((resolve, reject) => { s.once('error', reject); s.listen(0, '127.0.0.1', resolve); });
  t.after(() => new Promise(resolve => { s.stopLab?.(); s.close(resolve); s.closeAllConnections(); }));
  return `http://127.0.0.1:${s.address().port}`;
}
async function lab(t) {
  const c = { control_token: token(), sentinels: { responses: token(), messages: token() } };
  c.mock_url = await listen(createMock(c), t); return c;
}
async function observe(c, id, predicate) {
  const end = mono() + 2000;
  while (mono() < end) { const rs = (await control(c, 'state')).records.filter(r => r.id === id); if (predicate(rs)) return rs; await sleep(10); }
  assert.fail('observable socket event missing');
}
for (const protocol of ['responses', 'messages']) {
  test(`${protocol}: tiny initial frames do not acknowledge semantic output (old cancellation timing false positive)`, async t => {
    const f = fixture(protocol); let permit; const held = new Promise(r => { permit = r; });
    const s = http.createServer(async (req, res) => {
      for await (const _ of req) {};
      res.writeHead(200, { 'content-type': 'text/event-stream' }); res.write(f.frames[0]);
      await held; for (const frame of f.frames.slice(1)) res.write(frame); res.end();
    });
    const base = await listen(s, t); let ack;
    const p = request(base, token(), protocol, 'tiny', { timeout: 2000, onAck: ms => { ack = ms; } });
    await sleep(50); assert.equal(ack, undefined); permit();
    const result = await p.promise; assert.equal(success(result), true); assert.ok(result.ack_frame_bytes > 4096);
  });
  test(`${protocol}: split UTF-8, near-limit tool and terminal survive streaming discard (protocol corruption/empty completion regression)`, () => {
    const inspector = new Inspector(protocol);
    for (const frame of fixture(protocol, { near: true }).frames)
      for (let i = 0; i < frame.length; i += 7919) inspector.push(frame.subarray(i, i + 7919));
    const result = inspector.finish(); assert.ok(result.terminal_ms); assert.equal(result.malformed, false);
    assert.equal(result.tool_id, protocol === 'responses' ? CALL : TOOL); assert.ok(result.ack_frame_bytes > 4096);
    assert.ok(result.max_frame_bytes < MiB); assert.equal(inspector.pending.length, 0);
  });
  test(`${protocol}: actual accepted effect + acknowledged frame + reset has one effect (duplicate uncertain request regression)`, async t => {
    const c = await lab(t), id = `reset-${protocol}`; let ack;
    const healthy = await request(c.mock_url, c.sentinels[protocol], protocol, `${id}.healthy`).promise;
    assert.equal(success(healthy), true);
    await control(c, 'rule', { id, mode: 'uncertain-after' });
    const p = request(c.mock_url, c.sentinels[protocol], protocol, id, { onAck: (ms, size) => { ack = { ms, size }; } });
    await observe(c, id, x => x.length && x[0].hold_until_ms !== null);
    const end = mono() + 2000; while (!ack && mono() < end) await sleep(10); assert.ok(ack);
    await control(c, 'ack', { id, mono_ms: ack.ms, frame_bytes: ack.size }); await control(c, 'reset', { id });
    const downstream = await p.promise, upstream = await observe(c, id, x => x.length && x[0].close_ms !== null);
    assert.equal(uncertaintyVerdict({ healthy_control: true, downstream, upstream }, 'uncertain-after').status, 'PASS');
    assert.equal(upstream[0].effects, 1);
    assert.equal(uncertaintyVerdict({ healthy_control: true, downstream, upstream: [...upstream, { ...upstream[0], sequence: 99 }] }, 'uncertain-after').status, 'FAIL');
  });
  test(`${protocol}: 8 MiB comments plus real text/tool frames drain without collection (old comment-only load missed native frame damage)`, async t => {
    const c = await lab(t), id = `memory-${protocol}`;
    await control(c, 'rule', { id, mode: 'memory', mib: 8 });
    const d = await request(c.mock_url, c.sentinels[protocol], protocol, id, { slow: true, timeout: 5000 }).promise;
    assert.equal(success(d), true); assert.ok(d.bytes >= 8 * MiB); assert.ok(d.comments > 0);
    assert.ok(d.text_delta_bytes > 4096); assert.ok(d.tool_id); assert.ok(d.max_frame_bytes < MiB);
    const rs = await observe(c, id, x => x.length && x[0].close_ms !== null); assert.equal(rs[0].effects, 1);
  });
  for (const trigger of ['revoke', 'expiry']) test(`${protocol}: actual broker ${trigger} closes active stream and denies authority (B11 regression; no Go claim)`, async t => {
    const c = await lab(t), id = `broker-${protocol}-${trigger}`, oidc = token(), key = c.sentinels[protocol];
    const dir = await mkdtemp(join(tmpdir(), 'rr-transport-test-')); t.after(() => rm(dir, { recursive: true, force: true }));
    const server = await createBroker({ ledgerPath: join(dir, 'ledger.json'), ttlMs: trigger === 'expiry' ? 600 : 5000,
      verifyOIDC: async value => { assert.equal(value, oidc); return { runID: id, attempt: '1', workflowSHA: 'a'.repeat(40), expires: Date.now() + 5000 }; },
      resolveWorkspace: async () => 'lab', scopes: { [`synthetic:${protocol}`]: { protocol, model: protocol === 'responses' ? 'gpt-4.1' : 'claude-sonnet-4-5',
        baseURL: c.mock_url, workspaces: { lab: { key, groupID: 1 } } } } });
    const base = await listen(server, t);
    const grant = await fetchJSON(`${base}/grant`, 'POST', { provider: 'synthetic', protocol }, { authorization: `Bearer ${oidc}` });
    await control(c, 'rule', { id, mode: 'hold-after' }); let ack;
    const p = request(base, grant.capability, protocol, id, { timeout: 2500, onAck: ms => { ack = ms; } });
    const end = mono() + 500; while (!ack && mono() < end) await sleep(10); assert.ok(ack);
    if (trigger === 'revoke') await fetchJSON(`${base}/grant`, 'DELETE', undefined, { authorization: `Bearer ${grant.capability}` });
    const d = await p.promise; assert.equal(success(d), false);
    const rs = await observe(c, id, x => x.length && x[0].close_ms !== null); assert.equal(rs.length, 1);
    const denied = await fetch(`${base}/v1/${protocol}`, { method: 'POST', headers: { authorization: `Bearer ${grant.capability}` }, body: '{}' });
    assert.equal(denied.status, 401); await denied.body.cancel();
  });
}
test('missing upstream/cooldown denial cannot satisfy uncertainty oracle (old no_upstream_fault_exercised false green)', () => {
  assert.equal(uncertaintyVerdict({ healthy_control: true, upstream: [], downstream: {} }, 'uncertain-before').status, 'NOT RUN');
});
test('usage-drain receipt remains red even after terminal/release (default engine immediate-abort regression)', () => {
  const row = { healthy_control: true, cancel_ms: 20, downstream: { ack_ms: 10, ack_frame_bytes: 8192 }, upstream: [{
    effects: 1, effect_ms: 1, first_flush_ms: 2, ack_received_ms: 11, close_ms: 10030, release_ms: 10000, terminal_ms: 10020 }] };
  assert.equal(cancellationVerdict(row, 'after').status, 'FAIL');
  row.upstream[0].close_ms = 30; row.upstream[0].terminal_ms = null; row.upstream[0].release_ms = null;
  assert.equal(cancellationVerdict(row, 'after').status, 'PASS');
  row.upstream[0].first_flush_ms = null;
  assert.equal(cancellationVerdict(row, 'after').status, 'FAIL');
});
const meta = { id: 'batch', instance: 'owned', engine_pid: 12, streams: 5, started_ms: 1100, ended_ms: 1400 };
const sample = (mono_ms, phase, rss_bytes = 100 * MiB) => ({ collector: 'root-go-pid', batch_id: 'batch', instance: 'owned', engine_pid: 12,
  clock: 'linux-CLOCK_MONOTONIC', phase, mono_ms, peak_reset_ms: 1000, rss_bytes, cgroup_current_bytes: rss_bytes,
  cgroup_peak_bytes: rss_bytes, cgroup_limit_bytes: 768 * MiB, sockets: 2, goroutines: 20 });
test('client RSS or sparse telemetry never produces engine memory PASS (original unmeasured engine peak regression)', () => {
  assert.equal(telemetryVerdict([], meta).status, 'NOT RUN');
  const ss = [sample(1000, 'baseline'), sample(1200, 'sample'), sample(1400, 'quiescent')];
  assert.equal(telemetryVerdict(ss, meta).status, 'PASS');
  assert.equal(telemetryVerdict(ss.map(x => ({ ...x, collector: 'client-rss' })), meta).status, 'NOT RUN');
  ss[1].rss_bytes = 400 * MiB; ss[1].cgroup_current_bytes = 400 * MiB; ss[1].cgroup_peak_bytes = 400 * MiB;
  assert.equal(telemetryVerdict(ss, meta).status, 'FAIL');
  ss[1] = sample(1200, 'sample'); ss[2].rss_bytes = 140 * MiB;
  assert.equal(telemetryVerdict(ss, meta).status, 'FAIL');
});
test('patched image cannot be accepted as original deployment (hardcoded-image provenance regression)', () => {
  const expected = { source_sha: SOURCE, image: ORIGINAL, instance: 'owned', variant: 'original', patch_sha256: null,
    source_manifest_sha256: 'a'.repeat(64), cgroup_limit_bytes: 768 * MiB };
  const observed = { ...expected, inspected: true, engine_pid: 12, clock: 'linux-CLOCK_MONOTONIC' };
  assert.equal(verifyDeployment(expected, observed).variant, 'original');
  assert.throws(() => verifyDeployment(expected, { ...observed, variant: 'patched' }));
});
test('unterminated or HTTP-200 error cannot be successful protocol evidence (E02/E03/E04 regression)', () => {
  const i = new Inspector('responses'); i.push(Buffer.from('event: response.created\ndata: {"type":"response.created"}\n\n'));
  i.push(Buffer.from('data: {"type":"response.failed","response":{"status":"failed"}}\n\n'));
  i.push(Buffer.from('data: {')); const r = i.finish(); assert.equal(r.failed, true); assert.equal(r.malformed, true); assert.equal(r.terminal_ms, null);
});
