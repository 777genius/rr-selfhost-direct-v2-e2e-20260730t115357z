import os,subprocess,re,json
from pathlib import Path
own=Path.cwd()/'sub2api-cancel-oracle-review';candidate=Path.cwd()/'.spike-inputs/candidate/sub2api-cancel-oracle-repair'
code=(candidate/'broker.test.mjs').read_text().split("for(const protocol of ['responses','messages']) {")[0]
code=code.replace('ttlMs = 3000 } = {})','ttlMs = 3000, omitObserver = false } = {})').replace('let now = 0, server, signal, physicalClose;','let now = 0, server, signal, physicalClose, member = true;')
code=code.replace("resolveWorkspace:async()=> 'fixture',","resolveWorkspace:async()=> 'fixture',isWorkspaceActive:async()=>member,")
code=code.replace("if(throws)throw Error('observer');},","if(throws)throw Error('observer');}, ...(omitObserver?{observeCancellation:undefined}:{}),")
code=code.replace('get physicalClose(){return physicalClose;}','setMember(x){member=x;},get physicalClose(){return physicalClose;}')
code+='''
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
'''
(own/'tests/independent-broker.test.mjs').write_text(code)
code=(candidate/'oracle.test.mjs').read_text()
code=code[:code.index("for (const protocol of ['responses', 'messages']) {")]
code+='''
for(const protocol of ['responses','messages'])for(const cause of ['membership','workspace-revoke','server-close','timeout','downstream-close','request-finally'])test(`${protocol}: ${cause} cannot substitute revoke causality`,()=>{
  const row=trace(protocol);row.broker_abort_events[0].cause=cause;assert.equal(verdict(row,'after').status,'FAIL');
});
for(const protocol of ['responses','messages'])test(`${protocol}: immediate duplicate effect cannot be erased in final receipt`,()=>{
  const row=trace(protocol);row.upstream_at_immediate_oracle[0].effects=2;assert.equal(verdict(row,'after').status,'FAIL');
});
'''
(own/'tests/independent-oracle.test.mjs').write_text(code)
r=subprocess.run(['node','--experimental-vm-modules','--test','--test-reporter=tap',str(own/'tests/independent-broker.test.mjs'),str(own/'tests/independent-oracle.test.mjs')],env=dict(os.environ,CANCEL_CODE=str(own/'w2')),capture_output=True,text=True,timeout=30)
tap=r.stdout+r.stderr;(own/'independent.tap').write_text(tap)
counts={k:int(re.search(r'^# '+k+r' (\d+)$',tap,re.M)[1]) for k in ['tests','pass','fail','cancelled','skipped']};assert r.returncode==0,tap
(own/'independent-verification.json').write_text(json.dumps(counts,indent=2)+'\n');print(counts)
