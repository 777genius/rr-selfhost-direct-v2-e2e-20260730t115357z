import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {pathToFileURL,fileURLToPath} from 'node:url';
const source=process.env.NUMERIC_SOURCE ? pathToFileURL(process.env.NUMERIC_SOURCE) : new URL('../sub2api-spike/evidence.mjs',import.meta.url);
const {codexNumericEvidence:accept}=await import(source.href);
const fixture=fileURLToPath(new URL('../sub2api-spike/fixture/',import.meta.url));
const rows=[{initial_balance:1000,amount:-50,final_balance:1050},{initial_balance:1000,amount:25.5,final_balance:974.5}];
const event=output=>({type:'item.completed',item:{type:'command_execution',status:'completed',exit_code:0,command:'node --input-type=module -e "import {withdraw} from \'./wallet.mjs\'"',aggregated_output:output}});
const expr=`import {withdraw} from './wallet.mjs';for(const r of ${JSON.stringify(rows)}){const wallet={balance:r.initial_balance};const actual=withdraw(wallet,r.amount).balance;if(actual!==r.final_balance||wallet.balance!==r.final_balance)process.exit(1);console.log(JSON.stringify({...r,final_balance:actual}));}`;
const stdout=execFileSync(process.execPath,['--input-type=module','-e',expr],{cwd:fixture,encoding:'utf8'});
test('real complete wallet stdout strict JSONL matches each exact example',()=>{for(const row of rows)assert.equal(accept(event(stdout),row),true);});
test('whole object and immediate root-array members accepted',()=>{for(const row of rows){assert.equal(accept(event(JSON.stringify(row,null,2)),row),true);assert.equal(accept(event(JSON.stringify(rows)),row),true);}});
test('all JSONL lines required finite complete objects; no recursion or assembly',()=>{
 for(const bad of ['{}','[]','null','garbage',JSON.stringify({...rows[1],amount:'25.5'}),'{"initial_balance":1e999,"amount":1,"final_balance":0}'])
  for(const text of [stdout+bad,bad+'\n'+stdout])assert.equal(accept(event(text),rows[0]),false);
 for(const text of [JSON.stringify({nested:rows[0]}),JSON.stringify([rows]),'prose\n'+stdout])assert.equal(accept(event(text),rows[0]),false);
 const split=Object.keys(rows[0]).map(k=>({...rows[0],[k]:rows[0][k]+1}));
 assert.equal(accept(event(split.map(JSON.stringify).join('\n')),rows[0]),false);
});
test('successful completed command and exact finite example remain mandatory',()=>{
 for(const mutation of [{exit_code:1},{exit_code:'0'},{status:'failed'},{type:'agent_message'},{command:'echo wallet.mjs withdraw'}])assert.equal(accept({...event(stdout),item:{...event(stdout).item,...mutation}},rows[0]),false);
 for(const k of Object.keys(rows[0]))assert.equal(accept(event(stdout),{...rows[0],[k]:String(rows[0][k])}),false);
});
