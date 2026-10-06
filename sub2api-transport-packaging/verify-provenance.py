"""Validate retained history and reconstructed prior inputs without duplicated source."""
import argparse, importlib.util, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('prepare', HERE/'prepare-standalone.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def verify(package, base_root=None, repo=None):
    frozen=Path(package)/'historical-input'
    prior=m.prior_bytes(base_root,repo)
    def payload(name):
        prefix='prior-code/'
        return prior[name[len(prefix):]] if name.startswith(prefix) else checked_read(frozen,name)
    manifest=json.loads(checked_read(frozen,'INPUT-HASHES.json'))
    for name, expected in manifest.items():
        if m.digest(payload(name)) != expected: raise ValueError('historical input hash: '+name)
    for directory, ledger in [('candidate','output-hashes.json'),('independent-review','artifact-hashes.json')]:
        entries=json.loads(checked_read(frozen,directory+'/'+ledger))
        for name,expected in entries.items():
            if m.digest(checked_read(frozen,directory+'/'+name))!=expected: raise ValueError('retained output hash: '+name)
    reviewed=json.loads(checked_read(frozen,'independent-review/evidence/reviewed-source-hashes.json'))
    prefix='.spike-inputs/candidate/sub2api-transport-r2/'
    for name,expected in reviewed.items():
        if not name.startswith(prefix) or m.digest(checked_read(frozen,'candidate/'+name[len(prefix):]))!=expected: raise ValueError('reviewed hash: '+name)
    execution=json.loads(checked_read(frozen,'execution.json'))
    historical={s:sum(r['status']==s for r in execution['results']) for s in ['FAIL','NOT RUN']}
    if historical!={'FAIL':11,'NOT RUN':9} or execution['total_upstream_attempts']!=686 or sum(r['effects'] for r in execution['results'])!=686: raise ValueError('history changed')
    if not all(r['cleanup']['failures']==0 and not r['cleanup']['remaining_resources'] for r in execution['results']): raise ValueError('cleanup history changed')
    if json.loads(checked_read(frozen,'independent-review/review.json'))['verdict']!='REQUESTCHANGES': raise ValueError('historical verdict changed')
    return {'integrity':'PASS','provided_files':len(manifest),'prior_files':len(prior),'historical':historical,'effects':686,'history_reexecuted':False,'original_verdict':'REQUESTCHANGES'}

def checked_read(root,name):
    from pathlib import PurePosixPath
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p)!=name or '\\' in name: raise ValueError('unsafe historical path')
    target=Path(root)
    if any(ancestor.is_symlink() for ancestor in (target.absolute(), *target.absolute().parents)):
        raise ValueError('historical symlink root or ancestor')
    for part in p.parts:
        target=target/part
        if target.is_symlink(): raise ValueError('historical symlink')
    return target.read_bytes()

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--package-root',type=Path,default=HERE.parent/'sub2api-transport-r4'); p.add_argument('--base-root',type=Path); p.add_argument('--repo',type=Path)
    a=p.parse_args(); print(json.dumps(verify(a.package_root,a.base_root,a.repo),indent=2))
