import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { codexNumericEvidence } from '../sub2api-spike/evidence.mjs';
import { telemetryVerdict } from '../.spike-inputs/runtime/sub2api-transport-r4/adapter.mjs';
import { Inspector, fixture } from '../.spike-inputs/runtime/sub2api-regression-lab/wire.mjs';
const json=p=>JSON.parse(readFileSync(p,'utf8')),MiB=1048576;
const history=json(new URL('../sub2api-transport-r4/historical-input/execution.json',import.meta.url));
test('older 20-case inventory keeps FAIL and NOT RUN evidence',()=>{
  assert.equal(history.results.length,20);
  for(const r of history.results){assert.ok(['FAIL','NOT RUN'].includes(r.status));assert.ok(['FAIL','NOT RUN'].includes(r.memory.status));if(r.cleanup)assert.equal(r.cleanup.failures,0);}
});
for(const protocol of ['responses','messages']) {
  test('real full-frame 8MiB discard parser '+protocol,()=>{
    const f=fixture(protocol,{near:true}),p=new Inspector(protocol);
    const feed=b=>{for(let i=0;i<b.length;i+=32749)p.push(b.subarray(i,i+32749));};
    for(const b of f.frames.slice(0,f.early))feed(b);
    let remaining=8*MiB-f.frames.reduce((n,b)=>n+b.length,0);
    while(remaining){const size=Math.min(remaining,16384);assert.ok(size>=5);feed(Buffer.from(': '+'x'.repeat(size-4)+'\n\n'));remaining-=size;}
    for(const b of f.frames.slice(f.early))feed(b);
    const r=p.finish();assert.equal(r.bytes,8*MiB);assert.equal(r.failed,false);assert.equal(r.malformed,false);
    assert.ok(r.terminal_ms!==null && r.tool_id && r.comments>0 && r.text_delta_bytes>4096);
    assert.ok(r.max_frame_bytes>=1.9*MiB && r.max_frame_bytes<2*MiB);assert.equal(p.pending.length,0);
  });
}
const rows=[{initial_balance:1000,amount:-50,final_balance:1050},{initial_balance:1000,amount:25.5,final_balance:974.5}];
const event=output=>({type:'item.completed',item:{type:'command_execution',command:'node --input-type=module -e "import wallet.mjs; withdraw"',aggregated_output:output,exit_code:0,status:'completed'}});
for(const shape of ['object','array','jsonl'])test('real local wallet reproduction '+shape,()=>{
  const expression=`import {withdraw} from './wallet.mjs'; const rows=${JSON.stringify(rows)}.map(({initial_balance,amount})=>({initial_balance,amount,final_balance:withdraw({balance:initial_balance},amount).balance})); ${shape==='object'?'console.log(JSON.stringify(rows[0]))':shape==='array'?'console.log(JSON.stringify(rows))':'for(const r of rows)console.log(JSON.stringify(r))'}`;
  const output=execFileSync(process.execPath,['--input-type=module','-e',expression],{cwd:fileURLToPath(new URL('../sub2api-spike/fixture/',import.meta.url)),encoding:'utf8',timeout:5000});
  for(const r of shape==='object'?rows.slice(0,1):rows)assert.equal(codexNumericEvidence(event(output),r),true);
});
test('strict JSONL denies mixed lines, nonfinite/scalar coercion and assembled rows',()=>{
  const valid=rows.map(JSON.stringify).join('\n')+'\n';
  for(const junk of ['prose','[]','null','{broken',JSON.stringify({...rows[1],amount:'25.5'}),JSON.stringify(rows[1]).replace('974.5','1e999')])
    assert.equal(codexNumericEvidence(event(valid+junk),rows[0]),false);
  for(const key of Object.keys(rows[0]))for(const bad of [null,'1000',true,{},[],Infinity,NaN])
    assert.equal(codexNumericEvidence(event(JSON.stringify({...rows[0],[key]:bad})),rows[0]),false);
  assert.equal(codexNumericEvidence(event([{...rows[0],amount:0},{...rows[0],final_balance:0}].map(JSON.stringify).join('\n')),rows[0]),false);
  for(const changes of [{exit_code:'0'},{exit_code:1},{status:'failed'},{command:'echo wallet.mjs withdraw'}])
    assert.equal(codexNumericEvidence({...event(valid),item:{...event(valid).item,...changes}},rows[0]),false);
});
