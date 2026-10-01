import test from 'node:test';
import assert from 'node:assert/strict';
import {exercise} from './load-harness.mjs';
const MiB=1048576;
const rejected = ['null','true','"8388608"','[8388608]','[]','{}','{"value":8388608}','-1','0.5','1e400','9007199254740992'];
test('strict JSONL numeric evidence cannot pass or poison aggregation in actual load',async()=>{
  // Every canary crosses an actual JSON parse boundary, including overflow 1e400.
  let cases=0;
  for(const field of ['bytes','text_delta_bytes','max_frame_bytes','comments','duration_ms','terminal_ms']) {
    for(const raw of rejected) {
      if(['duration_ms','terminal_ms'].includes(field)&&['0.5','9007199254740992'].includes(raw))continue;
      const downstream=JSON.parse(`{"${field}":${raw}}\n`);
      const row=await exercise({downstream});
      assert.equal(row.functional_status,'FAIL',field+raw);
      assert.equal(row.acceptance_status,'FAIL',field+raw);
      assert.equal(row.downstream.bytes,null,field+raw);
      assert.equal(row.downstream.max_frame_bytes,null,field+raw);
      cases++;
    }
  }
  for(const field of ['bytes','effects','close_ms'])for(const raw of rejected) {
    if(field==='close_ms'&&['0.5','9007199254740992'].includes(raw))continue;
    const row=await exercise({upstream:JSON.parse(`{"${field}":${raw}}\n`)});
    assert.equal(row.functional_status,'FAIL','upstream '+field+raw);cases++;
  }
  process.stdout.write(JSON.stringify({strict_jsonl_invalid_numeric_cases:cases,actual_function:'load',engine:'NOT RUN'})+'\n');
});
test('exact upstream/downstream body volumes for all18 cells; protocol conversion mismatch stays FAIL',async()=>{
  for(const protocol of ['responses','messages'])for(const mib of [8,32,64])for(const streams of [1,5,20]) {
    const args={protocol,mib,streams};
    const row=await exercise(args);
    assert.equal(row.functional_status,'PASS');assert.equal(row.downstream.bytes,mib*MiB*streams);
    assert.equal(row.acceptance_status,'NOT RUN');assert.equal(row.memory_envelope.physical_interval_rss_status,'NOTPROVEN');
    for(const delta of [-1,1])for(const side of ['upstream','downstream']) {
      assert.equal((await exercise({...args,[side]:{bytes:mib*MiB+delta}})).functional_status,'FAIL');
    }
  }
});
test('near-limit frame qualification has exact integer boundaries and no cap equality',async()=>{
  for(const [frame,status] of [[Math.floor(1.9*MiB),'FAIL'],[Math.ceil(1.9*MiB),'PASS'],[2*MiB-1,'PASS'],[2*MiB,'FAIL']]) {
    assert.equal((await exercise({downstream:{max_frame_bytes:frame}})).functional_status,status);
  }
});
test('protocol/effect/terminal/text/tool/comment gates and numeric soak boundary remain strict',async()=>{
  for(const downstream of [{http_status:500},{transport:'deadline'},{failed:true},{malformed:true},{terminal_ms:null},
    {text_delta_bytes:4096},{tool_id:null},{comments:0}])assert.equal((await exercise({downstream})).functional_status,'FAIL');
  for(const upstream of [{effects:0},{effects:2},{finished:false},{identity:'UNKNOWN'},{close_ms:null}])assert.equal((await exercise({upstream})).functional_status,'FAIL');
  const row=await exercise({stage:'soak',streams:5,count:250});
  assert.equal(row.functional_status,'PASS');assert.equal(row.downstream.requests,250);assert.equal(row.acceptance_status,'NOT RUN');
  assert.equal((await exercise({stage:'soak',streams:5,count:250,downstream:{bytes:[8388608]}})).functional_status,'FAIL');
  const overflow=await exercise({stage:'soak',streams:5,count:250,downstream:{bytes:Number.MAX_SAFE_INTEGER}});
  assert.equal(overflow.functional_status,'FAIL');assert.equal(overflow.downstream.bytes,null);
});
