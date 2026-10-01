"""Apply frozen unified patches in memory; publish paths and hashes only."""
from pathlib import Path
import hashlib,json,re
ROOT=Path.cwd()
OUT=ROOT/'sub2api-candidate-review-v4'
def sha(b): return hashlib.sha256(b).hexdigest()
def load(p): return json.loads((ROOT/p).read_text())
def apply(patch,initial=None):
    lines=(ROOT/patch).read_bytes().splitlines(keepends=True)
    result={} if initial is None else dict(initial)
    i=0; adds=dels=0
    while i<len(lines):
        if not lines[i].startswith(b'diff --git '): i+=1;continue
        path=lines[i].decode().strip().split(' b/',1)[1];i+=1
        while not lines[i].startswith(b'--- '): i+=1
        old=lines[i][4:].strip();i+=2
        original=(result[path] if initial is not None and path in result else (b'' if old==b'/dev/null' else (ROOT/'.spike-inputs/upstream'/path).read_bytes()))
        src=original.splitlines(keepends=True); cursor=0; dst=[]
        while i<len(lines) and not lines[i].startswith(b'diff --git '):
            if not lines[i].startswith(b'@@ '): i+=1;continue
            m=re.match(rb'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[i]);assert m
            start=int(m[1]); oldcount=int(m[2] or b'1');newcount=int(m[4] or b'1')
            target=start-1 if oldcount else start
            assert target>=cursor,(path,target,cursor)
            dst.extend(src[cursor:target]);cursor=target;i+=1;oc=nc=0
            while i<len(lines) and lines[i][:1] in (b' ',b'+',b'-'):
                mark=lines[i][:1];payload=lines[i][1:]
                if mark in (b' ',b'-'):
                    assert cursor<len(src) and src[cursor]==payload,(path,cursor)
                    cursor+=1;oc+=1
                if mark in (b' ',b'+'):dst.append(payload);nc+=1
                adds+=mark==b'+';dels+=mark==b'-';i+=1
            assert (oc,nc)==(oldcount,newcount),(path,oc,nc,oldcount,newcount)
        dst.extend(src[cursor:]);result[path]=b''.join(dst)
    return result,{'added_lines':adds,'removed_lines':dels,'changed_lines':adds+dels}
newpatch='.spike-inputs/native/patches/native-reasoning.patch'
oldpatch='.spike-inputs/native/checks/rejected432.patch'
delta='.spike-inputs/native/checks/r3-repair.patch'
new,ncounts=apply(newpatch);old,ocounts=apply(oldpatch);chained,dcounts=apply(delta,old)
manifest=load('.spike-inputs/native/SOURCE.json');oldmanifest=load('.spike-inputs/native/checks/r3-rejected-source.json')
assert sha((ROOT/newpatch).read_bytes())==manifest['patch']['sha256']=='30cb1d6b5060cbf41b822fa46fc996fafd91acbc470d89bf2882be90eb24b4d5'
assert sha((ROOT/oldpatch).read_bytes())==oldmanifest['patch']['sha256']=='432cffdf3b2a2659da76403242942b45177d69f60fda17efd14605d7798e7135'
assert chained==new
assert ncounts=={k:manifest['patch'][k] for k in ncounts}
assert ocounts=={k:oldmanifest['patch'][k] for k in ocounts}
records=[]
for f in manifest['files']:
    p=f['path'];original=ROOT/'.spike-inputs/upstream'/p
    observed_original=sha(original.read_bytes()) if original.exists() else None
    assert observed_original==f['original_sha256'],p
    assert sha(new[p])==f['patched_sha256'],p
    oldentry=next((x for x in oldmanifest['files'] if x['path']==p),None)
    if oldentry: assert sha(old[p])==oldentry['patched_sha256'],p
    records.append({'path':p,'frozen_original_path':str(original.relative_to(ROOT)), 'original_sha256':observed_original,'patched_sha256':sha(new[p]),'reviewed432_sha256':sha(old[p]) if p in old else None,'byte_identical_to_reviewed432':old.get(p)==new[p]})
assert set(new)==set(f['path'] for f in manifest['files'])
unchanged=[p for p in old if old[p]==new[p]]
assert len(unchanged)==15
reference='backend/internal/service/independent_reference_namespace_test.go'
prescription=ROOT/'sub2api-candidate-review/independent_reference_namespace_test.go'
assert new[reference]==prescription.read_bytes()
assert len(new[reference].splitlines())==42
assert all(old[p]==(ROOT/'sub2api-candidate-review/native-patched'/p).read_bytes() for p in old)
evidence={ 'method':'Strict unified-hunk application to frozen upstream bytes entirely in memory; context/count assertions; no persisted native source copies', 'upstream_revision':manifest['upstream']['revision'],'patches':[{ 'path':p,'sha256':sha((ROOT/p).read_bytes()),'counts':c} for p,c in [(newpatch,ncounts),(oldpatch,ocounts),(delta,dcounts)]], 'files':records,'verified_original_hashes':sum(x['original_sha256'] is not None for x in records),'verified_patched_hashes':len(records),'all_15_other_files_byte_identical':True,'all_16_reviewed432_files_match_canonical_materialization':True,'delta_application_equals_full_replacement':True,'independent_reference_test':{'path':str(prescription.relative_to(ROOT)),'sha256':sha(new[reference]),'lines':42,'byte_identical':True},'input_identity':[{'path':p,'sha256':sha((ROOT/p).read_bytes())} for p in ['sub2api-candidate-review/REPORT.md','sub2api-candidate-review/review.json','.spike-inputs/native/SOURCE.json','.spike-inputs/native/checks/r3-rejected-source.json','.spike-inputs/native/checks/r3-source-audit.json','sub2api-fork-review-v2/independent_boundary_test.go.txt','.spike-inputs/native/checks/r1-r2-preserved-patterns.json','.spike-inputs/native/checks/regression-oracles.json','.spike-inputs/native/checks/patched-execution.json']]}
(OUT/'source-hashes.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({'status':'PASS','original_hashes':evidence['verified_original_hashes'],'patched_hashes':len(records),'unchanged_files':len(unchanged),'counts':ncounts,'delta':dcounts,'independent_test_byte_identical':True}))
