from pathlib import Path
import hashlib,json,shutil,subprocess
root=Path.cwd(); owned=root/'sub2api-transport-review-r4'; candidate=root/'.spike-inputs/candidate'; repair=candidate/'sub2api-transport-r2'
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((root/'.spike-inputs/INPUT-HASHES.json').read_text())
checked={name:{'expected':digest,'actual':h(root/'.spike-inputs'/name)} for name,digest in manifest.items()}
assert all(x['actual']==x['expected'] for x in checked.values())
(owned/'evidence/input-verification.json').write_text(json.dumps(checked,indent=2)+'\n')
source_hashes={str(p.relative_to(root)):h(p) for p in sorted(repair.rglob('*')) if p.is_file()}
(owned/'evidence/reviewed-source-hashes.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
dest=owned/'reconstructed'; dest.mkdir(exist_ok=True)
for folder in ['sub2api-regression-lab','sub2api-spike']:
    shutil.copytree(candidate/folder,dest/folder,dirs_exist_ok=True)
changes=json.loads((repair/'changed-loc.json').read_text())
for name,row in changes.items(): assert h(dest/name)==row['original_sha256'],name
r=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(repair/'lab-overlay.patch')],cwd=dest,text=True,capture_output=True)
assert r.returncode==0,r.stdout+r.stderr
for name,row in changes.items():
    assert h(dest/name)==row['result_sha256'],name
    assert h(dest/name)==h(repair/'overlay'/name),name
    if Path(name).suffix=='.mjs': subprocess.run(['node','--check',str(dest/name)],check=True)
(dest/'sub2api-transport-r2').mkdir(exist_ok=True); shutil.copyfile(repair/'adapter.mjs',dest/'sub2api-transport-r2/adapter.mjs')
p=subprocess.run(['node',str(dest/'sub2api-regression-lab/run.mjs'),'--plan'],check=True,capture_output=True,text=True)
plan=json.loads(p.stdout)
assert {s:sum(x['stage']==s for x in plan['cases']) for s in ['cancel','uncertainty','memory','soak']}==dict(cancel=12,uncertainty=8,memory=18,soak=2)
assert [x['count'] for x in plan['cases'] if x['stage']=='soak']==[250,250]
assert plan['budget']['max_actual_upstream_attempts']==2000
(owned/'evidence/reconstructed-plan.json').write_text(p.stdout)
(owned/'evidence/integration-verification.json').write_text(json.dumps({'input_hashes_verified':len(checked),'canonical_patch_zero_fuzz':True,'six_output_hashes_match':True,'runnable_plan':True,'frozen_root_patch':'NOT RUN: .spike-inputs/prior-code absent','requested_transport_r3':'MISSING: only transport-r2 supplied'},indent=2)+'\n')
print('PASS manifest, canonical zero-fuzz patch, exact six output hashes, syntax, runnable 40case plan; frozen-root baseline and requested r3 missing')
