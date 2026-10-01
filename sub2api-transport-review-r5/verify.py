from pathlib import Path
import hashlib,json,subprocess,shutil,tempfile,os
root=Path(__file__).resolve().parent.parent
own=root/'sub2api-transport-review-r5'
inputs=root/'.spike-inputs'
candidate=inputs/'candidate/sub2api-transport-r4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_manifest(base,path):
 m=json.loads(path.read_text())
 for name,h in m.items():assert sha(base/name)==h,(str(path),name)
 return len(m)
summary={'outer_manifest_sha256':sha(inputs/'INPUT-HASHES.json'),'outer_files_verified':check_manifest(inputs,inputs/'INPUT-HASHES.json')}
summary['candidate_outputs_verified']=check_manifest(candidate,candidate/'output-hashes.json')
history=candidate/'historical-input'
summary['historical_inputs_verified']=check_manifest(history,history/'INPUT-HASHES.json')
for d,m in [('candidate','output-hashes.json'),('independent-review','artifact-hashes.json')]:summary[d+'_historical_outputs_verified']=check_manifest(history/d,history/d/m)
reviewed=json.loads((history/'independent-review/evidence/reviewed-source-hashes.json').read_text())
for name,h in reviewed.items():assert sha(history/'candidate'/name.removeprefix('.spike-inputs/candidate/sub2api-transport-r2/'))==h
summary['original_review_hashes_verified']=len(reviewed)
execution=json.loads((history/'execution.json').read_text())
assert {s:sum(r['status']==s for r in execution['results']) for s in ['FAIL','NOT RUN']}=={'FAIL':11,'NOT RUN':9}
assert execution['total_upstream_attempts']==sum(r['effects'] for r in execution['results'])==686
assert all(r['cleanup']['failures']==0 and not r['cleanup']['remaining_resources'] for r in execution['results'])
summary['history']={'sha256':sha(history/'execution.json'),'FAIL':11,'NOT RUN':9,'attempts':686,'effects':686,'rerun':False}
assert json.loads((history/'independent-review/review.json').read_text())['verdict']=='REQUESTCHANGES'
changes=json.loads((candidate/'changed-loc.json').read_text())
summary['patches']={}
for lane,base,patch in [('canonical',inputs/'candidate','lab-overlay.patch'),('frozen-root',history/'prior-code','frozen-root-overlay.patch')]:
 with tempfile.TemporaryDirectory(dir=own/'tmp',prefix=lane+'-') as temporary:
  dest=Path(temporary)
  for name in ['sub2api-regression-lab','sub2api-spike']:shutil.copytree(base/name,dest/name)
  for name,row in changes.items():assert sha(dest/name)==row['original_sha256'],(lane,name)
  args=['patch','--batch','--fuzz=0','-p1','-i',str(candidate/patch)]
  dry=subprocess.run(args[:1]+['--dry-run']+args[1:],cwd=dest,check=True,capture_output=True,text=True)
  applied=subprocess.run(args,cwd=dest,check=True,capture_output=True,text=True)
  assert all(word not in (dry.stdout+applied.stdout).lower() for word in ['offset','fuzz'])
  for name,row in changes.items():
   assert sha(dest/name)==row['result_sha256']==sha(candidate/'overlay'/name)
   if name.endswith('.mjs'):subprocess.run(['node','--check',str(dest/name)],check=True,capture_output=True)
  (dest/'sub2api-transport-r4').mkdir();shutil.copyfile(candidate/'adapter.mjs',dest/'sub2api-transport-r4/adapter.mjs')
  plan=json.loads(subprocess.run(['node',str(dest/'sub2api-regression-lab/run.mjs'),'--plan'],check=True,capture_output=True,text=True).stdout)
  assert len(plan['cases'])==40
  assert {s:sum(c['stage']==s for c in plan['cases']) for s in ['cancel','uncertainty','memory','soak']}=={'cancel':12,'uncertainty':8,'memory':18,'soak':2}
  memory={(c['protocol'],c['mib'],c['streams']) for c in plan['cases'] if c['stage']=='memory'}
  assert memory=={(p,m,n) for p in ['responses','messages'] for m in [8,32,64] for n in [1,5,20]}
  assert [(c['count'],c['streams']) for c in plan['cases'] if c['stage']=='soak']==[(250,5),(250,5)]
  assert plan['budget']['max_actual_upstream_attempts']==2000
  (own/'evidence'/f'{lane}-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
  env=dict(os.environ,RR_LOAD_SOURCE=str(dest/'sub2api-regression-lab/run.mjs'))
  tests=subprocess.run(['node','--test',str(own/'independent.test.mjs'),str(candidate/'load.test.mjs')],env=env,check=True,capture_output=True,text=True)
  (own/'evidence'/f'{lane}-load.tap').write_text(tests.stdout+tests.stderr)
  (own/'evidence'/f'{lane}-patch.txt').write_text(dry.stdout+applied.stdout)
  summary['patches'][lane]={'sha256':sha(candidate/patch),'zero_fuzz':True,'zero_offset':True,'files':{name:sha(dest/name) for name in changes},'plan_cases':40,'behavioral_tests':8}
summary['reviewed_source_hashes']={str(p.relative_to(inputs)):sha(p) for p in sorted(candidate.rglob('*')) if p.is_file()}
(own/'evidence/verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='reviewed_source_hashes'},indent=2))
