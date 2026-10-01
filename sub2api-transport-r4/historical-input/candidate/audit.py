"""Read-only final input/output integrity audit; run from any directory."""
from pathlib import Path
import hashlib,json
owned=Path(__file__).resolve().parent
root=owned.parent
inputs=json.loads((owned/'input-hashes.json').read_text())
for name,digest in inputs.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest, 'INPUT_CHANGED:'+name
outputs=json.loads((owned/'output-hashes.json').read_text())
actual={str(p.relative_to(owned)) for p in owned.rglob('*') if p.is_file() and p.name!='output-hashes.json'}
assert actual==set(outputs), 'OUTPUT_INVENTORY_CHANGED'
for name,digest in outputs.items():
    assert hashlib.sha256((owned/name).read_bytes()).hexdigest()==digest, 'OUTPUT_CHANGED:'+name
before=json.loads((owned/'evidence/before.json').read_text())['regression_before_tests']
assert before['statuses']=={'FAIL':11,'NOT RUN':9} and before['synthetic_attempts']==686
v=json.loads((owned/'validation.json').read_text())
assert v['new_engine_gates']=='NOT RUN' and v['physical_absolute_intersample_bound']=='NOTPROVEN'
assert v['canonical_overlay_loc']=={'added':45,'deleted':16,'changed':61}
print(json.dumps({'input_files_verified':len(inputs),'output_files_verified':len(outputs),
                  'historical_failures_unchanged':True,'new_engine_gates':'NOT RUN',
                  'physical_absolute_intersample_bound':'NOTPROVEN','integrity':'PASS'},sort_keys=True))
