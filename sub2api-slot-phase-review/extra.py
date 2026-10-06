from pathlib import Path
import shutil,subprocess,os,json
O=Path(__file__).resolve().parent;R=O.parent;H=O/'runtime';I=R/'.spike-inputs'
for package in ('sub2api-transport-packaging','sub2api-transport-r4'):shutil.copytree(I/'canonical'/package,H/package,dirs_exist_ok=True)
s=(H/'sub2api-slot-lab/phase-boundary.test.mjs').read_text();s=s[:s.index("test('native Retry")]
s=s.replace('supervisor=1200000}', 'supervisor=1200000,advance=0}')
s=s.replace('activeDeadline;const objects', 'activeDeadline;const observations=[];const objects')
s=s.replace("if(path.endsWith('/run.mjs'))", "if(path.endsWith('/common.mjs'))source=source.replace('export function control(c, action, body) {', 'export function control(c, action, body) { globalThis.__observe(c.deadline, action);');\n  if(path.endsWith('/run.mjs'))")
s=s.replace("activeDeadline=config.deadline;throw", "activeDeadline=config.deadline;if(advance)now=advance;throw")
s=s.replace('globalThis.__phaseSave=', 'globalThis.__observe=(deadline,action)=>observations.push({deadline,action,now});\n globalThis.__phaseSave=')
s=s.replace('snapshot:async()=>zero', 'snapshot:async(ids,deadline)=>{observations.push({deadline,action:"redis",now});return zero;}')
s=s.replace('return {row,models,posts,activeDeadline}', 'return {row,models,posts,activeDeadline,observations}')
s+='''
test('exact 105s supervisor admission succeeds with full active budget',async()=>{const x=await exercise({supervisor:105000,finish:69999});assert.equal(x.models,1);assert.equal(x.activeDeadline,104999);assert.equal(x.row.fixture.deadline_ms,70000);assert.equal(x.row.cleanup.failures,0);});
test('active deadline exactly reached during Redis and rule setup prevents first model',async()=>{const x=await exercise({finish:5000});assert.equal(x.models,1);});
for(const advance of [104500,105000,105001])test(`failure observation and teardown capped at supervisor at ${advance}`,async()=>{const x=await exercise({supervisor:105000,advance});assert.equal(x.models,1);assert.equal(x.row.status,'FAIL');const cleanup=x.observations.filter(o=>o.now===advance);assert.ok(cleanup.length>=5);assert.ok(cleanup.every(o=>o.deadline<=105000));assert.ok(cleanup.filter(o=>o.action==='redis'||o.action==='state'||o.action==='stop').every(o=>o.deadline<=Math.min(105000,advance+1000)));if(advance>=105000){assert.equal(x.row.cleanup.failures,4);assert.equal(x.row.cleanup.remaining.length,4);}else assert.equal(x.row.cleanup.failures,0);});
'''
# Make one separate case advance during initial Redis read to active expiration.
s=s.replace('advance=0}', 'advance=0,initialAdvance=0}').replace('snapshot:async(ids,deadline)=>{observations', 'snapshot:async(ids,deadline)=>{if(initialAdvance&&now<initialAdvance)now=initialAdvance;observations')
s=s.replace("const x=await exercise({finish:5000});assert.equal(x.models,1);", "const x=await exercise({finish:5000,initialAdvance:40000});assert.equal(x.models,0);assert.equal(x.row.reason,'BATCH_DEADLINE');")
(H/'extra.test.mjs').write_text(s)
res=[]
for name,args in [('inherited-node-rerun',['node','--test']+['sub2api-slot-lab/'+n for n in ['offline.test.mjs','recovery-contract.test.mjs','tls-factory.test.mjs','login-boundary.test.mjs','setup-rate-limit.test.mjs']]),('extra',['node','--experimental-vm-modules','--test','extra.test.mjs'])]:
 p=subprocess.run(args,cwd=H,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30);(O/'evidence'/f'{name}.txt').write_bytes(p.stdout);res.append({'name':name,'exit_code':p.returncode});print(name,p.returncode,flush=True)
(O/'extra-results.json').write_text(json.dumps(res,indent=2))
