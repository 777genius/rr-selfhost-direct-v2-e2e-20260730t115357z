// Root-only sandbox adapter. Existing production-path setup/load/cleanup functions
// are exported in the disposable code copy; no accounts recreated per burst.
import { readFile } from 'node:fs/promises';
import { loadConfig, save, mono, must, control } from '../sub2api-regression-lab/common.mjs';
import { setup, load, cleanup } from '../sub2api-regression-lab/run.mjs';
const json = async p => JSON.parse(await readFile(p,'utf8'));
const path = '/private/profile-owned.json';
async function main() {
  const c = await loadConfig(); c.deadline = (await json('/private/supervisor.json')).deadline_ms;
  const mode = process.argv[2];
  if (mode === 'setup') {
    const owned = {path,intent:null,resources:[]}; await save(path,owned,true);
    const spec = {id:'profile-warmup',protocol:process.argv[3],stage:'memory',streams:5,mib:8};
    const row = {id:spec.id,protocol:spec.protocol};
    const tenant = await setup(c,spec,row,owned);
    await save('/private/profile-tenant.json',tenant,true);
    row.resources = owned.resources.map(({kind,id})=>({kind,id}));
    row.preparation_state = await control(c,'state');
    must(!row.preparation_state.exceeded && row.preparation_state.active===0 && row.preparation_state.records.every(r=>r.identity!=='UNKNOWN'),'SETUP_EFFECT_AMBIGUITY');
    row.setup_finished_ms = mono();
    await save('/evidence/setup.json',row,true); return;
  }
  const owned = await json(path);
  if (mode === 'cleanup') {
    await save('/evidence/account-cleanup.json',await cleanup(c,owned),true); return;
  }
  if (mode === 'state') { await save('/evidence/mock-final.json',await control(c,'state')); return; }
  must(mode==='burst','EXPLICIT_MODE_REQUIRED');
  c.deadline = Math.min(c.deadline,mono()+85000);
  const spec = await json('/private/burst.json');
  must(spec.stage==='memory' && spec.mib===8 && [1,5,20].includes(spec.streams) && spec.count===spec.streams,'FROZEN_VOLUME_AND_COUNT');
  must(Array.isArray(spec.request_ids) && spec.request_ids.length===spec.streams && new Set(spec.request_ids).size===spec.streams && spec.request_ids.every((id,j)=>id===`${spec.id}.r${String(j+1).padStart(2,'0')}`),'EXACT_REQUEST_IDS');
  must(mono()+15000<c.deadline,'FULL_BURST_RESERVE_REQUIRED');
  const tenant = await json('/private/profile-tenant.json');
  const clients=[]; const before=await control(c,'state');
  const row={id:spec.id,protocol:spec.protocol,started_ms:mono(),evidence_kind:'distinct-instrumented-binary/synthetic-upstream',
    dedicated_resources:owned.resources.map(({kind,id})=>({kind,id})),live_provider:false};
  try { await load(c,spec,tenant,row,clients); }
  catch(e) { row.functional_status='FAIL'; row.reason=e.labCode??'BURST_EXCEPTION'; row.stop_required=true; }
  finally {
    for(const p of clients)p.cancel();
    for(const id of spec.request_ids)await control(c,'stop',{id}).catch(()=>{row.stop_control_failed=true;});
    const state=await control(c,'state').catch(()=>null);
    if(state) {
      row.upstream=state.records.filter(r=>spec.request_ids.includes(r.id));
      row.upstream_attempts_total=state.total-before.total;
      row.upstream_effects_total=state.effects-before.effects;
      row.active_at_boundary=state.active;
      row.unknown_identity=state.records.some(r=>r.identity==='UNKNOWN');
      row.exceeded=state.exceeded;
      row.attempt_sequences=row.upstream.map(r=>r.sequence);
    } else row.state_unavailable=true;
    row.ended_ms=mono();
    // Empirical return FAIL is kept in full. It does not erase functional results
    // or prevent further bounded diagnostic bursts. Safety/identity/volume FAIL
    // stops admission. No reliability acceptance is inferred from diagnosis.
    row.stop_required ||= row.functional_status!=='PASS' || row.safety_stop || row.stop_control_failed ||
      row.state_unavailable || row.unknown_identity || row.exceeded || row.active_at_boundary!==0 ||
      row.upstream?.length!==spec.streams || row.upstream_attempts_total!==spec.streams || row.upstream_effects_total!==spec.streams ||
      !['PASS','FAIL'].includes(row.memory_envelope?.empirical_qualified_status);
    await save(`/evidence/${spec.id}.json`,row,true);
  }
  if(row.stop_required)process.exitCode=1;
}
main().catch(()=>{process.stderr.write('PROFILE_ADAPTER_STOP\n');process.exitCode=1;});
