#!/usr/bin/env python3
"""Independent exact package/source/provenance checks, no Git/Go/services."""
import sys
sys.dont_write_bytecode=True
import argparse,ast,difflib,json,re
from pathlib import Path
import prepare
O=Path(__file__).resolve().parent
require=prepare.require
load=lambda n:json.loads((O/n).read_text())
def source_checks(upstream,gofmt):
    tree,m=prepare.prepare(upstream,gofmt)
    actual={p:b for p,b in tree.items() if p.startswith('backend/')}
    require({p:prepare.digest(b) for p,b in actual.items()}==load('executed-source-hashes.json'),'complete3158 actual source ledger mismatch')
    require(len(m['production_files'])==41 and len(m['final_files'])==60 and len(m['test_overlay_files'])==19,'41 production/19 test path scope mismatch')
    require(prepare.digest((O/'labtests.patch').read_bytes())=='a2276bd1f8a90a7554a81749f669bb4ffddf874883374824ecafa91a3b6e46d4','canonical lab patch changed')
    require(prepare.digest((O/'old-tests-overlay.patch').read_bytes())=='e86f3f5ac4f233d78ab05f3c4f8ef8cebf2356faa7470ad92e4f9933b1819abf','frozen old overlay changed')
    require(prepare.digest((O/'case-inventory.json').read_bytes())==m['inventory_sha256'],'old inventory changed')
    require(len({r['case_id'] for r in load('case-inventory.json')['cases']})==160,'old160 inventory mismatch')
    require(prepare.digest((O/'lab-source-manifest.json').read_bytes())==m['canonical_source_manifest_sha256'],'lab source manifest changed')
    # Restore every before byte from the bound old-W9-to-actual patch in memory.
    # Strict inverse hunks enforce both context and declared positions.
    raw=(O/'w9-to-actual.patch').read_text().splitlines(True)
    reverted=[];cursor=0
    while cursor<len(raw):
        require(raw[cursor].startswith('--- '),'unexpected binding patch header')
        oldheader,newheader=raw[cursor],raw[cursor+1];newfile=oldheader=='--- /dev/null\n';cursor+=2
        if newfile:
            name=newheader[6:].strip();require(name in tree,'missing added source');del tree[name]
            while cursor<len(raw) and not raw[cursor].startswith('--- '):cursor+=1
            continue
        reverted.extend(['--- a/'+newheader[6:],'+++ b/'+oldheader[6:]])
        while cursor<len(raw) and not raw[cursor].startswith('--- '):
            line=raw[cursor];cursor+=1
            if line.startswith('@@ '):
                h=re.fullmatch(r'@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@(.*)\n',line)
                require(h is not None,'bad inverse hunk');reverted.append('@@ -'+h[2]+' +'+h[1]+' @@'+h[3]+'\n')
            elif line.startswith('+'):reverted.append('-'+line[1:])
            elif line.startswith('-'):reverted.append('+'+line[1:])
            else:reverted.append(line)
    # Inverse engine accepts bytes through a minimal patch object, with no disk.
    class Patch:
        def read_bytes(self):return ''.join(reverted).encode()
    prepare.apply_exact(tree,Patch())
    old={p:b for p,b in tree.items() if p.startswith('backend/')}
    require(prepare.fingerprint(old)==m['old_w9_backend']['sha256'] and len(old)==3156,'restored complete actual old W9 source mismatch')
    frozen=tree.copy();prepare.apply_exact(frozen,O/'w9-to-final.patch')
    prepare.verify_files(frozen,m['frozen_W1_final_source_paths'],'frozen W1 all53 source bytes')
    up=prepare.read_tree(upstream)
    prod={r['path'] for r in m['production_files']}
    patch=''.join(''.join(difflib.unified_diff(up.get(p,b'').decode().splitlines(True),frozen[p].decode().splitlines(True),fromfile='a/'+p if p in up else '/dev/null',tofile='b/'+p,n=3)) for p in sorted(prod))
    require(prepare.digest(patch.encode())==m['frozen_W1_fullsource_patch_sha256'],'frozen437bd5 fullsource reconstruction mismatch')
    b=tree.copy();touched=prepare.apply_exact(b,O/'bulk-production.patch')
    require(touched=={'backend/internal/repository/account_repo.go'},'bulk production path scope changed')
    lines=(O/'bulk-production.patch').read_text().splitlines()
    require(sum(l.startswith('+') and not l.startswith('+++') for l in lines)==29 and sum(l.startswith('-') and not l.startswith('---') for l in lines)==6,'bulk +29/-6 scope mismatch')
    p='backend/internal/repository/account_repo.go';a=tree[p].decode();z=b[p].decode();start='func (r *accountRepository) BulkUpdate(';end='\ntype accountGroupQueryOptions'
    require(a[:a.index(start)]==z[:z.index(start)] and a[a.index(end):]==z[z.index(end):],'production changed outside BulkUpdate')
    aa=a[a.index(start):a.index(end)];zz=z[z.index(start):z.index(end)]
    require(aa[:aa.index('\tquery :=')]==zz[:zz.index('\tquery :=')],'bulk preflight/SET/WHERE changed')
    require(aa[aa.index('\tbaseCtx :='):aa.index('\tresult, err :=')]==zz[zz.index('\tbaseCtx :='):zz.index('\t// RETURNING')],'transaction acquisition changed')
    require(aa[aa.index('\tif updates.ProbeEnabled != nil {',aa.index('\tresult, err :=')):].replace('"account_ids": ids','"account_ids": updatedIDs').replace('baseCtx, ids','baseCtx, updatedIDs')==zz[zz.index('\tif updates.ProbeEnabled != nil {',zz.index('\t// RETURNING')):],'probe/commit/cache conditions changed')
    adapted=prepare.apply_exact(b,O/'unit-fixture-adaptation.patch')
    require(len(adapted)==5,'exact five fixture adaptations required')
    for p in adapted:
        require([l for l in tree[p].splitlines() if b'require.' in l or b'assert.' in l]==[l for l in b[p].splitlines() if b'require.' in l or b'assert.' in l],'old assertion changed: '+p)
    for p in tree:
        if p.endswith('_test.go') and p not in adapted:require(tree[p]==actual[p],'old fixture changed: '+p)
    for name,h in m['migrations'].items():require(prepare.digest(actual['backend/migrations/'+name])==h and actual['backend/migrations/'+name]==tree['backend/migrations/'+name],'migration changed')
    combined=tree.copy();prepare.apply_exact(combined,O/'w9-to-bulk.patch');prepare.apply_exact(combined,O/'w9-to-final.patch')
    require({p:b for p,b in combined.items() if p.startswith('backend/')}==actual,'exact official/old-W9 composition equivalence failed')
    require(prepare.digest(actual['backend/go.mod'])==prepare.digest(tree['backend/go.mod']) and prepare.digest(actual['backend/go.sum'])==prepare.digest(tree['backend/go.sum']),'actual Go dependency bytes changed')
    functions={n.name:n for n in ast.parse((O/'verify-runtime-receipts.py').read_text()).body if isinstance(n,ast.FunctionDef)}
    for n,h in m['preserved_runtime_functions'].items():require(prepare.digest(ast.dump(functions[n]).encode())==h,'nearest producer verifier function altered: '+n)
    return {'result':'PASS','production_paths':41,'source_paths':60,'gofmt_paths':57,'backend_files':3158,'backend_sha256':prepare.fingerprint(actual),'frozen_W1_fullsource':'437bd5 byte-exact reconstruction','old_inventory':160,'old_fixture_assertions':'preserved','old53_final_paths':'byte-exact before bulk adaptation','BulkUpdate_delta':'+29/-6 only','admin_delta':'+0/-1 unused import','migrations':'241/242/243 byte-exact','Go_dependency_bytes':'actual exact','preserved_producer_functions':list(m['preserved_runtime_functions']),'production_GO':False}
def artifact_checks():
    ledger=load('artifact-manifest.json');files={p.relative_to(O).as_posix():p for p in O.rglob('*') if p.is_file()}
    require(not any(p.is_symlink() for p in O.rglob('*')),'package symlinks forbidden')
    require(len(files)<=80 and set(files)==set(ledger['files'])|{'artifact-manifest.json'},'thin artifact file set mismatch')
    for n,h in ledger['files'].items():require(prepare.digest(files[n].read_bytes())==h,'artifact changed: '+n)
    return len(files)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upstream',type=Path,required=True);p.add_argument('--gofmt',type=Path,required=True);a=p.parse_args()
    count=artifact_checks();result=source_checks(a.upstream,a.gofmt);result['artifact_files']=count;print(json.dumps(result,indent=2))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,IndexError) as e:print(json.dumps({'result':'FAIL','reason':str(e)}),file=sys.stderr);sys.exit(1)
