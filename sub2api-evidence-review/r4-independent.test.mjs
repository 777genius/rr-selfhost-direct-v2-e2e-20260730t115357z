import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {codexNumericEvidence as candidate, financialEvidence} from '../.spike-inputs/candidate/sub2api-spike/evidence.mjs';
import {codexNumericEvidence as canonical} from '../sub2api-spike/evidence.mjs';
const fixture=new URL('../.spike-inputs/candidate/sub2api-spike/fixture/',import.meta.url);
const a={initial_balance:1000,amount:-50,final_balance:1050}, b={initial_balance:1000,amount:25.5,final_balance:974.5};
const cmd='node --input-type=module -e "import {withdraw} from \'./wallet.mjs\'"';
const ev=output=>({type:'item.completed',item:{type:'command_execution',command:cmd,status:'completed',exit_code:0,aggregated_output:output}});
const jsonl=[a,b].map(JSON.stringify).join('\n');
test('real wallet Node stdout object array JSONL and actual baseline rejection',()=>{
 const expr=`import {withdraw} from './wallet.mjs';const rows=${JSON.stringify([a,b])}.map(x=>({...x,final_balance:withdraw({balance:x.initial_balance},x.amount).balance}));console.log(JSON.stringify(rows));for(const x of rows)console.log(JSON.stringify(x));`;
 const out=execFileSync(process.execPath,['--input-type=module','-e',expr],{cwd:fixture,encoding:'utf8',timeout:5000});
 const [array,...rows]=out.trimEnd().split('\n');assert.deepEqual(JSON.parse(array),[a,b]);assert.equal(rows.join('\n'),jsonl);
 for(const x of [a,b]){assert.equal(candidate(ev(array),x),true);assert.equal(candidate(ev(rows.join('\n')),x),true);assert.equal(canonical(ev(rows.join('\n')),x),false);assert.equal(canonical(ev(array),x),true);}
 assert.equal(candidate(ev(JSON.stringify(a,null,2)),a),true);
});
test('every JSONL line validated even after or before exact matching row',()=>{
 const invalid=['prose','{}','[]','null','true','42',JSON.stringify([a]),JSON.stringify({nested:a}),JSON.stringify(a,null,2),'{bad',JSON.stringify({...b,amount:'25.5'}),JSON.stringify(b).replace('974.5','1e999')];
 for(const line of invalid)for(const output of [line+'\n'+jsonl,jsonl+'\n'+line])assert.equal(candidate(ev(output),a),false,output);
 assert.equal(candidate(ev('\r\n'+jsonl.replace('\n','\r\n\t\r\n')+'\r\n'),a),true);
 for(const key of Object.keys(a)){assert.equal(candidate(ev(jsonl),{...a,[key]:a[key]+1}),false);const missing={...b};delete missing[key];assert.equal(candidate(ev(jsonl+'\n'+JSON.stringify(missing)),a),false);}
});
test('no cross-row assembly recursion prose or numeric coercion',()=>{
 const split=Object.keys(a).map(key=>({...a,[key]:a[key]+1}));
 for(const output of [JSON.stringify(split),split.map(JSON.stringify).join('\n'),JSON.stringify({example:a}),JSON.stringify([[a]]),'PASS\n'+JSON.stringify(a),'```json\n'+jsonl+'\n```'])assert.equal(candidate(ev(output),a),false);
 for(const key of Object.keys(a))assert.equal(candidate(ev(jsonl),{...a,[key]:String(a[key])}),false);
});
test('successful completed real command event type and original command classifier retained',()=>{
 for(const item of [{type:'reasoning'},{type:'agent_message'},{status:'failed'},{status:'in_progress'},{exit_code:1},{exit_code:'0'},{command:'echo withdraw wallet.mjs'},{command:'cd /tmp && '+cmd},{command:'/usr/bin/'+cmd}])assert.equal(candidate({...ev(jsonl),item:{...ev(jsonl).item,...item}},a),false);
 for(const type of ['item.started','turn.completed','reasoning','agent_message'])assert.equal(candidate({...ev(jsonl),type},a),false);
 for(const shell of ['bash','sh','zsh'])for(const flag of ['c','lc'])assert.equal(candidate({...ev(jsonl),item:{...ev(jsonl).item,command:`/bin/${shell} -${flag} '${cmd}'`}},a),true);
});
test('fixed fixture bytes and projection fixture exact custody',async()=>{
 for(const [name,expected] of [['wallet.mjs','c47fcdfb32c95bf1ede68c01a3705084a658ecbd2882ab21ca4e8cc5fc658f71'],['BUSINESS_RULES.md','1a9837e5e95ee86f22eb171c7bc9ee1226c55ff859973ad573417feb6aae43a5']])assert.equal(createHash('sha256').update(await readFile(new URL(name,fixture))).digest('hex'),expected);
 assert.deepEqual(await readFile(new URL('../.spike-inputs/candidate/sub2api-evidence-r2/numeric-jsonl-fixture.json',import.meta.url)),await readFile(new URL('../.spike-inputs/actual-canary/actual-numeric-jsonl-projection.json',import.meta.url)));
});
test('separate reads genuine terminal and final finding remain mandatory',async()=>{
 const read=(name,output)=>({...ev(output),item:{...ev(output).item,command:'cat '+name}});
 const events=[read('wallet.mjs',await readFile(new URL('wallet.mjs',fixture),'utf8')),read('BUSINESS_RULES.md',await readFile(new URL('BUSINESS_RULES.md',fixture),'utf8')),{type:'turn.completed'}];
 const doc={findings:[{file:'wallet.mjs',function:'withdraw',summary:'negative withdrawal increases balance',example:a}]};
 assert.equal(financialEvidence('codex',events,JSON.stringify(doc),'mimo').terminal_verified,true);
 for(const list of [events.slice(1),events.filter((_,i)=>i!==1),events.slice(0,2),[...events,{type:'turn.failed'}],[...events,{type:'error'}]])assert.throws(()=>financialEvidence('codex',list,JSON.stringify(doc),'mimo'));
 for(const doc of ['{}','{"findings":[]}','reasoning',JSON.stringify({findings:[{file:'wallet.mjs',function:'withdraw',summary:'',example:a}]})])assert.throws(()=>financialEvidence('codex',events,doc,'mimo'));
});
