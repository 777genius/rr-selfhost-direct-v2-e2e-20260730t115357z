"""Offline regression verification; reconstruct historical fixtures only in disposable storage."""
import hashlib, importlib.util, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
HERE=ROOT/'sub2api-transport-packaging'; INPUTS=ROOT/'.spike-inputs'
PACKAGE=INPUTS/'candidate/sub2api-transport-r4'; BASE=INPUTS/'public-base'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
summary={}
outer=json.loads((INPUTS/'INPUT-HASHES.json').read_text())
assert all(sha(INPUTS/name)==expected for name,expected in outer.items())
summary['outer_inputs_verified']=len(outer)
frozen=INPUTS/'candidate/sub2api-transport-packaging'
summary['frozen_package_hashes']={str(p.relative_to(frozen)):sha(p) for p in sorted(frozen.rglob('*')) if p.is_file()}
for name in ('prepare-standalone.py','audit.py','base-pin.json','base-hashes.json','base-to-prior.delta.json','prior-hashes.json','runtime-hashes.json'):
    assert (HERE/name).read_bytes()==(frozen/name).read_bytes(),name
summary['preserved_reconstruction_files']=True
m=load_module('prepare',HERE/'prepare-standalone.py')
prior=m.prior_bytes(BASE); runtime=m.runtime_bytes(PACKAGE,BASE)
assert len(prior)==102 and len(runtime)==103
assert set(m.load('base-to-prior.delta.json'))==set(json.loads((BASE/'BASE-PIN.json').read_text())['different_files'])
original_manifest=json.loads((PACKAGE/'historical-input/INPUT-HASHES.json').read_text())
assert all(m.digest(payload)==original_manifest['prior-code/'+name] for name,payload in prior.items())
summary.update(base_files=len(m.base_bytes(BASE)),prior_files=len(prior),runtime_files=len(runtime),delta_files=8,public_base_sha=m.SHA)
actions=json.loads((HERE/'action-manifest.json').read_text())
summary['installed_wrappers']={}
for row in actions['replace']:
    assert sha(INPUTS/'candidate'/row['target'])==row['after_sha256']
    assert sha(ROOT/row['source'])==row['after_sha256']
    assert sha(INPUTS/'candidate'/row['retain_original_as'])==row['before_sha256']
    summary['installed_wrappers'][row['target']]={'sha256':row['after_sha256'],'unchanged':True,'retained_original_sha256':row['before_sha256']}
with tempfile.TemporaryDirectory(prefix='packaging-repair-') as d:
    temp=Path(d); fixture=temp/'original-proposal'; shutil.copytree(PACKAGE,fixture)
    for p in fixture.rglob('*'):
        if p.is_file(): p.chmod(0o644)
    m.write_new(fixture/'historical-input/prior-code',prior)
    for row in actions['replace']:
        name=row['target'].split('/',1)[1]; shutil.copyfile(fixture/'packaging-retention'/name,fixture/name)
    tests=load_module('packaging_tests',HERE/'packaging_test.py'); tests.BASE=BASE; tests.PACKAGE=fixture
    with (HERE/'python-tests.txt').open('w') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    assert result.wasSuccessful()
    summary['python_packaging']={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)}
    text=(HERE/'packaging.test.mjs').read_text().replace("const packageRoot=resolve(root,'.spike-inputs/candidate');",'const packageRoot='+json.dumps(str(PACKAGE))+';').replace("resolve(root,'.spike-inputs/public-base')",json.dumps(str(BASE))).replace("resolve(here,'prepare-standalone.py')",json.dumps(str(HERE/'prepare-standalone.py'))).replace("resolve(here,'runtime-hashes.json')",json.dumps(str(HERE/'runtime-hashes.json')))
    nodefile=temp/'packaging.test.mjs'; nodefile.write_text(text)
    proc=subprocess.run(['node','--test',str(nodefile)],capture_output=True,text=True)
    (HERE/'node-tests.tap').write_text(proc.stdout+proc.stderr)
    assert proc.returncode==0,proc.stderr
    summary['node_packaging']={'exit':proc.returncode,'tests':2}
    # Actual disposable final assembly: corrected helper, unchanged installed wrappers,
    # original retained helpers and history, no prior-code/runtime delivery subtree.
    assembly=temp/'assembly'; assembly.mkdir()
    package=assembly/'sub2api-transport-r4'; shutil.copytree(PACKAGE,package)
    shutil.copytree(HERE,assembly/'sub2api-transport-packaging')
    assert not (package/'historical-input/prior-code').exists()
    assert not (package/'runtime').exists()
    commands=[]
    for program,filename in [('verify-provenance.py','provenance-result.json'),('audit.py','audit-result.json')]:
        cmd=['python3',str(package/program),'--base-root',str(BASE)]
        proc=subprocess.run(cmd,capture_output=True,text=True)
        assert proc.returncode==0,proc.stderr
        (HERE/filename).write_text(proc.stdout)
        commands.append({'program':program,'exit':proc.returncode,'result':json.loads(proc.stdout)})
    out=assembly/'generated'
    proc=subprocess.run(['python3',str(package/'prepare-standalone.py'),'--base-root',str(BASE),'--output',str(out),'--plan'],capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)==json.loads((PACKAGE/'evidence/standalone-plan.json').read_text())
    assert all(sha(out/name)==expected for name,expected in m.load('runtime-hashes.json').items())
    commands.append({'program':'prepare-standalone.py','exit':proc.returncode,'unchanged_plan':True,'runtime_hashes_verified':103})
    summary['disposable_assembly']=commands
summary['test_adaptations']='Historical Python tests rebound BASE/PACKAGE to a byte-verified disposable original-proposal fixture; Node test location constants adapted in a disposable copy. Helper and installed wrapper bytes are exercised unchanged. All generated trees removed.'
summary['current_helper_sha256']=sha(HERE/'verify-provenance.py')
summary['historical_output_ledger_sha256']=sha(PACKAGE/'output-hashes.json')
summary['historical_input_manifest_sha256']=sha(PACKAGE/'historical-input/INPUT-HASHES.json')
assert all(sha(INPUTS/name)==expected for name,expected in outer.items())
(HERE/'repair-verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='frozen_package_hashes'},indent=2))
