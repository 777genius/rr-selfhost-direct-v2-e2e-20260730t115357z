"""Read-only packaging audit; original ledgers and historical verdicts remain immutable."""
import argparse, importlib.util, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('provenance',HERE/'verify-provenance.py')
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
m=v.m
p=argparse.ArgumentParser(); p.add_argument('--package-root',type=Path,default=HERE.parent/'sub2api-transport-r4'); p.add_argument('--base-root',type=Path); p.add_argument('--repo',type=Path)
p.add_argument('--pre-integration',action='store_true',help='audit the untouched supplied proposal before controller action')
a=p.parse_args(); package=a.package_root
proof=v.verify(package,a.base_root,a.repo)
prior=m.prior_bytes(a.base_root,a.repo); runtime=m.runtime_bytes(package,a.base_root,a.repo)
ledger=json.loads((package/'output-hashes.json').read_text())
actions=json.loads((HERE/'action-manifest.json').read_text())
replaced={row['target'].split('/',1)[1] for row in actions['replace']}
for row in actions['replace']:
    name=row['target'].split('/',1)[1]
    expected=row['before_sha256'] if a.pre_integration else row['after_sha256']
    if m.digest(v.checked_read(package,name))!=expected: raise ValueError('helper pre/post hash: '+name)
verified=0
for name,expected in ledger.items():
    if name.startswith('runtime/'): payload=runtime[name[8:]]
    elif name.startswith('historical-input/prior-code/'): payload=prior[name[len('historical-input/prior-code/'):]]
    elif name in replaced:
        old=package/name if a.pre_integration else package/'packaging-retention'/name
        payload=v.checked_read(old.parent,old.name)
    else: payload=v.checked_read(package,name)
    if m.digest(payload)!=expected: raise ValueError('original output ledger hash: '+name)
    verified+=1
validation=json.loads((package/'validation.json').read_text())
if validation['new_engine_gates']!='NOT RUN' or validation['physical_absolute_intersample_bound']!='NOTPROVEN': raise ValueError('gate promotion')
print(json.dumps({'integrity':'PASS','original_output_hashes_verified':verified,'runtime_files_verified':len(runtime),'historical':proof,'new_engine_gates':'NOT RUN','physical_absolute_intersample_bound':'NOTPROVEN','normal_handoff_scanner':'controller MUST PASS; not executed by worker'},indent=2))
