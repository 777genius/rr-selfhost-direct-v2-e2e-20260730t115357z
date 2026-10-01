import sys
sys.dont_write_bytecode=True
import json, hashlib, importlib.util, shutil, subprocess, os, re
from pathlib import Path
root=Path.cwd(); own=root/'sub2api-cancel-oracle-review'; candidate=root/'.spike-inputs/candidate/sub2api-cancel-oracle-repair'; frozen=root/'.spike-inputs/original-inputs/original-inputs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for manifest in [root/'.spike-inputs/INPUT-HASHES.json',root/'.spike-inputs/original-inputs/INPUT-HASHES.json',frozen/'INPUT-HASHES.json']:
    for n,h in json.loads(manifest.read_text()).items():assert sha(manifest.parent/n)==h,(manifest,n)
spec=importlib.util.spec_from_file_location('prepare',candidate/'prepare.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.INPUT=frozen
w2,ledger=m.prepare();base,_=m.prepare(baseline=True);w1=m.apply_delta(dict(base),(candidate/'w1-cancel-oracle.patch').read_text())
assert m.apply_delta(dict(w1),(candidate/'w2-restoration.patch').read_text())==w2
for n in m.MODULES[:2]:assert w1[n]==w2[n]
expected=w1[m.MODULES[2]].replace('x.close_ms - cancel <= 1250','x.close_ms - cancel <= 1200').replace('PHYSICAL_UPSTREAM_ABORT_OBSERVED_WITHIN_1250MS','PHYSICAL_UPSTREAM_ABORT_OBSERVED_WITHIN_1200MS');assert expected==w2[m.MODULES[2]]
(own/'.spike-inputs').mkdir(exist_ok=True);(own/'.spike-inputs/original-inputs').symlink_to(frozen,target_is_directory=True)
tests=own/'tests';tests.mkdir()
for n in ['oracle.test.mjs','broker.test.mjs','runner.test.mjs']:shutil.copyfile(candidate/n,tests/n)
results={}
for mode,files in [('old',base),('w1',w1),('w2',w2)]:
    stage=own/mode
    for n,s in files.items():
        p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s);subprocess.run(['node','--check',str(p)],check=True,capture_output=True)
    env=dict(os.environ,CANCEL_CODE=str(stage));r=subprocess.run(['node','--experimental-vm-modules','--test','--test-reporter=tap',*[str(tests/n) for n in ['oracle.test.mjs','broker.test.mjs','runner.test.mjs']]],env=env,capture_output=True,text=True,timeout=30)
    tap=r.stdout+r.stderr;(own/(mode+'.tap')).write_text(tap);results[mode]={k:int(re.search(r'^# '+k+r' (\d+)$',tap,re.M)[1]) for k in ['tests','pass','fail','cancelled','skipped']};results[mode]['exit_code']=r.returncode
assert results['old']['fail']==53 and results['w1']['fail']==18 and results['w2']['pass']==111 and results['w2']['fail']==0,results
rows=[json.loads(p.read_text()) for p in (root/'.spike-inputs/actual-rows').glob('*.json')]
assert sum(r['status']=='FAIL' for r in rows)==5 and sum(r['status']=='PASS' for r in rows)==1
for p in (root/'.spike-inputs/actual-rows').glob('*.json'):assert p.read_bytes()==(frozen/'actual-faults'/p.name).read_bytes()
results['source_ledger']=ledger;results['historical']={'FAIL':5,'PASS':1,'promoted':0};results['exact_test_hashes']={p.name:sha(p) for p in tests.glob('*.mjs')};(own/'verification.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps({k:v for k,v in results.items() if k in ['old','w1','w2','historical']}))
