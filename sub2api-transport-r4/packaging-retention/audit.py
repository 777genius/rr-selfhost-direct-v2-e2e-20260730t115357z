"""Read-only exact input/output, provenance, runtime and completion-contract audit."""
from pathlib import Path
import hashlib,json,subprocess,re
owned=Path(__file__).resolve().parent
root=owned.parent
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs=json.loads((owned/'input-hashes.json').read_text())
for name,expected in inputs.items():
    assert digest(root/name)==expected,'INPUT_CHANGED:'+name
outputs=json.loads((owned/'output-hashes.json').read_text())
actual={str(p.relative_to(owned)) for p in owned.rglob('*') if p.is_file() and p != owned/'output-hashes.json'}
assert actual==set(outputs),'OUTPUT_INVENTORY_CHANGED'
for name,expected in outputs.items():
    assert digest(owned/name)==expected,'OUTPUT_CHANGED:'+name
v=json.loads((owned/'validation.json').read_text())
assert v['new_engine_gates']=='NOT RUN' and v['physical_absolute_intersample_bound']=='NOTPROVEN'
assert v['historical']=={'FAIL':11,'NOT RUN':9,'synthetic_attempts':686,'effects':686,'cleanup_failures':0,'remaining_owned_resources':0}
assert v['canonical_overlay_loc']=={'added':64,'deleted':21,'changed':85}
changes=json.loads((owned/'changed-loc.json').read_text())
assert len(changes)==6
for name,row in changes.items():
    assert digest(owned/'overlay'/name)==row['result_sha256']
    assert digest(owned/'runtime'/name)==row['result_sha256']
# All support files stay exact frozen copies; only the six overlay paths differ.
for p in (owned/'historical-input/prior-code').rglob('*'):
    if not p.is_file():continue
    name=str(p.relative_to(owned/'historical-input/prior-code'))
    if name not in changes:assert digest(owned/'runtime'/name)==digest(p),name
for name in ['adapter.mjs','collector.py']:
    assert digest(owned/name)==digest(owned/'historical-input/candidate'/name)
assert digest(owned/'runtime/sub2api-transport-r4/adapter.mjs')==digest(owned/'adapter.mjs')
proof=json.loads(subprocess.run(['python3',str(owned/'verify-provenance.py')],check=True,capture_output=True,text=True).stdout)
assert proof['integrity']=='PASS' and proof['original_verdict']=='REQUESTCHANGES'
for file,pass_count,fail_count in [('node-tests.tap',23,0),('load-tests.tap',4,0),('independent-before.tap',4,4)]:
    log=(owned/'evidence'/file).read_text()
    assert re.search(r'pass '+str(pass_count)+r'\b',log) and re.search(r'fail '+str(fail_count)+r'\b',log),file
for name,lane in json.loads((owned/'evidence/overlay-verification.json').read_text()).items():
    assert lane['zero_fuzz'] and lane['zero_offset'] and lane['files']==6 and lane['result_hashes']=='PASS'
    assert 'pass 4' in lane['actual_load_tests'] and 'fail 0' in lane['actual_load_tests']
assert 'Ran 9 tests' in (owned/'evidence/python-tests.txt').read_text() and '\nOK\n' in (owned/'evidence/python-tests.txt').read_text()
print(json.dumps({'integrity':'PASS','input_files_verified':len(inputs),'output_files_verified':len(outputs),
    'historical_verdict':'REQUESTCHANGES','independent_regressions':'4 RED before / 4 GREEN after',
    'functional_local_tests':'27 PASS','collector_synthetic_tests':'9 PASS','both_sixfile_patches':'zero fuzz / zero offset / exact hashes',
    'engine_kernel_load':'NOT RUN','physical_absolute_intersample_bound':'NOTPROVEN'},sort_keys=True))
