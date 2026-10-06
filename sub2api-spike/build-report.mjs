import { readFile, writeFile, readdir } from 'node:fs/promises';
import { harnessDigest } from './operator/provenance.mjs';
import { normalizedReceipt } from './receipts.mjs';
const plan = await readFile('sub2api-spike/PLAN.md', 'utf8');
const tree = await harnessDigest();
const source = JSON.parse(await readFile('sub2api-spike/source-snapshot.json', 'utf8'));
let worker; try { worker = JSON.parse(await readFile('sub2api-spike/evidence/worker-verification.json', 'utf8')); } catch { worker = { status: 'NOT RUN' }; }
const entries = [...plan.matchAll(/^- ([A-H]\d{2}) (.+)$/gm)].map(m => ({ id: m[1], input_expected: m[2], status: 'NOT RUN', evidence_kind: 'contract', actual: 'No normalized operator receipt; socket-bound tests cannot execute in worker sandbox.', versions: { node: process.version, sub2api_source_sha: source.claimed_sha, source_pin_verified: source.pin_verified, harness_git_sha: null, harness_tree_sha256: tree }, duration_ms: null, upstream_requests: null, limitation: 'Runnable code/source analysis is not actual container or real Actions success.', evidence: [], observations: [] }));
const byID = new Map(entries.map(e => [e.id,e]));
for (const [id, actual, kind] of [
  ['B01', 'Valid synthetic RSA-signed new-workflow token verified; baseline rejects new workflow. HTTP scoped grant/idempotency not executed.', 'contract'],
  ['B02', 'Forged RSA signature, unknown kid and invalid algorithm rejected by actual cryptographic verifier with synthetic JWKS.', 'contract'],
  ['B03', 'Wrong issuer/audience and malformed run/time claims rejected at verifier boundary; HTTP denial tests await operator.', 'contract'],
  ['B04', 'Repository/name/owner/workflow SHA/ref/main/event mutations rejected at signed verifier boundary.', 'contract'],
  ['B05', 'Expired and future OIDC rejected; capability expiry/cancellation requires socket execution.', 'contract'],
  ['A06', 'Malformed financial output and absent tool evidence rejected; independent fixture withdrawal 100,-10 reproduces 110. Genuine structured client completion pending.', 'contract'],
  ['A10', 'One-byte Web ReadableStream UTF8 split decoded correctly without network; actual proxy large/slow consumer tests pending.', 'contract'],
  ['E04', 'Malformed/truncated SSE rejected by streamed validator without sockets; engine/client stream lane pending.', 'contract'],
  ['D06', 'Inspected accounts.credentials JSONB, direct JSONB updates, Redis scheduler full-account JSON plus metadata retaining api_key, and credential-bearing admin export. These are private credential surfaces; application encryption is not proven. Backups/RDB/AOF/dumps require custody controls.', 'source-audit'],
  ['E11', 'Source risk: max_account_switches=0 ignored by OpenAI handler constructor, effective fallback remains three; same-account retry is independently configured. Our broker never retries. Actual engine uncertain-effect behavior remains unmeasured.', 'source-audit'],
  ['F04', 'Concurrent actual engine OAuth refresh untested. Gateway base_url does not replace OAuth lifecycle endpoint; no approved interception/test identity input.', 'source-audit'],
  ['F05', 'API-key refresh honestly returns reconnect/type requirement; real/synthetic engine OAuth rejection/rotation lane pending.', 'source-audit'],
  ['F07', 'No authorized test-only Codex OAuth identity supplied.', 'source-audit'],
  ['F08', 'No authorized test-only Claude OAuth identity supplied.', 'source-audit'],
  ['F09', 'No credential/account-home/pool access or writes made. Production pool regression remains untested.', 'source-audit'],
  ['H06', 'Source built-in /auth/oauth/oidc/start/callback is human panel login, separate from our signed GitHub workflow run authorization.', 'source-audit'],
  ['H07', 'Staged LICENSE is LGPLv3; deployment must review distribution/source obligations and maintenance policy. Exports/cache/backup contain credentials; no legal conclusion.', 'source-audit'],
  ['H08', 'BYOK CONDITIONAL GO for further isolated evaluation; subscription adoption NO-GO pending identity/lifecycle/isolation evidence; customer boundary CONDITIONAL GO as private prototype, production SSO/membership integration unimplemented.', 'source-audit']
]) { const e=byID.get(id); e.actual=actual; e.evidence_kind=kind; e.observations.push({ status: worker.status, path: kind === 'contract' ? 'evidence/worker-verification.json' : 'SOURCE-ANALYSIS.md', covers_requirement: false }); }
// Full negative crypto requirements are proven at their closest strong boundary;
// no requirement needing transport/container/client is promoted from pure checks.
if (worker.status === 'PASS') for (const id of ['B02','B04']) { const e=byID.get(id); e.status='PASS'; e.duration_ms=worker.duration_ms; e.upstream_requests=0; e.limitation='Isolated actual RS256 verification, synthetic signed identity/JWKS. No real Actions or upstream effects claimed.'; e.evidence=['evidence/node-contract.tap']; }
const receipts = [];
for (const path of process.argv.slice(2)) {
  const r = await normalizedReceipt(path, tree); receipts.push(path);
  for (const o of r.results) {
    const e=byID.get(o.id); if (!e) throw Error('Unknown matrix ID');
    e.observations.push({ ...o, evidence_kind:r.evidence_kind, receipt:path });
    if (o.status === 'FAIL' || o.covers_requirement && e.status !== 'FAIL') {
      e.status=o.status; e.evidence_kind=r.evidence_kind; e.actual=o.actual; e.duration_ms=o.duration_ms; e.upstream_requests=o.upstream_requests; e.versions=r.versions; e.limitation=o.limitation; e.evidence.push(path);
    }
  }
}
let issues = { status:'NOT RUN', limitation:'Independent issues census/findings and exact integrated-harness technical review not staged in this worktree.' };
try { const files=await readdir('sub2api-spike/issues'); issues={ status:'PENDING REVIEW', files:files.filter(f=>/^(AUDIT\.md|findings\.json)$/.test(f)), limitation:'Issue files preserved; coordinator must review source-version/reproducer linkage before claims are promoted.' }; } catch {}
const counts = Object.fromEntries(['PASS','FAIL','NOT RUN'].map(s=>[s,entries.filter(e=>e.status===s).length]));
const result={ schema:1, generated_at:new Date().toISOString(), scope:'Authorized disposable Sub2API adoption spike; A–H original matrix preserved', counts, worker_verification:worker, versions:entries[0].versions, normalized_operator_receipts:receipts, issues, critical_blockers:['Socket tests denied by sandbox; no transport/container/real Actions receipts.','Source/image pin and measured image/client/database versions require independent provenance.','Engine zero account-switch configuration is ineffective in inspected constructor; uncertain-effect duplicate gate unproven.','Actual-key custody, runner isolation, teardown and test-only OAuth identities pending.'], verdicts:{ BYOK:'CONDITIONAL GO for further isolated evaluation only', subscription_accounts:'NO-GO for adoption until test-only OAuth/lifecycle/isolation evidence', customer_UI:'CONDITIONAL GO private adapter prototype; production SSO/membership remains required' }, results:entries };
await writeFile('sub2api-spike/results.json',JSON.stringify(result,null,2)+'\n');
const embedded=JSON.stringify(result).replace(/</g,'\\u003c');
await writeFile('sub2api-spike/report.html',`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Sub2API — результаты спайка</title><style>body{font:16px system-ui;margin:2rem;color:#192632;background:#f7f9fc}table{border-collapse:collapse;width:100%;background:white}td,th{padding:.7rem;border:1px solid #d8e0eb;text-align:left;vertical-align:top}select{margin:.6rem;padding:.4rem}.PASS{color:#16713c}.FAIL{color:#a32232}#blockers{color:#87312c}small{color:#526078}</style><h1>Sub2API: проверка частного шлюза</h1><p>Локальные проверки и исходный код не доказывают успешный запуск настоящих агентов. Все ошибки сохранены; отсутствующие квитанции оператора отмечены NOT RUN.</p><p id="counts"></p><ul id="blockers"></ul><label>Статус <select id="status"><option value="">Все</option><option>PASS</option><option>FAIL</option><option>NOT RUN</option></select></label><label>Доказательство <select id="kind"><option value="">Все</option><option>contract</option><option>synthetic-upstream</option><option>synthetic-container</option><option>real-Actions</option><option>source-audit</option></select></label><table><thead><tr><th>ID / контракт</th><th>Статус / доказательство</th><th>Наблюдение и ограничения</th></tr></thead><tbody id="rows"></tbody></table><p id="issue"></p><script type="application/json" id="data">${embedded}</script><script>const d=JSON.parse(document.getElementById('data').textContent),s=document.getElementById('status'),k=document.getElementById('kind');document.getElementById('counts').textContent=JSON.stringify(d.counts);document.getElementById('issue').textContent='Независимый аудит: '+d.issues.limitation;for(const b of d.critical_blockers){const e=document.createElement('li');e.textContent=b;document.getElementById('blockers').append(e)}function render(){const rows=document.getElementById('rows');rows.replaceChildren();for(const e of d.results.filter(e=>(!s.value||e.status===s.value)&&(!k.value||e.evidence_kind===k.value))){const tr=document.createElement('tr');for(const text of [e.id+' — '+e.input_expected,e.status+' / '+e.evidence_kind,(typeof e.actual==='string'?e.actual:JSON.stringify(e.actual))+' Ограничения: '+e.limitation+' Запросы upstream: '+e.upstream_requests]){const td=document.createElement('td');td.textContent=text;tr.append(td)}tr.children[1].className=e.status;rows.append(tr)}}s.onchange=k.onchange=render;render();</script></html>`);
console.log(JSON.stringify({ matrix_entries:entries.length,counts,operator_receipts:receipts.length,harness_tree_sha256:tree }));
