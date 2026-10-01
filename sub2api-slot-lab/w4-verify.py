"""Bounded offline verification; never invokes native/root/Docker commands."""
from pathlib import Path
from unittest.mock import patch
import hashlib, json, os, subprocess, sys, unittest
sys.dont_write_bytecode = True
HERE=Path(__file__).resolve().parent; REPO=HERE.parent
E=HERE/'w4-evidence'; E.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
inputs=json.loads((REPO/'.spike-inputs/INPUT-HASHES.json').read_text())
assert all(sha(REPO/'.spike-inputs'/n)==h for n,h in inputs.items()), 'frozen input drift'
w3=REPO/'.spike-inputs/candidate/sub2api-slot-lab'
changed=[str(p.relative_to(w3)) for p in w3.rglob('*') if p.is_file() and (HERE/p.relative_to(w3)).read_bytes()!=p.read_bytes()]
assert changed==['root-driver.py'], changed
old=(w3/'root-driver.py').read_text(); new=(HERE/'root-driver.py').read_text()
assert new==old.replace("'output_to_stdout':False", "'output_to_stdout':True").replace("'LOG_OUTPUT_TO_STDOUT':'false'", "'LOG_OUTPUT_TO_STDOUT':'true'")
runs={}
def run(name,args,env=None):
    r=subprocess.run(args,cwd=REPO,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1',**(env or {})},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
    (E/name).write_bytes(r.stdout); runs[name]={'command':args,'exit':r.returncode}; return r.returncode
assert run('logging-red.txt',[sys.executable,'-m','unittest','discover','-s','sub2api-slot-lab','-p','logging_preflight_test.py'],{'SLOT_LOGGING_PACKAGE':str(w3)})==1
assert run('logging-green.txt',[sys.executable,'-m','unittest','discover','-s','sub2api-slot-lab','-p','logging_preflight_test.py'])==0
assert run('node-34.tap',['node','--test','--test-reporter=tap','sub2api-slot-lab/offline.test.mjs','sub2api-slot-lab/recovery-contract.test.mjs'])==0
# Preserve W3 tests byte-for-byte. Their frozen W2 and image inputs moved one
# directory deeper in this slot; relocate only test input paths in memory.
real=Path.read_text
def read(self,*a,**k):
    if self==REPO/'.spike-inputs/actual-image.json':
        return real(REPO/'.spike-inputs/original-inputs/actual-image.json',*a,**k)
    return real(self,*a,**k)
with patch.object(Path,'read_text',read):
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='*_test.py')
sys.modules['launch_transport_test'].BASELINE=REPO/'.spike-inputs/original-inputs/candidate/sub2api-slot-lab'
with (E/'python-16.txt').open('w') as out:
    result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
assert result.wasSuccessful() and result.testsRun==16
runs['python-16.txt']={'command':[sys.executable,'sub2api-slot-lab/w4-verify.py'],'tests':16,'exit':0,'relocation':'frozen W2/image test paths only; test files unchanged'}
ledger={'schema':'slot-W4-native-logging-preflight-v1','frozen_inputs_verified':len(inputs),'W3_changed_files':changed,
        'native_validator_sha256':sha(REPO/'.spike-inputs/native-config-validator.go'),
        'actual_W3_failure_sha256':sha(REPO/'.spike-inputs/actual-root-failure.json'),
        'actual_84_row_root_run':'PENDING controller; not executed by worker','runs':runs,
        'hashes':{str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*') if p.is_file() and p.name!='W4-LEDGER.json'}}
(HERE/'W4-LEDGER.json').write_text(json.dumps(ledger,indent=2)+'\n')
assert len([p for p in HERE.rglob('*') if p.is_file()])<60
print('PASS: 34 Node, 16 Python; frozen W3 RED, repaired GREEN; frozen inputs intact; <60 files')
