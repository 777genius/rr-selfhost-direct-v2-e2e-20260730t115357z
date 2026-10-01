import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { telemetryVerdict } from '../.spike-inputs/transport-artifacts/adapter.mjs';
import { Inspector, fixture } from '../.spike-inputs/transport-artifacts/overlay/sub2api-regression-lab/wire.mjs';
import { codexNumericEvidence } from '../sub2api-spike/evidence.mjs';
const MiB=1048576;
const input=new URL('../.spike-inputs/actual-execution/',import.meta.url);
const json=url=>JSON.parse(readFileSync(url,'utf8'));
const cases=[];
for (const protocol of ['responses','messages']) for (const name of readdirSync(new URL(protocol+'/',input)).filter(x=>x.startsWith('memory-'))) {
  const dir=new URL(protocol+'/'+name+'/',input);
  const row=json(new URL('case.json',dir));
  const ready=json(new URL('telemetry.ready.json',dir));
  const done=json(new URL('telemetry.done.json',dir));
  const samples=readFileSync(new URL('telemetry.ndjson',dir),'utf8').trim().split('\n').map(JSON.parse);
  const meta={...row.telemetry_boundary,ended_ms:done.ended_ms};
  cases.push({name,row,ready,done,samples,meta});
  test('exact frozen receipt replay '+name,()=>{
    assert.deepEqual(telemetryVerdict(samples,meta,ready,{done}),row.memory_envelope);
  });
}
test('actual full-tail gate rejects omitted DONE, short tail, forged identity and hidden slow retry',()=>{
  const {samples,meta,ready,done}=cases[0];
  for (const options of [{},{done:{...done,full_tail_ms:4999}},{done:{...done,engine_pid:done.engine_pid+1}}]) {
    assert.equal(telemetryVerdict(samples,meta,ready,options).empirical_qualified_status,'NOT RUN');
  }
  const slow=structuredClone(samples);slow[1].sample_duration_ms=251;slow[1].sample_started_ms=slow[1].mono_ms-251;
  assert.equal(telemetryVerdict(slow,meta,ready,{done}).reason,'TELEMETRY_IDENTITY_OR_FIELDS_UNVERIFIED');
});
for (const protocol of ['responses','messages']) for (const volume of [8,32,64]) {
  test(`real discard inspector ${protocol} exact ${volume}MiB with near-limit semantic frames`,()=>{
    const f=fixture(protocol,{near:true}), parser=new Inspector(protocol);
    let maxPending=0;
    const feed=bytes=>{
      for (let offset=0;offset<bytes.length;offset+=32749) {
        parser.push(bytes.subarray(offset,offset+32749));
        maxPending=Math.max(maxPending,parser.pending.length);
      }
    };
    for (const frame of f.frames.slice(0,f.early)) feed(frame);
    let remaining=volume*MiB-f.frames.reduce((sum,frame)=>sum+frame.length,0);
    assert.ok(remaining>=0);
    const comment=Buffer.from(': '+'x'.repeat(16380)+'\n\n');
    while(remaining>0) {
      const size=remaining<=comment.length+4?remaining:comment.length;
      assert.ok(size>=5);
      feed(size===comment.length?comment:Buffer.from(': '+'x'.repeat(size-4)+'\n\n'));
      remaining-=size;
    }
    for (const frame of f.frames.slice(f.early)) feed(frame);
    const result=parser.finish();
    assert.equal(result.bytes,volume*MiB);assert.ok(result.terminal_ms!==null);
    assert.equal(result.malformed,false);assert.equal(result.failed,false);
    assert.ok(result.tool_id);assert.ok(result.comments>0);assert.ok(result.text_delta_bytes>4096);
    assert.ok(result.max_frame_bytes>=1.9*MiB && result.max_frame_bytes<2*MiB);
    assert.ok(maxPending<2*MiB);assert.equal(parser.pending.length,0);
    assert.equal(Object.hasOwn(parser,'events'),false);
  });
}
test('actual discard inspector rejects oversized and malformed frames',()=>{
  assert.throws(()=>new Inspector('responses').push(Buffer.alloc(2*MiB+1,120)),/FRAME_LIMIT/);
  assert.throws(()=>new Inspector('responses').push(Buffer.from('data: {broken}\n\n')));
});
test('independent numeric contract: exact object, array, strict JSONL, atomic rows and completed tools',()=>{
  const row={initial_balance:1000,amount:-50,final_balance:1050};
  const other={initial_balance:1000,amount:25.5,final_balance:974.5};
  const e=output=>({type:'item.completed',item:{type:'command_execution',command:'node --input-type=module -e "import wallet.mjs; withdraw"',aggregated_output:output,exit_code:0,status:'completed'}});
  const valid=[JSON.stringify(row),JSON.stringify([other,row]),JSON.stringify(row)+'\n'+JSON.stringify(other)+'\n'];
  for (const s of valid) assert.equal(codexNumericEvidence(e(s),row),true);
  const s=valid[2];
  for (const extra of ['prose','[]','null','{broken',JSON.stringify({...other,amount:'25.5'}),JSON.stringify(other).replace('974.5','1e999')]) assert.equal(codexNumericEvidence(e(s+extra),row),false);
  const split=[{...row,amount:1},{...row,final_balance:1}].map(JSON.stringify).join('\n');
  assert.equal(codexNumericEvidence(e(split),row),false);
  for (const value of ['1000',null,undefined,Infinity,NaN]) for(const key of Object.keys(row)) assert.equal(codexNumericEvidence(e(JSON.stringify({...row,[key]:value})),row),false);
  for(const changes of [{status:'failed'},{exit_code:1},{exit_code:'0'},{command:'echo wallet.mjs withdraw'}]) assert.equal(codexNumericEvidence({...e(s),item:{...e(s).item,...changes}},row),false);
});
