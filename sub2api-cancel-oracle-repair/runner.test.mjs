import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { EventEmitter } from 'node:events';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const own=resolve(import.meta.dirname), source=resolve(process.env.CANCEL_CODE??`${own}/.verification/new`);
let runner=await readFile(`${source}/sub2api-regression-lab/run.mjs`,'utf8');
// Test access only: the body executed is byte-identical to the generated cancellation runner.
runner=runner.replace('async function cancel(', 'export async function cancel(');
let receipts=await readFile(`${source}/sub2api-regression-lab/receipts.mjs`,'utf8');
for(const name of ['common','client'])receipts=receipts.replace(`'./${name}.mjs'`,JSON.stringify(pathToFileURL(resolve(own,`../.spike-inputs/original-inputs/canonical/sub2api-regression-lab/${name}.mjs`)).href));
const {cancellationVerdict}=await import(`data:text/javascript;base64,${Buffer.from(receipts).toString('base64')}`);
const healthy=JSON.parse(await readFile(resolve(own,'../.spike-inputs/original-inputs/actual-faults/cancel-responses-after-revoke.json'),'utf8')).preparation_control;
async function exercise(placement, trigger, expiryCause='expiry', earlyTimer=false) {
  let now=50, server, options, pendingResolve, response, expiryFired=false, deadlineTimerTruncated=false;
  const operations=[], spec={id:`cancel-responses-${placement}-${trigger}`,protocol:'responses',placement,trigger};
  const row={id:spec.id,protocol:spec.protocol,started_ms:0,healthy_control:true,preparation_control:structuredClone(healthy),deployment:{clock:'linux-CLOCK_MONOTONIC'}};
  row.preparation_control.upstream[0].id=`${spec.id}.healthy`;
  const r={sequence:2,id:spec.id,identity:'responses',protocol:'responses',mode:`hold-${placement}`,started_ms:89,effect_ms:90,effects:1,
    first_write_ms:placement==='after'?91:null,first_flush_ms:placement==='after'?92:null,client_ack_ms:null,ack_received_ms:null,
    ack_frame_bytes:0,terminal_ms:null,close_ms:null,release_ms:null,reset_ms:null,finished:false,hold_started_ms:95,hold_until_ms:10095,bytes:placement==='after'?10308:0};
  const d={started_ms:80,http_status:placement==='before'?502:200,transport:placement==='before'?null:'aborted',client_cancel_ms:null,
    client_close_ms:null,ack_ms:null,ack_frame_bytes:0,terminal_ms:null,failed:false,malformed:false};
  const pending={state:{client_cancel_ms:null},promise:new Promise(resolve=>{pendingResolve=resolve;}),cancel(){
    pending.state.client_cancel_ms=now;d.client_cancel_ms=now;d.transport='client_cancel';finish(false);
  }};
  function finish(broker=true,cause=trigger) {
    if(broker)options.observeCancellation?.({protocol:'responses',dispatch:1,cause,mono_ms:now,clock:'linux-CLOCK_MONOTONIC'});
    r.close_ms=now+0.5;d.client_close_ms=now+2;
    if(broker){now++;response.emit('close');}pendingResolve(structuredClone(d));
  }
  function advance(ms){const target=now+Math.max(0,ms);if(trigger==='expiry'&&!expiryFired&&target>=3000){now=3000;expiryFired=true;finish(true,expiryCause);}now=target;}
  const common={mono:()=>now,sleep:async ms=>{if(earlyTimer&&!deadlineTimerTruncated&&ms>1000&&ms<2000){deadlineTimerTruncated=true;advance(ms-0.5);}else advance(ms);},MiB:1048576,must(ok,code){if(!ok)throw Error(code);},save:async()=>{},loadConfig:async()=>{},admin:async()=>{},
    control:async(_c,action,body)=>{operations.push(action);now++;if(action==='ack'){r.client_ack_ms=body.mono_ms;r.ack_received_ms=now;r.ack_frame_bytes=body.frame_bytes;now+=0.01;}return {records:[structuredClone(r)],total:1,effects:1,exceeded:false};},
    fetchJSON:async(_url,method)=>{if(method==='DELETE'){advance(5);finish();return {revoked:true};}return {capability:'virtual-capability',expires:3000};}};
  const deps={
    'node:fs/promises':{mkdir:async()=>{},readFile:async()=>''},'node:crypto':{randomBytes:()=>({toString:()=> 'fixture'})},'node:url':{pathToFileURL},
    '../sub2api-spike/broker.mjs':{createBroker:async opt=>{options=opt;server=Object.assign(new EventEmitter(),{listen(_port,_host,cb){cb();},address:()=>({port:1}),close(cb){cb();},closeAllConnections(){}});return server;}},
    './common.mjs':common,
    './client.mjs':{success:d=>d.http_status===200&&!d.transport&&!d.failed&&!d.malformed&&d.terminal_ms!==null,
      request(_base,_key,_protocol,id,opt){if(id.endsWith('.capacity'))return {promise:Promise.resolve({http_status:trigger==='client'?200:401,terminal_ms:trigger==='client'?10096:null})};
        response=new EventEmitter();server?.emit('request',{url:'/v1/responses'},response);now=100;
        if(placement==='after'){d.ack_ms=now;d.ack_frame_bytes=9465;opt.onAck(now,9465);}return pending;}},
    '../sub2api-transport-r4/adapter.mjs':{telemetryVerdict(){}},
    './wire.mjs':{models:{responses:'fixture-model'},CALL:'fixture-call',TOOL:'fixture-tool'},
    './receipts.mjs':{cancellationVerdict,uncertaintyVerdict(){},telemetryVerdict(){}},'./plan.mjs':{cases:[],budget:{}},
  };
  const context=vm.createContext({console,URL,AbortSignal,process:{argv:[],version:process.version},fetch:async()=>({status:401,body:{cancel:async()=>{}}}),setTimeout,clearTimeout});
  const mod=new vm.SourceTextModule(runner,{context});await mod.link(async name=>{const values=deps[name];assert.ok(values,name);const m=new vm.SyntheticModule(Object.keys(values),function(){for(const[k,v]of Object.entries(values))this.setExport(k,v);},{context});await m.link(()=>{});await m.evaluate();return m;});await mod.evaluate();
  await mod.namespace.cancel({run_id:'fixture',engine_url:'http://virtual.invalid',deadline:90000},spec,{key:'fixture',group:1},row,[]);
  return {row,operations};
}
for(const placement of ['before','after'])for(const trigger of ['client','revoke','expiry'])test(`runner ${placement} ${trigger}: binds real cancellation, physical proof, unchanged hold`,async()=>{
  const {row,operations}=await exercise(placement,trigger);
  assert.equal(row.status,'PASS',row.reason);assert.equal(row.cancel_trigger,trigger);
  assert.equal(row.cancel_ms,trigger==='expiry'?3000:row.action_requested_ms);
  if(trigger==='revoke')assert.ok(row.upstream[0].close_ms<row.broker_boundary_close_ms);
  assert.ok(row.immediate_observation_ms>=row.cancel_ms+1250);assert.ok(row.immediate_observation_ms<10095);
  assert.equal(operations.includes('release'),false);assert.equal(operations.includes('reset'),false);
  assert.equal(row.upstream[0].terminal_ms,null);assert.equal(row.upstream[0].finished,false);
});
test('runner accepts the request expiry timer as the actual expiry trigger',async()=>{
  const {row}=await exercise('after','expiry','request-expiry');assert.equal(row.status,'PASS',row.reason);assert.equal(row.cancel_ms,3000);
});

test('runner waits until the source clock reaches 1250ms when a timer returns early',async()=>{
  const {row}=await exercise('after','revoke','expiry',true);assert.equal(row.status,'PASS',row.reason);
  assert.ok(row.immediate_observation_ms>=row.cancel_ms+1250);
});
