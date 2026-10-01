import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const MiB=1048576;
const source=readFileSync(process.env.RR_LOAD_SOURCE || new URL('../.spike-inputs/candidate/sub2api-transport-r4/overlay/sub2api-regression-lab/run.mjs',import.meta.url),'utf8');
const start=source.indexOf('async function load('),end=source.indexOf('async function runOne(');
assert.ok(start>=0&&end>start);
async function run({protocol='messages',mib=8,streams=1,count=streams,stage='memory',side,field,value}={}){
 let clock=1100,index=0;
 const ready={schema:'raw-observation-v2',fresh_container_inspected:true,engine_pid:42,instance:'independent-r5',container_id:'a'.repeat(64)};
 const results=Array.from({length:count},()=>({http_status:200,transport:null,failed:false,malformed:false,terminal_ms:1200,bytes:mib*MiB,text_delta_bytes:5000,tool_id:'owned-fixture',comments:1,duration_ms:10,max_frame_bytes:1992295}));
 const receipts=Array.from({length:count},()=>({bytes:mib*MiB,effects:1,finished:true,identity:protocol,close_ms:1300}));
 if(side)(side==='downstream'?results:receipts)[count-1][field]=value;
 const context={MiB,readFile:async()=>JSON.stringify(ready),must:(ok,message)=>assert.ok(ok,message),mono:()=>clock,save:async()=>{},out:'virtual',setInterval:()=>1,clearInterval:()=>{},telemetry:async()=>[],telemetryVerdict:()=>({status:'NOT RUN',empirical_qualified_status:'NOT RUN',physical_interval_rss_status:'NOTPROVEN'}),control:async()=>{},request:()=>({promise:Promise.resolve(results[index++]),cancel(){}}),success:r=>r.http_status===200&&!r.transport&&!r.failed&&!r.malformed&&r.terminal_ms!==null,waitFor:async()=>receipts,sleep:async ms=>{clock+=ms}};
 const row={};await vm.runInNewContext(`(${source.slice(start,end)})`,context)({deadline:100000,observed:ready},{id:'independent',stage,protocol,mib,streams,...(stage==='soak'?{count}:{})},{key:'offline'},row,[]);return row;
}
test('all 18 matrix cells: one corrupted receipt rejects both signs and both wire sides',async()=>{
 let checks=0;for(const protocol of ['responses','messages'])for(const mib of [8,32,64])for(const streams of [1,5,20]){
  const args={protocol,mib,streams};const good=await run(args);assert.equal(good.functional_status,'PASS');assert.equal(good.downstream.bytes,mib*MiB*streams);assert.equal(good.acceptance_status,'NOT RUN');
  for(const side of ['upstream','downstream'])for(const delta of [-1,1]){const bad=await run({...args,side,field:'bytes',value:mib*MiB+delta});assert.equal(bad.functional_status,'FAIL');assert.equal(bad.acceptance_status,'FAIL');checks++;}
 }console.log(JSON.stringify({independent_single_corrupted_volume_checks:checks}));
});
test('all numeric fields: JSON coercion canaries in a mixed five-stream batch fail closed',async()=>{
 let checks=0;const invalid=['null','true','false','"10"','[]','[10]','{}','{"value":10}','1e400','-1'];
 for(const [side,fields] of [['downstream',['bytes','text_delta_bytes','max_frame_bytes','comments','duration_ms','terminal_ms']],['upstream',['bytes','effects','close_ms']]])for(const field of fields)for(const raw of invalid){
  const row=await run({streams:5,side,field,value:JSON.parse(raw)});assert.equal(row.functional_status,'FAIL',side+field+raw);assert.equal(row.acceptance_status,'FAIL');if(side==='downstream'){assert.equal(row.downstream.bytes,null);assert.equal(row.downstream.max_frame_bytes,null);}checks++;
 }console.log(JSON.stringify({independent_mixed_numeric_checks:checks}));
});
test('frame boundaries and actual protocol-conversion frame loss fail',async()=>{
 for(const [value,status] of [[1992294,'FAIL'],[1992295,'PASS'],[2097151,'PASS'],[2097152,'FAIL'],[5000,'FAIL'],[2008693,'PASS'],[1998992,'PASS']])assert.equal((await run({side:'downstream',field:'max_frame_bytes',value})).functional_status,status);
});
test('fractional/unsafe counters reject, fractional finite durations pass, synthetic soak retains no physical green',async()=>{
 for(const [side,fields] of [['downstream',['bytes','text_delta_bytes','max_frame_bytes','comments']],['upstream',['bytes','effects']]])for(const field of fields)for(const value of [0.5,9007199254740992])assert.equal((await run({side,field,value})).functional_status,'FAIL');
 for(const [side,field] of [['downstream','duration_ms'],['downstream','terminal_ms'],['upstream','close_ms']])assert.equal((await run({side,field,value:0.5})).functional_status,'PASS');
 const row=await run({stage:'soak',streams:5,count:250});assert.equal(row.functional_status,'PASS');assert.equal(row.downstream.requests,250);assert.equal(row.acceptance_status,'NOT RUN');assert.equal(row.memory_envelope.physical_interval_rss_status,'NOTPROVEN');
});
