import test from 'node:test';
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {codexNumericEvidence,financialEvidence} from '../.spike-inputs/candidate/sub2api-spike/evidence.mjs';
const execute=promisify(execFile);
const fixture=new URL('../.spike-inputs/candidate/sub2api-spike/fixture/',import.meta.url);
const n={initial_balance:100,amount:-10,final_balance:110};
const f={initial_balance:100,amount:0.5,final_balance:99.5};
const event=(output)=>({type:'item.completed',item:{type:'command_execution',status:'completed',exit_code:0,command:'node --input-type=module -e "import {withdraw} from \'./wallet.mjs\'"',aggregated_output:output}});
test('independent real Node output matches either immediate member and preserves single object',async()=>{
 const {stdout}=await execute(process.execPath,['--input-type=module','-e','import {withdraw} from "./wallet.mjs"; console.log(JSON.stringify([-10,0.5].map(amount=>({initial_balance:100,amount,final_balance:withdraw({balance:100},amount).balance}))));'],{cwd:fixture,timeout:5000});
 assert.deepEqual(JSON.parse(stdout),[n,f]);
 assert.equal(codexNumericEvidence(event(stdout),n),true);assert.equal(codexNumericEvidence(event(stdout),f),true);
 assert.equal(codexNumericEvidence(event(JSON.stringify(n)),n),true);
});
test('independent exact fields cannot be assembled across members or coerced',()=>{
 for(const v of [[{initial_balance:100},{amount:-10},{final_balance:110}],[{...n,amount:0},{...n,initial_balance:99}],[{...n,final_balance:'110'}],[{...n,final_balance:110.000001}],[{...n,amount:null}],[]]) assert.equal(codexNumericEvidence(event(JSON.stringify(v)),n),false);
 for(const key of Object.keys(n)){const bad={...n};delete bad[key];assert.equal(codexNumericEvidence(event(JSON.stringify([bad])),n),false);}
 assert.equal(codexNumericEvidence(event('[{"initial_balance":100,"amount":-10,"final_balance":1e999}]'),n),false);
});
test('independent no recursive or prose extraction',()=>{
 for(const v of [{payload:[n]},[[n]],[{payload:n}],JSON.stringify(n),null,42])assert.equal(codexNumericEvidence(event(JSON.stringify(v)),n),false);
 for(const out of ['prefix '+JSON.stringify([n]),JSON.stringify([n])+' suffix','```json\n'+JSON.stringify([n])+'\n```',JSON.stringify(n)+'\n'+JSON.stringify(f)])assert.equal(codexNumericEvidence(event(out),n),false);
 assert.equal(codexNumericEvidence(event(JSON.stringify([null,[],f,n])),n),true);
});
test('independent failed command and agent/reasoning items cannot prove numbers',()=>{
 const e=event(JSON.stringify([n]));
 for(const change of [{exit_code:1},{exit_code:'0'},{status:'failed'},{type:'agent_message'},{type:'reasoning'},{command:'echo node wallet.mjs withdraw'},{command:'cd /tmp && node wallet.mjs withdraw'}])assert.equal(codexNumericEvidence({...e,item:{...e.item,...change}},n),false);
 for(const type of ['item.started','turn.completed','reasoning'])assert.equal(codexNumericEvidence({...e,type},n),false);
});
test('independent wallet/rules bytes equal sealed constants and canonical fixtures',async()=>{
 for(const [name,hash]of Object.entries({'wallet.mjs':'c47fcdfb32c95bf1ede68c01a3705084a658ecbd2882ab21ca4e8cc5fc658f71','BUSINESS_RULES.md':'1a9837e5e95ee86f22eb171c7bc9ee1226c55ff859973ad573417feb6aae43a5'})){
 const bytes=await readFile(new URL(name,fixture));assert.equal(createHash('sha256').update(bytes).digest('hex'),hash);
 assert.deepEqual(bytes,await readFile(new URL('../gateway-spike/fixture/'+name,import.meta.url)));
 }
});
test('independent financial contract still requires separate successful reads and genuine terminal',async()=>{
 const read=(command,aggregated_output)=>({...event(aggregated_output),item:{...event(aggregated_output).item,command}});
 const events=[read('cat wallet.mjs',await readFile(new URL('wallet.mjs',fixture),'utf8')),read('cat BUSINESS_RULES.md',await readFile(new URL('BUSINESS_RULES.md',fixture),'utf8')),{type:'turn.completed'}];
 const review=JSON.stringify({findings:[{file:'wallet.mjs',function:'withdraw',summary:'negative withdrawal increases balance',example:n}]});
 assert.equal(financialEvidence('codex',events,review,'mimo').terminal_verified,true);
 for(const selection of [events.slice(0,2),events.slice(1),[events[0],events[2]],[...events,{type:'turn.failed'}],[{...events[0],item:{...events[0].item,command:'cat wallet.mjs BUSINESS_RULES.md'}},...events.slice(1)]])assert.throws(()=>financialEvidence('codex',selection,review,'mimo'));
 for(const bad of ['',JSON.stringify({findings:[]}),JSON.stringify({findings:[{file:'wallet.mjs',function:'withdraw',summary:'',example:n}]})])assert.throws(()=>financialEvidence('codex',events,bad,'mimo'));
});
