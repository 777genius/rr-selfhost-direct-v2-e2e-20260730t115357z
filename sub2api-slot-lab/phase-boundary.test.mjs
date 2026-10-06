import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
const base=resolve('fullsub2api-slot-lab');
async function exercise({retry=false,finish=0,supervisor=1200000}={}) {
 let now=0,serial=0,login=0,models=0,posts=0,activeDeadline;const objects={},saved=new Map();
 const old={fetch:globalThis.fetch,clock:process.hrtime.bigint,timer:globalThis.setTimeout};
 process.hrtime.bigint=()=>BigInt(now*1e6);
 globalThis.setTimeout=(fn,ms,...args)=>{now+=ms;queueMicrotask(()=>fn(...args));return 0;};
 const reply=(data,status=200)=>({ok:status===200,status,headers:new Headers({'Retry-After':'60'}),arrayBuffer:async()=>Buffer.from(JSON.stringify(data))});
 globalThis.fetch=async(url,o)=>{
  const route=new URL(url).pathname.replace('/api/v1','');
  if(route.startsWith('/__lab/'))return reply({total:0,effects:0,records:[],rejections:[],exceeded:false});
  if(route==='/auth/login') {if(retry&&++login===1)return reply({error:'rate limit exceeded',message:'Too many requests, please try again later'},429);if(retry)now+=5000;return reply({code:0,data:{access_token:'synthetic-token'}});}
  if(o.method==='DELETE')return reply({code:0,data:{}});
  const kind=route.split('/')[2]??'keys';
  if(o.method==='POST') {posts++;const body=JSON.parse(o.body),obj={...body,id:++serial,status:'active'};if(route==='/keys'){obj.key='synthetic-native-key';obj.user_id=objects.users.id;objects.keys=obj;}else objects[kind]=obj;return reply({code:0,data:obj});}
  if(route.startsWith('/keys/')) {if(finish)now=finish;return reply({code:0,data:objects.keys});}
  return reply({code:0,data:objects[kind]});
 };
 const synthetic=exports=>new vm.SyntheticModule(Object.keys(exports),function(){for(const [k,v] of Object.entries(exports))this.setExport(k,v);});
 const cache=new Map();
 async function load(path){if(cache.has(path))return cache.get(path);let source=await readFile(path,'utf8');
  if(path.endsWith('/common.mjs'))source=source.replace(/export async function save\([\s\S]*?\n}/, 'export async function save(path,data) { globalThis.__phaseSave(path,data); }');
  if(path.endsWith('/run.mjs'))source+='\nexport { cycle };';
  const m=new vm.SourceTextModule(source,{identifier:path});cache.set(path,m);
  await m.link(async(spec,parent)=>{
   if(spec.endsWith('/client.mjs'))return synthetic({request:()=>{models++;activeDeadline=config.deadline;throw Object.assign(Error('MODEL_BOUNDARY'),{code:'MODEL_BOUNDARY'});},success:()=>false});
   if(spec.endsWith('/wire.mjs'))return synthetic({models:{responses:'synthetic-model',messages:'synthetic-model'}});
   if(spec.startsWith('node:'))return synthetic(await import(spec));
   return load(resolve(dirname(parent.identifier),spec));
  });return m;
 }
 globalThis.__phaseSave=(path,data)=>saved.set(path,structuredClone(data));
 const config={engine_url:'http://sub2api:8080',mock_url:'https://mock:8099',admin_bearer:'synthetic',sentinels:{responses:'synthetic'},supervisor_deadline:supervisor};
 const zero={started_ms:0,observed_ms:0,...Object.fromEntries(['user','account','key','userWait','accountWait'].map(k=>[k,{count:0,members:[],ttl_ms:-2}]))};
 try {const run=await load(resolve(process.env.SLOT_PHASE_OLD==='1'?'.spike-inputs/candidate/sub2api-slot-lab/run.mjs':`${base}/run.mjs`));await run.evaluate();const row=await run.namespace.cycle(config,{id:'offline.responses.account.default',protocol:'responses',lane:'account',optin:false},{snapshot:async()=>zero});return {row,models,posts,activeDeadline};}
 finally {globalThis.fetch=old.fetch;globalThis.setTimeout=old.timer;process.hrtime.bigint=old.clock;delete globalThis.__phaseSave;}
}
test('native Retry-After60 plus 5s response fits setup and receives full 35s active',async()=>{const x=await exercise({retry:true});assert.equal(x.models,1,JSON.stringify(x.row));assert.equal(x.row.fixture.end_ms,65000);assert.equal(x.row.fixture.deadline_ms,70000);assert.equal(x.row.native_cycle.start_ms,65000);assert.equal(x.activeDeadline,100000);assert.equal(x.row.reason,'MODEL_BOUNDARY');assert.equal(x.row.cleanup.failures,0);});
test('no retry also receives full active period from setup completion',async()=>{const x=await exercise({finish:4321});assert.equal(x.models,1,JSON.stringify(x.row));assert.equal(x.activeDeadline,39321);assert.equal(x.row.native_cycle.start_ms,4321);});
test('supervisor cannot admit required phases: zero fixture creation and zero inference',async()=>{const x=await exercise({supervisor:104999});assert.equal(x.models,0);assert.equal(x.posts,0);assert.equal(x.row.reason,'SUPERVISOR_DEADLINE');assert.equal(x.row.cleanup.failures,0);});
for(const finish of [70000,70001])test(`successful readback at ${finish} fails before inference`,async()=>{const x=await exercise({finish});assert.equal(x.models,0);assert.equal(x.row.reason,'FIXTURE_DEADLINE');assert.equal(x.row.native_cycle,undefined);assert.equal(x.row.cleanup.failures,0);assert.deepEqual(x.row.cleanup.remaining,[]);});
