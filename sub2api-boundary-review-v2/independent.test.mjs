import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {customerAdapter,AdminAPI} from './disposable/boundary/sub2api-spike/customer.mjs';
import {bindGrantedRun} from './disposable/provenance/sub2api-spike/granted-run.mjs';
import {verifier,token,workflowSHA} from './disposable/provenance/sub2api-spike/test-support.mjs';
const selection={provider:'mimo',protocol:'responses'}, identity={workspace:'a',user:'u'};
const clone=structuredClone;
async function fixture(t,{at,uncertain=false,unknown=false,foreign=false}={}) {
 const dir=await mkdtemp(new URL('./disposable/state-',import.meta.url).pathname);t.after(()=>rm(dir,{recursive:true,force:true}));
 const statePath=join(dir,'state.json');
 const workspaces={a:{members:{u:'owner'},groups:{'mimo:responses':11},quarantineTemplates:{'mimo:responses':101}}};
 const credentials={a:{'mimo:responses':'inert-only'}};
 let template={id:101,name:'rr-sub2-spike-20260930-template',platform:'openai',type:'apikey',status:'inactive',schedulable:false,credentials:null,extra:{rr_quarantine_template:{workspace:'a',...selection},openai_disable_capability_probe:true}};
 let account,duplicates=0,revocations=0;const writes=[];
 const admin=new AdminAPI({baseURL:'https://unused.invalid',adminKey:'inert-only'});
 admin.call=async(method,path,body)=>{
  if(path==='/accounts/101'&&method==='GET')return clone(template);
  if(path==='/accounts/101'&&method==='PUT'){template={...template,...clone(body)};delete template.group_ids;writes.push({stage:'prepare',body:clone(body)});return clone(template);}
  if(path==='/accounts/101/duplicate'){
   duplicates++;account={...clone(template),id:202,name:template.name+' (Copy)',status:'active'};
   if(unknown)throw Error('ambiguous acknowledgement');
   if(uncertain) return {...clone(account),group_ids:[99],schedulable:true};
   return clone(account);
  }
  if(path.startsWith('/accounts?page='))return {items:[clone(account)],total:1};
  if(method==='GET') {if(foreign) return {...clone(account),name:'foreign'};return clone(account);}
  writes.push({path,method,body:clone(body)});
  if(method==='DELETE')return {};
  Object.assign(account,clone(body));
  if(Array.isArray(account.group_ids)&&!account.group_ids.length)delete account.group_ids;
  const stage=body?.schedulable===true?'schedule':body?.group_ids?.length?'attach':body?.status==='active'?'activate':null;
  if(stage===at)workspaces.a.groups['mimo:responses']=22;
  return clone(account);
 };
 const adapter=await customerAdapter({statePath,admin,workspaces,credentialProfiles:credentials,onAuthorityChange:async()=>{revocations++;}});
 return {adapter,workspaces,writes,statePath,get account(){return account},get template(){return template},get duplicates(){return duplicates},get revocations(){return revocations}};
}
test('BR01 independent full stock omitted slices pass connect and unknown-ack retirement',async t=>{
 for(const unknown of [false,true]){
 const r=await fixture(t,{unknown});
 if(unknown){await assert.rejects(r.adapter.operate(identity,'connect',null,selection));const [b]=await r.adapter.recovery();assert.equal(b.upstreamID,null);assert.deepEqual(await r.adapter.reconcile(identity,b.id,'retire'),{retired:true});}
 else {const result=await r.adapter.operate(identity,'connect',null,selection);assert.equal(result.status,'active');assert.equal(r.account.schedulable,true);assert.deepEqual(r.account.group_ids,[11]);}
 assert.equal(r.duplicates,1);
 }
});
test('BR03 independent remap at each promotion acknowledgement compensates before publication',async t=>{
 for(const at of ['attach','activate','schedule']){
 const r=await fixture(t,{at});await assert.rejects(r.adapter.operate(identity,'connect',null,selection),{code:'authority_changed'});
 assert.equal(r.account.schedulable,false);assert.equal(r.account.status,'inactive');assert.equal(r.account.group_ids,undefined);assert.equal(r.duplicates,1);
 }
});
test('owned malformed acknowledgement retains ID and quarantines; reused foreign ID fences without writes',async t=>{
 for(const foreign of [false,true]){
 const r=await fixture(t,{uncertain:true,foreign});await assert.rejects(r.adapter.operate(identity,'connect',null,selection),{code:'quarantine_invalid'});
 const [b]=await r.adapter.recovery();assert.equal(b.upstreamID,202);const disk=JSON.parse(await readFile(r.statePath));
 if(foreign){assert.equal(r.writes.filter(x=>x.path).length,0);assert.equal(r.workspaces.a.suspended,true);assert.equal(disk.bindings[b.id].fenced,true);assert.equal(r.revocations,1);}
 else{assert.equal(r.account.schedulable,false);assert.equal(r.account.status,'inactive');assert.equal(r.account.group_ids,undefined);}
 }
});
test('BR02 integration contract: preparation must preserve explicit trusted probe-disable',async t=>{
 const r=await fixture(t);await r.adapter.operate(identity,'connect',null,selection);
 assert.equal(r.writes.find(x=>x.stage==='prepare').body.extra.openai_disable_capability_probe,true);
});
test('BR04 independently selected grant identity denies all supported cross-selection changes',async()=>{
 const c=await verifier()(token());
 for(const [provider,agent,protocol] of [['mimo','codex','responses'],['mimo','claude','messages'],['openrouter','codex','responses']]){
 const grant={...c,provider,protocol};const runtime={...c,provider,agent};
 const receipt=bindGrantedRun(grant,runtime);assert.deepEqual(Object.keys(receipt).sort(),['attempt','protocol','provider','runID','workflowSHA']);assert.equal(Object.isFrozen(receipt),true);
 for(const change of [{runID:'999'},{attempt:'9'},{workflowSHA:'b'.repeat(40)},{provider:'unknown'},{agent:'unknown'}])assert.throws(()=>bindGrantedRun(grant,{...runtime,...change}));
 }
 assert.equal(c.workflowSHA,workflowSHA);
});
