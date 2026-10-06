import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
const runtime = resolve(process.env.SLOT_SETUP_RUNTIME ?? 'sub2api-slot-lab/w7-runtime');
const side = process.env.SLOT_SETUP_OLD === '1' ? 'adapter-old.mjs' : 'adapter.mjs';
const { setup, cleanup } = await import(`${runtime}/sub2api-slot-lab/${side}`);
const native = {error:'rate limit exceeded',message:'Too many requests, please try again later'};
const response = (status, data) => ({status,ok:status===200,headers:new Headers({'Retry-After':'1'}),arrayBuffer:async()=>Buffer.from(JSON.stringify(data))});
async function fixture(check, failRoute) {
 const temporary = await mkdtemp(resolve('sub2api-slot-lab/w7-evidence/setup-'));
 const saved = {fetch:globalThis.fetch,clock:process.hrtime.bigint,timer:globalThis.setTimeout};
 let now=0, id=0, logins=0;const calls=[], waits=[], objects={};
 const journal={path:`${temporary}/private-journal.json`,resources:[],intent:null};
 process.hrtime.bigint=()=>BigInt(now*1e6);
 globalThis.setTimeout=(fn,ms,...args)=>{waits.push(ms);now+=ms;queueMicrotask(()=>fn(...args));return 0;};
 globalThis.fetch=async(url,o)=>{
  const route=new URL(url).pathname.replace('/api/v1','');const body=o.body&&JSON.parse(o.body);
  calls.push({route,method:o.method,body,at:now});
  assert.equal(o.redirect,'error');assert.ok(o.signal instanceof AbortSignal);
  if(route===failRoute && o.method==='POST')return response(429,native);
  if(route==='/auth/login') {logins++;return logins===1?response(429,native):response(200,{code:0,data:{access_token:'fixture-user'}});}
  if(o.method==='POST') {
   const disk=JSON.parse(await readFile(journal.path,'utf8'));assert.equal(disk.intent.kind,route.split('/').at(-1));
   const kind=route.split('/').at(-1),data={...body,id:++id,status:'active'};
   if(kind==='keys'){data.key='synthetic-native-key';data.user_id=objects.users.id;assert.equal(o.headers.authorization,'Bearer fixture-user');}
   objects[kind]=data;return response(200,{code:0,data});
  }
  if(o.method==='DELETE')return response(200,{code:0,data:{}});
  return response(200,{code:0,data:objects[route.split('/').at(-2)]});
 };
 const c={engine_url:'http://sub2api:8080',mock_url:'https://mock:8099',admin_bearer:'synthetic-admin-token',sentinels:{responses:'synthetic-provider-sentinel'},deadline:35000,supervisor_deadline:1200000};
 const spec={id:'offline.responses.account.default',protocol:'responses',lane:'account',optin:false};
 try {await check(()=>setup(c,spec,journal),calls,waits,journal,c);} finally {Object.assign(globalThis,{fetch:saved.fetch,setTimeout:saved.timer});process.hrtime.bigint=saved.clock;await rm(temporary,{recursive:true,force:true});}
}
test('actual setup retries only native login and preserves default binding, private custody and cleanup',async()=>fixture(async(run,calls,waits,journal,c)=>{
 const tenant=await run();assert.deepEqual(waits,[1000]);assert.deepEqual(calls.filter(c=>c.route==='/auth/login').map(c=>c.at),[0,1000]);
 const loginCalls=calls.filter(c=>c.route==='/auth/login');assert.deepEqual(loginCalls[0].body,loginCalls[1].body);
 for(const route of ['/admin/groups','/admin/accounts','/admin/users','/keys'])assert.equal(calls.filter(c=>c.route===route&&c.method==='POST').length,1);
 const account=calls.find(c=>c.route==='/admin/accounts').body;assert.equal(Object.hasOwn(account.extra,'native_api_key_cancel_on_disconnect'),false);assert.equal(account.credentials.pool_mode_retry_count,0);
 const disk=JSON.parse(await readFile(journal.path,'utf8'));assert.equal(disk.user_token,'fixture-user');assert.equal(disk.native_key,tenant.key);assert.equal(disk.intent,null);assert.equal(disk.resources.length,4);
 assert.equal(c.deadline,35000);assert.equal(c.supervisor_deadline,1200000);
 assert.deepEqual(await cleanup(c,journal),{failures:0,ambiguous_intent:false,remaining:[]});
 assert.equal(calls.some(c=>c.route.includes('/responses')||c.route.includes('/messages')),false);
}));
for(const route of ['/admin/groups','/admin/accounts','/admin/users','/keys'])test(`actual setup never retries ${route} POST429`,async()=>fixture(async(run,calls,waits,journal)=>{
 await assert.rejects(run(),/CONTROL_OR_ADMIN_REJECTED/);assert.equal(calls.filter(c=>c.route===route&&c.method==='POST').length,1);
 assert.equal(journal.intent.kind,route.split('/').at(-1));
 assert.equal(waits.length,route==='/keys'?1:0);
},route));
