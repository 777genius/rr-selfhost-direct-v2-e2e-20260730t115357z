import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {telemetryVerdict} from './adapter.mjs';
import {cases} from './historical-input/prior-code/sub2api-regression-lab/plan.mjs';
const MiB=1048576;
const source=readFileSync(new URL('./overlay/sub2api-regression-lab/run.mjs',import.meta.url),'utf8');
const actualLoad=source.slice(source.indexOf('async function load('),source.indexOf('async function runOne('));
async function exercise({extra=0,upstreamBytes=8*MiB,overrides={}}={}) {
  let now=1100;
  const ready={schema:'raw-observation-v2',fresh_container_inspected:true,engine_pid:42,instance:'fixture',container_id:'a'.repeat(64)};
  const row={},upstream=[{effects:1,finished:true,identity:'messages',close_ms:1000,bytes:upstreamBytes}];
  const result={http_status:200,transport:null,failed:false,malformed:false,terminal_ms:1200,bytes:8*MiB+extra,text_delta_bytes:5000,tool_id:'toolu_rr_transport_01',comments:1,duration_ms:10,max_frame_bytes:1992295,...overrides};
  const context={readFile:async()=>JSON.stringify(ready),must:(ok,reason)=>{if(!ok)throw Error(reason)},mono:()=>now,save:async()=>{},out:'owned-virtual-evidence',setInterval:()=>1,clearInterval:()=>{},telemetry:async()=>[],telemetryVerdict:()=>({status:'NOT RUN',empirical_qualified_status:'NOT RUN',physical_interval_rss_status:'NOTPROVEN'}),control:async()=>{},request:()=>({promise:Promise.resolve(result),cancel(){}}),success:r=>r.http_status===200&&!r.transport&&!r.failed&&!r.malformed&&r.terminal_ms!==null,waitFor:async()=>upstream,sleep:async ms=>{now+=ms},MiB};
  const load=vm.runInNewContext(`(${actualLoad})`,context);
  await load({deadline:100000,observed:{engine_pid:42,instance:'fixture',container_id:ready.container_id}}, {id:'memory-messages-8-1',stage:'memory',protocol:'messages',mib:8,streams:1},{key:'fixture-only'},row,[]);
  return row;
}
test('actual load driver accepts exact-volume valid control',async()=>assert.equal((await exercise()).functional_status,'PASS'));
test('REGRESSION: actual load driver must reject one extra downstream byte',async()=>assert.equal((await exercise({extra:1})).functional_status,'FAIL'));
test('REGRESSION: actual load driver must reject upstream byte loss despite downstream padding',async()=>assert.equal((await exercise({upstreamBytes:8*MiB-1})).functional_status,'FAIL'));
test('REGRESSION: actual load driver must reject missing near2MiB frame',async()=>assert.equal((await exercise({overrides:{max_frame_bytes:5000}})).functional_status,'FAIL'));
test('REGRESSION: actual load driver must reject numeric array byte canary',async()=>assert.equal((await exercise({overrides:{bytes:[8*MiB]}})).functional_status,'FAIL'));
test('actual load driver rejects numeric object byte canary',async()=>assert.equal((await exercise({overrides:{bytes:{value:8*MiB}}})).functional_status,'FAIL'));
test('40case matrix contains exact cross product and two 250-request soaks',()=>{
 assert.equal(cases.length,40);assert.equal(cases.filter(c=>c.stage==='cancel').length,12);assert.equal(cases.filter(c=>c.stage==='uncertainty').length,8);
 assert.equal(cases.filter(c=>c.stage==='memory').length,18);assert.deepEqual(cases.filter(c=>c.stage==='soak').map(c=>c.count),[250,250]);
});
test('adapter rejects JSON numeric objects and arrays without coercion',()=>{
 const identity={instance:'fixture',engine_pid:42,pid_start_ticks:10,cgroup_path:'/fixture',cgroup_device:1,cgroup_inode:2,container_id:'a'.repeat(64),exe_device:3,exe_inode:4};
 const meta={...identity,id:'memory-messages-8-1',streams:1,started_ms:1100,ended_ms:1300};
 const samples=Array.from({length:55},(_,i)=>({...identity,schema:'raw-observation-v2',batch_id:meta.id,collector:'root-go-pid',clock:'linux-CLOCK_MONOTONIC',mono_ms:1000+i*100,sample_started_ms:999+i*100,sample_duration_ms:1,phase:i===0?'baseline':1000+i*100<1300?'active':'quiescent',rss_bytes:100*MiB,raw_vm_hwm_bytes:100*MiB,smaps_rollup_rss_bytes:100*MiB,mapped_virtual_extent_bytes:1024*MiB,mapped_external_candidate_extent_bytes:50*MiB,maps_count:3,maps_sha256:'b'.repeat(64),rss_kind:'raw-proc-status-approximate',smaps_kind:'page-table-walk-observation-not-interval-peak',maps_kind:'observed-virtual-extents-not-continuous-bound',physical_interval_rss_upper_bound_bytes:null,cgroup_current_bytes:30*MiB,cgroup_peak_bytes:60*MiB,cgroup_limit_bytes:768*MiB,sockets:2,goroutines:null,goroutines_source:'unavailable-instantaneous'}));
 const ready={...identity,schema:'raw-observation-v2',fresh_container_inspected:true,container_created_ms:800,pid_created_ms:900,first_ready_ms:1000,first_sample:{...samples[0]}};
 const done={...identity,schema:ready.schema,batch_id:meta.id,status:'DONE',ended_ms:1300,last_sample_ms:6400,full_tail_ms:5099};
 const evaluate=()=>telemetryVerdict(samples,meta,ready,{done});
 assert.equal(evaluate().empirical_qualified_status,'PASS');assert.equal(evaluate().physical_interval_rss_status,'NOTPROVEN');assert.equal(evaluate().status,'NOT RUN');
 for(const field of ['rss_bytes','raw_vm_hwm_bytes','smaps_rollup_rss_bytes','mono_ms','sample_started_ms','sample_duration_ms','maps_count','sockets','cgroup_current_bytes','cgroup_peak_bytes'])for(const value of [{value:1},[1],[],{},'1',null]){
  const original=samples[1][field];samples[1][field]=value;assert.equal(evaluate().empirical_qualified_status,'NOT RUN',field+JSON.stringify(value));samples[1][field]=original;
 }
});
