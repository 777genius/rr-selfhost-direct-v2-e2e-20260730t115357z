import hashlib,json,os,pathlib,shutil,subprocess,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parent.parent
OWN=ROOT/'sub2api-memory-profile-review';INPUT=ROOT/'.spike-inputs';NEW=INPUT/'candidate/sub2api-memory-profile';OLD=INPUT/'original-inputs/candidate/sub2api-memory-profile';FULL=INPUT/'original-inputs/original-inputs'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(name,args):
 c=subprocess.run(args,capture_output=True,text=True,env=env,timeout=60)
 (OWN/(name+'.txt')).write_text(c.stdout+c.stderr);return {'returncode':c.returncode}
result={}
pins=json.loads((INPUT/'INPUT-HASHES.json').read_text());bad=[n for n,h in pins.items() if not (INPUT/n).is_file() or sha(INPUT/n)!=h]
result['custody']={'entries':len(pins),'mismatches':bad}
changes=[];same=[]
for p in OLD.iterdir():
 if p.is_file() and (NEW/p.name).is_file():
  (same if sha(p)==sha(NEW/p.name) else changes).append(p.name)
result['top_level_changed']=changes;result['top_level_unchanged']=same
result['legacy_manifest_sha256']=sha(NEW/'source-manifest.json')
result['overlay_unchanged']=sha(OLD/'overlay/backend/cmd/server/rr_sub2_profile.go')==sha(NEW/'overlay/backend/cmd/server/rr_sub2_profile.go')
with tempfile.TemporaryDirectory(dir=OWN) as td:
 base=pathlib.Path(td);pkg=base/'sub2api-memory-profile';pkg.mkdir();(pkg/'evidence').mkdir()
 for p in NEW.iterdir():
  if p.is_file():shutil.copyfile(p,pkg/p.name)
 shutil.copytree(NEW/'overlay',pkg/'overlay')
 (base/'.spike-inputs').symlink_to(FULL,target_is_directory=True)
 for n in ('sub2api-spike','sub2api-transport-r4'):(base/n).symlink_to(ROOT/n,target_is_directory=True)
 result['python']=run('python-tests',[sys.executable,'-m','unittest','discover','-s',str(pkg),'-p','test_*.py','-v'])
 result['node']=run('node-tests',['node','--test',str(pkg/'offline.test.mjs')])
 result['source_prepare']=run('source-prepare',[sys.executable,str(pkg/'prepare.py'),'--verify-only','--out',str(OWN/'source-prepare.json')])
 result['actual_audit']=run('actual-audit',[sys.executable,str(pkg/'audit_actual.py'),'--out',str(OWN/'actual-audit.json')])
 for side,target in [('old',OLD),('new',pkg)]:
  probe=base/side;probe.mkdir();(probe/'harness').mkdir();(probe/'harness/sub2api-memory-profile').symlink_to(target,target_is_directory=True)
  shutil.copyfile(INPUT/'prior-review/reproduce.py',probe/'reproduce.py')
  result['prescribed_'+side]=run('prescribed-'+side,[sys.executable,str(probe/'reproduce.py')])
  reg=base/('reg-'+side);reg.mkdir();(reg/'evidence').mkdir()
  for p in target.iterdir():
   if p.is_file():shutil.copyfile(p,reg/p.name)
  shutil.copyfile(NEW/'test_w3_regressions.py',reg/'test_w3_regressions.py')
  result['fixed_contract_'+side]=run('fixed-contract-'+side,[sys.executable,str(reg/'test_w3_regressions.py')])
(OWN/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
