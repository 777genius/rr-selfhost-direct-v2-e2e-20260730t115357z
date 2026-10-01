from pathlib import Path
import shutil,json,hashlib,importlib.util,subprocess,os
R=Path.cwd();O=R/'sub2api-slot-phase-review';H=O/'runtime';E=O/'evidence';E.mkdir(exist_ok=True);H.mkdir(exist_ok=True)
I=R/'.spike-inputs';C=I/'candidate/sub2api-slot-lab';W=I/'original-inputs/candidate/sub2api-slot-lab'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rel=json.loads((I/'parent-evidence/namespace-correction.json').read_text());assert len(rel['files'])==101
assert all(sha(C/n)==v for n,v in rel['files'].items())
changed=[];same=[]
for p in W.rglob('*'):
 if p.is_file():
  n=str(p.relative_to(W));q=C/n;assert q.exists(),n
  (same if p.read_bytes()==q.read_bytes() else changed).append(n)
assert changed==['run.mjs'],changed
crit=json.loads((I/'independent-W7/review.json').read_text())['critical_candidate_sha256'];pins={n:sha(C/n) for n in crit}
assert all(pins[n]==v for n,v in crit.items() if n!='run.mjs')
assert (I/'profile-root-driver.py').read_bytes()==(I/'original-inputs/profile-w7-root-driver.py').read_bytes()
shutil.copytree(C,H/'sub2api-slot-lab',dirs_exist_ok=True)
for p in (H/'sub2api-slot-lab').rglob('*'):
 if p.is_file():p.chmod(0o600)
spec=importlib.util.spec_from_file_location('fresh',C/'prepare.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.REPO=I/'canonical';manifest=m.assemble(H/'sub2api-slot-lab/build')
assert manifest['prepared_files']['sub2api-slot-lab/run.mjs']==pins['run.mjs']
shutil.copytree(H/'sub2api-slot-lab/build/sub2api-regression-lab',H/'sub2api-regression-lab')
shutil.copytree(W,H/'.spike-inputs/candidate/sub2api-slot-lab');shutil.copytree(H/'sub2api-regression-lab',H/'.spike-inputs/candidate/sub2api-regression-lab')
for package in ('sub2api-transport-packaging','sub2api-transport-r4'):shutil.copytree(I/'canonical'/package,H/package)
shutil.copytree(I/'original-inputs/original-inputs/profile-canonical-w3',H/'sub2api-memory-profile');(H/'sub2api-memory-profile/root-driver.py').chmod(0o600);shutil.copyfile(I/'profile-root-driver.py',H/'sub2api-memory-profile/root-driver.py')
# Only test location constants change; all original assertions retained.
p=H/'sub2api-slot-lab/phase-boundary.test.mjs';p.write_text(p.read_text().replace("resolve('fullsub2api-slot-lab')","resolve('sub2api-slot-lab')"))
results=[]
def run(name,args,extra={}):
 p=subprocess.run(args,cwd=H,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',**extra),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=25);(E/(name+'.txt')).write_bytes(p.stdout);results.append({'name':name,'exit_code':p.returncode});print(name,p.returncode,flush=True)
run('phase-red',['node','--experimental-vm-modules','--test','sub2api-slot-lab/phase-boundary.test.mjs'],{'SLOT_PHASE_OLD':'1'})
run('phase-green',['node','--experimental-vm-modules','--test','sub2api-slot-lab/phase-boundary.test.mjs'])
run('inherited-node',['node','--test']+['sub2api-slot-lab/'+n for n in ['offline.test.mjs','recovery-contract.test.mjs','tls-factory.test.mjs','login-boundary.test.mjs','setup-rate-limit.test.mjs']])
run('deadline-python',['python3','sub2api-slot-lab/deadline-regression.py'])
ledger=json.loads((C/'W8-LEDGER.json').read_text());stale={n:{'reported':v,'actual':manifest['prepared_files'][n]} for n,v in ledger['prepared_runtime']['prepared_files'].items() if manifest['prepared_files'][n]!=v}
(O/'audit.json').write_text(json.dumps({'relocated_files_verified':101,'W7_changed':changed,'W7_unchanged':len(same),'candidate_root_10_sha256':pins,'profile_root_driver_sha256':sha(I/'profile-root-driver.py'),'prepared_runtime':manifest,'producer_prepared_ledger_stale_entries':stale,'results':results},indent=2)+'\n')
