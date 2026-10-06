import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { EventEmitter } from 'node:events';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const source = resolve(process.env.CANCEL_CODE ?? `${import.meta.dirname}/.verification/new`);
const code = await readFile(`${source}/sub2api-spike/broker.mjs`, 'utf8');

// Virtual IO: no sockets, provider, filesystem writes, external identity/key/auth operations.
// Execute the exact broker source and native AbortController with deterministic clocks/timers.
async function fixture(protocol, { throws = false, timeoutMs = 30000, ttlMs = 3000 } = {}) {
  let now = 0, server, signal, physicalClose;
  const events = [], timers = [];
  const context = vm.createContext({ URL, Map, Set, WeakMap, Object, Error, AbortController,
    Date: class extends Date { static now() { return 1000000 + now; } },
    process: { pid: 1, hrtime: { bigint: () => BigInt(Math.round(now * 1e6)) } },
    setTimeout(fn, delay) { const t={ fn, delay, at:now+delay, cleared:false, unref() {} }; timers.push(t); return t; },
    clearTimeout(t) { if(t)t.cleared=true; },
    fetch: async (_url, options) => new Promise((_resolve,reject) => {
      signal=options.signal;
      signal.addEventListener('abort', () => { physicalClose=now+0.5; reject(Error('abort')); }, { once:true });
    }),
  });
  const response = () => Object.assign(new EventEmitter(), { writableFinished: false, headersSent:false,
    setHeader(){}, writeHead(){this.headersSent=true;}, destroy(){this.emit('close');} });
  const deps = {
    'node:http': { default:{createServer(_options, handler) { server=Object.assign(new EventEmitter(),{handler}); return server; }} },
    'node:crypto':{randomBytes:()=>({toString:()=> 'fixture-capability'}),randomUUID:()=> 'fixture-session'},
    'node:fs/promises':{mkdir:async()=>{},open:async()=>({writeFile:async()=>{},sync:async()=>{},close:async()=>{}})},
    'node:fs':{unlinkSync(){}},'node:path':{dirname:()=> 'virtual'},
    'node:stream':{Readable:{fromWeb:x=>x}}, 'node:stream/promises':{pipeline:async()=>{}},
    './native-errors.mjs':{nativeErrorFilter:()=>null},
    './util.mjs':{atomicJSON:async()=>{},loadJSON:async()=>({schema:1,runs:{}}),serial:()=>fn=>fn(),
      readJSON:async req=>req.body,send(res,status,data){res.status=status;res.data=data;res.writableFinished=true;res.emit('close');},
      bearer:req=>req.token,fault:(status,code)=>Object.assign(Error(code),{status,code})},
  };
  const mod=new vm.SourceTextModule(code,{context});
  await mod.link(async name=>{const values=deps[name];assert.ok(values,name);const m=new vm.SyntheticModule(Object.keys(values),function(){for(const [k,v] of Object.entries(values))this.setExport(k,v);},{context});await m.link(()=>{});await m.evaluate();return m;});await mod.evaluate();
  await mod.namespace.createBroker({ledgerPath:'virtual/ledger', ttlMs, timeoutMs,
    verifyOIDC:async()=>({runID:'fixture',attempt:'1',expires:2000000}),resolveWorkspace:async()=> 'fixture',
    scopes:{[`synthetic:${protocol}`]:{protocol,model:'fixture-model',baseURL:'http://virtual.invalid',workspaces:{fixture:{key:'nonsecret-fixture',groupID:1}}}},
    observeCancellation(event){events.push({event,abortedAtObservation:signal.aborted,physicalCloseAtObservation:physicalClose});if(throws)throw Error('observer');},
  });
  async function invoke(url,method,body,token='fixture-capability') {
    const req=Object.assign(new EventEmitter(),{url,method,body,token,headers:{},destroy(){this.destroyed=true;}}),res=response();
    const pending=server.handler(req,res);return {req,res,pending};
  }
  const grant=await invoke('/grant','POST',{provider:'synthetic',protocol},'virtual-claims');await grant.pending;
  assert.equal(grant.res.status,200);
  now=40; const stream=await invoke(`/v1/${protocol}`,'POST',{stream:true});
  // Flush only pending Promise reactions, never a wall clock wait.
  for(let i=0;i<12&&!signal;i++)await Promise.resolve();assert.ok(signal);
  return {events,timers,stream,server,signal,invoke,setTime(ms){now=ms;},get physicalClose(){return physicalClose;}};
}
for(const protocol of ['responses','messages']) {
  for(const cause of ['revoke','expiry','request-expiry']) test(`${protocol}: ${cause} observation precedes first actual abort and physical close`,async()=>{
    const f=await fixture(protocol);f.setTime(cause==='revoke'?1000:3000);
    if(cause==='revoke'){const r=await f.invoke('/grant','DELETE');await r.pending;assert.equal(r.res.status,200);}
    else f.timers[cause==='expiry'?0:1].fn();
    await f.stream.pending;
    assert.equal(f.signal.aborted,true);assert.equal(f.events.length,1);
    const {event,abortedAtObservation,physicalCloseAtObservation}=f.events[0];
    assert.equal(abortedAtObservation,false);assert.equal(physicalCloseAtObservation,undefined);
    assert.equal(event.cause,cause);assert.equal(event.dispatch,1);assert.equal(event.protocol,protocol);
    assert.equal(event.clock,'linux-CLOCK_MONOTONIC');assert.equal(event.mono_ms,cause==='revoke'?1000:3000);
    assert.ok(event.mono_ms<f.physicalClose);assert.equal(f.stream.res.status,502);
    // Cleanup and a second expiry callback do not create a second observation.
    f.server.emit('close');assert.equal(f.events.length,1);
  });
}
test('observer exception cannot prevent real cancellation',async()=>{
  const f=await fixture('responses',{throws:true});f.setTime(1000);
  const r=await f.invoke('/grant','DELETE');await r.pending;await f.stream.pending;
  assert.equal(f.signal.aborted,true);assert.ok(f.physicalClose);assert.equal(r.res.status,200);
});
test('request timeout remains distinct from expiry',async()=>{
  const f=await fixture('responses',{timeoutMs:1000,ttlMs:3000});
  assert.equal(f.timers[0].delay,3000);assert.equal(f.timers[1].delay,1000);
  f.setTime(1040);f.timers[1].fn();await f.stream.pending;
  assert.equal(f.events.length,1);assert.equal(f.events[0].event.cause,'timeout');
});
test('downstream close remains distinct from capability cancellation',async()=>{
  const f=await fixture('messages');f.setTime(900);f.stream.res.emit('close');await f.stream.pending;
  assert.equal(f.events.length,1);assert.equal(f.events[0].event.cause,'downstream-close');
});
