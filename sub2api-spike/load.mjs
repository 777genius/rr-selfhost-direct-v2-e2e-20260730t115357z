// Synthetic HTTP transport load only; cannot target live providers or private engines.
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createBroker } from './broker.mjs';
import { mockUpstream } from './mock-upstream.mjs';
import { verifier, token } from './test-support.mjs';
import { nativeEvents } from './evidence.mjs';
import { listen, stop } from './util.mjs';
const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-spike-20260930-load-'));
const upstream = mockUpstream(); let broker;
const receipt = { schema: 1, id: 'G05', evidence_kind: 'synthetic-upstream', status: 'FAIL', node: process.version, rounds: [], total_errors: 0, limitation: 'Node broker/mocked transport load only; excludes Sub2API engine/DB/Redis and paid model inference.' };
let runID = 1000, peakRSS = process.memoryUsage().rss;
const sample = setInterval(() => { peakRSS = Math.max(peakRSS, process.memoryUsage().rss); }, 10);
try {
  const upstreamURL = await listen(upstream.server);
  broker = await createBroker({ ledgerPath: join(dir, 'ledger.json'), verifyOIDC: verifier(), resolveWorkspace: c => Number(c.runID) % 2 ? 'a' : 'b', scopes: { 'mimo:responses': { protocol: 'responses', model: 'mimo-v2.6-pro', baseURL: upstreamURL, workspaces: { a: { key: 'synthetic-private-a', groupID: 1 }, b: { key: 'synthetic-private-b', groupID: 2 } } } } });
  const url = await listen(broker);
  for (const concurrency of [1, 5, 20, ...Array(10).fill(20)]) {
    const latencies = []; let errors = 0; const before = upstream.metrics.requests, started = Date.now();
    await Promise.all(Array.from({ length: concurrency }, async () => {
      const start = performance.now(), id = String(runID++); let cap;
      try {
        const grant = await fetch(`${url}/grant`, { method: 'POST', headers: { authorization: `Bearer ${token({ run_id: id })}` }, body: '{"provider":"mimo","protocol":"responses"}' });
        if (!grant.ok) throw Error('grant_failed'); cap = (await grant.json()).capability;
        const response = await fetch(`${url}/v1/responses`, { method: 'POST', headers: { authorization: `Bearer ${cap}` }, body: JSON.stringify({ input: [{ type: 'function_call_output', call_id: `run-${id}`, output: id }] }) });
        const events = await nativeEvents(response, 'responses');
        if (!events.some(e => e.delta?.includes(`run-${id}`))) throw Error('response_crossover');
      } catch { errors++; } finally {
        if (cap) await fetch(`${url}/grant`, { method: 'DELETE', headers: { authorization: `Bearer ${cap}` } }).catch(() => {});
        latencies.push(performance.now() - start);
      }
    }));
    latencies.sort((a,b) => a-b); receipt.total_errors += errors;
    receipt.rounds.push({ concurrency, duration_ms: Date.now() - started, errors, upstream_requests: upstream.metrics.requests - before, latency_p50_ms: latencies[Math.ceil(latencies.length * .5) - 1], latency_p95_ms: latencies[Math.ceil(latencies.length * .95) - 1], rss_bytes: process.memoryUsage().rss, stuck_connections: upstream.metrics.active });
  }
  receipt.upstream_requests = upstream.metrics.requests; receipt.peak_rss_bytes = peakRSS; receipt.stuck_connections = upstream.metrics.active;
  receipt.status = receipt.total_errors === 0 && receipt.upstream_requests === 226 && receipt.stuck_connections === 0 ? 'PASS' : 'FAIL';
} catch { receipt.failure_code = 'SYNTHETIC_LOAD_FAILURE'; }
finally { clearInterval(sample); if (broker) await stop(broker); await stop(upstream.server); await rm(dir, { recursive: true, force: true }); }
if (process.argv[2]) await writeFile(process.argv[2], JSON.stringify(receipt, null, 2) + '\n'); else console.log(JSON.stringify(receipt));
if (receipt.status !== 'PASS') process.exitCode = 1;
