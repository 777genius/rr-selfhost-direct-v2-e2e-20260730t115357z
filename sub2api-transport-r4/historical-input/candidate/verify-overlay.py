"""Apply exact patch only to a disposable owned copy; syntax and plan checks."""
from pathlib import Path
import hashlib, json, shutil, subprocess, tempfile
owned = Path(__file__).resolve().parent
root = owned.parent
changes = json.loads((owned/'changed-loc.json').read_text())
with tempfile.TemporaryDirectory(dir=owned, prefix='verify-') as d:
    dest=Path(d)
    for name, row in changes.items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == row['original_sha256']
        p=dest/name; p.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(root/name,p)
    subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(owned/'lab-overlay.patch')],cwd=dest,check=True,capture_output=True)
    for name,row in changes.items():
        p=dest/name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == row['result_sha256']
        if p.suffix == '.mjs': subprocess.run(['node','--check',str(p)],check=True,capture_output=True)
    for name in ['plan.mjs','receipts.mjs']:
        shutil.copyfile(root/'sub2api-regression-lab'/name,dest/'sub2api-regression-lab'/name)
    shutil.copytree(root/'sub2api-spike',dest/'sub2api-spike',ignore=shutil.ignore_patterns('evidence','operator','*.json','*.md','*.test.mjs'))
    (dest/'sub2api-transport-r2').mkdir()
    shutil.copyfile(owned/'adapter.mjs',dest/'sub2api-transport-r2/adapter.mjs')
    result=subprocess.run(['node','sub2api-regression-lab/run.mjs','--plan'],cwd=dest,check=True,capture_output=True,text=True)
    plan=json.loads(result.stdout)
    assert {s:sum(x['stage']==s for x in plan['cases']) for s in ['cancel','uncertainty','memory','soak']} == {'cancel':12,'uncertainty':8,'memory':18,'soak':2}
    assert sum(x.get('count',0) for x in plan['cases'])==500 and plan['budget']['max_actual_upstream_attempts']==2000
print('PASS: exact canonical patch, zero fuzz, matching output hashes, syntax, runnable original40case plan')

with tempfile.TemporaryDirectory(dir=owned,prefix='verify-frozen-') as d:
    dest=Path(d)
    for name in changes:
        p=dest/name; p.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/'.spike-inputs/prior-code'/name,p)
    subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(owned/'frozen-root-overlay.patch')],cwd=dest,check=True,capture_output=True)
    for name,row in changes.items():
        assert hashlib.sha256((dest/name).read_bytes()).hexdigest()==row['result_sha256']
print('PASS: exact frozen fresh-probe root patch, zero fuzz, same final output hashes')
