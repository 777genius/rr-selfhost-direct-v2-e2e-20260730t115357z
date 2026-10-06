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
async function fixture(protocol, { throws = false, timeoutMs = 30000, ttlMs = 3000, omitObserver = false } = {}) {
  let now = 0, server, signal, physicalClose, member = true;
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
    verifyOIDC:async()=>({runID:'fixture',attempt:'1',expires:2000000}),resolveWorkspace:async()=> 'fixture',isWorkspaceActive:async()=>member,
    scopes:{[`synthetic:${protocol}`]:{protocol,model:'fixture-model',baseURL:'http://virtual.invalid',workspaces:{fixture:{key:'nonsecret-fixture',groupID:1}}}},
    observeCancellation(event){events.push({event,abortedAtObservation:signal.aborted,physicalCloseAtObservation:physicalClose});if(throws)throw Error('observer');}, ...(omitObserver?{observeCancellation:undefined}:{}),
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
  return {events,timers,stream,server,signal,invoke,setTime(ms){now=ms;},setMember(x){member=x;},get physicalClose(){return physicalClose;}};
}

for(const protocol of ['responses','messages']) {
  test(`${protocol}: absent optional observer preserves cancellation`,async()=>{
    const f=await fixture(protocol,{omitObserver:true});f.setTime(1000);
    const r=await f.invoke('/grant','DELETE');await r.pending;await f.stream.pending;
    assert.equal(r.res.status,200);assert.equal(f.signal.aborted,true);assert.ok(f.physicalClose);assert.equal(f.events.length,0);
  });
  for(const cause of ['membership','workspace-revoke','server-close'])test(`${protocol}: ${cause} cancels with diagnostic-only metadata`,async()=>{
    const f=await fixture(protocol);f.setTime(1000);
    if(cause==='membership'){f.setMember(false);const r=await f.invoke('/grant','DELETE');await r.pending;assert.equal(r.res.status,403);}
    if(cause==='workspace-revoke')f.server.revokeWorkspace('fixture');
    if(cause==='server-close')f.server.emit('close');
    await f.stream.pending;assert.equal(f.signal.aborted,true);assert.ok(f.physicalClose);assert.equal(f.events.length,1);
    const e=f.events[0].event;assert.equal(e.cause,cause);assert.equal(Object.isFrozen(e),true);
    assert.deepEqual(Object.keys(e).sort(),['cause','clock','dispatch','mono_ms','protocol']);
    for(const t of f.timers)t.fn();f.server.emit('close');assert.equal(f.events.length,1);
  });
}
