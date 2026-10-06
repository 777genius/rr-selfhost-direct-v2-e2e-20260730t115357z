from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, tempfile, unittest
root=Path.cwd(); own=root/'sub2api-transport-packaging-review'; inputs=root/'.spike-inputs'; pkg=inputs/'candidate/sub2api-transport-r4'; helper=inputs/'candidate/sub2api-transport-packaging'; base=inputs/'public-base'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(name,args,**kw):
 p=subprocess.run(args,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},**kw)
 (own/'evidence'/name).write_text(p.stdout+p.stderr)
 return {'exit':p.returncode,'command':list(map(str,args))}
manifest=json.loads((inputs/'INPUT-HASHES.json').read_text()); assert all(sha(inputs/n)==h for n,h in manifest.items())
summary={'outer_files_verified':len(manifest),'inputs_manifest_sha256':sha(inputs/'INPUT-HASHES.json')}
spec=importlib.util.spec_from_file_location('prepare',helper/'prepare-standalone.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
prior=m.prior_bytes(base); runtime=m.runtime_bytes(pkg,base)
summary.update(prior_files=len(prior),runtime_files=len(runtime),delta_paths=sorted(m.load('base-to-prior.delta.json')))
assert set(summary['delta_paths'])==set(json.loads((base/'BASE-PIN.json').read_text())['different_files'])
for row in json.loads((helper/'action-manifest.json').read_text())['replace']:
 assert sha(inputs/'candidate'/row['target'])==row['after_sha256']
 assert sha(inputs/'candidate'/row['retain_original_as'])==row['before_sha256']
 assert (inputs/'candidate'/row['target']).read_bytes()==(inputs/'candidate'/row['source']).read_bytes()
assert not (pkg/'historical-input/prior-code').exists() and not (pkg/'runtime').exists()
old=json.loads((inputs/'original-review/artifact-hashes.json').read_text())
for n,h in old.items():
 if n.startswith('evidence/'):
  assert sha(inputs/'original-review'/n)==h
reviewed=json.loads((inputs/'original-review/evidence/verification.json').read_text())['reviewed_source_hashes']
for n,h in reviewed.items():
 if n.startswith('candidate/sub2api-transport-r4/overlay/') or n=='candidate/sub2api-transport-r4/adapter.mjs': assert sha(inputs/n)==h
summary['unchanged_approved_overlays_adapter']=True
for name in ['audit','verify-provenance']:
 summary[name]=run(name+'.json',['python3',str(pkg/(name+'.py')),'--base-root',str(base)])
with tempfile.TemporaryDirectory(dir=own,prefix='disposable-') as d:
 temp=Path(d); out=temp/'runtime'
 summary['prepare']=run('plan.json',['python3',str(pkg/'prepare-standalone.py'),'--base-root',str(base),'--output',str(out),'--plan'])
 assert json.loads((own/'evidence/plan.json').read_text())==json.loads((pkg/'evidence/standalone-plan.json').read_text())==json.loads((inputs/'original-review/evidence/frozen-root-plan.json').read_text())
 fixture=temp/'prior-proposal';shutil.copytree(pkg,fixture)
 m.write_new(fixture/'historical-input/prior-code',prior)
 for row in json.loads((helper/'action-manifest.json').read_text())['replace']:
  name=row['target'].split('/',1)[1];(fixture/name).chmod(0o644);shutil.copyfile(fixture/'packaging-retention'/name,fixture/name)
 # Supplied historical tests assume an earlier delivery layout. Adapt only locations
 # and populate their exact pre-integration input fixture from verified reconstruction.
 spec=importlib.util.spec_from_file_location('packaging_tests',helper/'packaging_test.py'); tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
 tests.BASE=base;tests.PACKAGE=fixture
 with (own/'evidence/python-tests.txt').open('w') as log:
  result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
 summary['python']={'pass':result.testsRun-len(result.failures)-len(result.errors),'fail':len(result.failures),'errors':len(result.errors)}
 text=(helper/'packaging.test.mjs').read_text().replace("const packageRoot=resolve(root,'.spike-inputs/candidate');",'const packageRoot='+json.dumps(str(pkg))+';').replace("resolve(root,'.spike-inputs/public-base')",json.dumps(str(base))).replace("resolve(here,'prepare-standalone.py')",json.dumps(str(helper/'prepare-standalone.py'))).replace("resolve(here,'runtime-hashes.json')",json.dumps(str(helper/'runtime-hashes.json')))
 nodefile=temp/'packaging.test.mjs';nodefile.write_text(text)
 summary['node_packaging']=run('node-packaging.tap',['node','--test',str(nodefile)])
 goal=(helper/'goal-independent.test.mjs').read_text().replace("new URL('../sub2api-spike/evidence.mjs',import.meta.url)",'pathToFileURL('+json.dumps(str(root/'sub2api-spike/evidence.mjs'))+')').replace("new URL('../sub2api-spike/fixture/',import.meta.url)",'pathToFileURL('+json.dumps(str(root/'sub2api-spike/fixture')+'/')+')')
 goalfile=temp/'goal.test.mjs';goalfile.write_text(goal)
 summary['goal_independent']=run('goal-independent.tap',['node','--test',str(goalfile)])
 summary['goal_canonical']=run('goal-canonical.tap',['node','--test',str(root/'sub2api-spike/evidence.test.mjs'),str(root/'gateway-spike/evidence.test.mjs'),str(root/'sub2api-evidence-r2/client-contract.test.mjs')])
 summary['no_overwrite']=run('no-overwrite.txt',['python3',str(pkg/'prepare-standalone.py'),'--base-root',str(base),'--output',str(out)])
 assert summary['no_overwrite']['exit']!=0
 assert all(sha(out/n)==h for n,h in m.load('runtime-hashes.json').items())
summary['supplied_root_gates']=json.loads((inputs/'actual-root-gates.json').read_text())
summary['test_adaptations']='Only path constants changed in disposable Node copies; Python BASE/PACKAGE rebound to exact reconstructed pre-integration fixture. Production helper/wrappers unchanged. All generated fixture trees removed.'
(own/'evidence/verification.json').write_text(json.dumps(summary,indent=2)+'\n')
freeze={str(p.relative_to(root)):sha(p) for folder in [inputs/'candidate',inputs/'original-review',inputs/'public-base'] for p in sorted(folder.rglob('*')) if p.is_file()}
(own/'frozen-input-hashes.json').write_text(json.dumps(freeze,indent=2)+'\n')
assert all(sha(inputs/n)==h for n,h in manifest.items())
print(json.dumps(summary,indent=2))
