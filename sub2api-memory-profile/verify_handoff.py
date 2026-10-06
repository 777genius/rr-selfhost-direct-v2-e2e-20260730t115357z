"""Offline crosscheck of actual isolated W2 patch through profile source binding.
Writes only the owned profile package evidence directory. Does not build or run Go, Docker, or root tools.
"""
from pathlib import Path
import copy,hashlib,json,re,sys,tempfile
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
sys.path.insert(0,str(HERE))
from reviewed_source import apply_reviewed,apply_patch
from analyze import validate_reviewed_manifest,expected_source_manifest
from launch_contracts import BASE

def sha(b):return hashlib.sha256(b).hexdigest()
def reverse_exact(new,patch):
    lines=patch.splitlines(keepends=True);current=new.splitlines(keepends=True);result=[];cursor=0;i=2;count=0
    assert lines[0].startswith('--- a/backend/') and lines[1].startswith('+++ b/backend/')
    while i<len(lines):
        m=re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n',lines[i]);assert m is not None;i+=1
        start=int(m[3])-1;assert cursor<=start<=len(current);result.extend(current[cursor:start]);cursor=start
        before=[];after=[]
        while i<len(lines) and not lines[i].startswith('@@ '):
            line=lines[i];i+=1;assert line[0] in ' +-'
            if line[0] in ' -':before.append(line[1:])
            if line[0] in ' +':after.append(line[1:])
        assert len(before)==int(m[2] or 1) and len(after)==int(m[4] or 1)
        assert current[cursor:cursor+len(after)]==after
        result.extend(before);cursor+=len(after);count+=1
    result.extend(current[cursor:]);return ''.join(result),count

def main():
    frozen=PROJECT/'.spike-inputs/original-inputs';package=PROJECT/'sub2api-stream-memory-fork'
    legacy_path=frozen/'candidate/sub2api-memory-profile/source-manifest.json';legacy=json.loads(legacy_path.read_text())
    files={str(p.relative_to(frozen/'actual-source')):p.read_bytes() for p in (frozen/'actual-source').rglob('*') if p.is_file()}
    expected=dict(legacy['source_after_sha256']);expected.pop('backend/cmd/server/rr_sub2_profile.go')
    assert {n:sha(b) for n,b in files.items()}==expected
    source=json.loads((package/'SOURCE.json').read_text());production=[f for f in source['files'] if f['kind']=='production']
    full=package/'patches/production.patch';filemap={f['path']:{'before_sha256':f['before_sha256'],'after_sha256':f['after_sha256']} for f in production}
    assert len(filemap)==4
    for f in production:assert sha(files[f['path']])==f['before_sha256']
    before_files=dict(files)
    preservation=source['preservation_sources']
    for row in preservation:assert sha(files[row['path']])==row['source_sha256']
    # This is explicitly a synthetic external binary prepin, not a real binary.
    spec={'schema':'rrsub2profile-reviewed-v1','base_manifest_sha256':sha(legacy_path.read_bytes()),'base_image':BASE,'binary_sha256':'e'*64,'patches':[{'path':str(full.resolve()),'sha256':sha(full.read_bytes()),'files':filemap}]}
    with tempfile.TemporaryDirectory(dir=HERE) as td:
        p=Path(td)/'reviewed-native-synthetic-binary-pin.json';p.write_text(json.dumps(spec)+'\n');receipt=apply_reviewed(p,legacy_path,files)
    for f in production:assert files[f['path']]==(package/f['overlay_path']).read_bytes()
    modified=sorted(n for n in files if files[n]!=before_files.get(n));assert modified==sorted(filemap)
    profile='backend/cmd/server/rr_sub2_profile.go';files[profile]=(frozen/'candidate/sub2api-memory-profile/overlay'/profile).read_bytes()
    manifest=copy.deepcopy(legacy);manifest['reviewed_source']=receipt;manifest['source_after_sha256']={n:sha(b) for n,b in sorted(files.items())};manifest['source_patch_files']=sorted(set(legacy['source_patch_files'])|set(filemap));validate_reviewed_manifest(manifest)
    with tempfile.TemporaryDirectory(dir=HERE/'evidence') as td:
        expected=Path(td)/'source-manifest.json';expected.write_text(json.dumps(manifest)+'\n')
        accepted_sha,accepted=expected_source_manifest(expected)
        assert accepted_sha==sha(expected.read_bytes()) and accepted==manifest
    delta=json.loads((package/'W2-DELTA.json').read_text());ownership=delta['files'][0];new=(package/ownership['overlay_path']).read_text();patch=(package/ownership['patch']).read_text()
    assert sha(patch.encode())==delta['patches'][ownership['patch']]
    old,hunks=reverse_exact(new,patch);assert sha(old.encode())==ownership['before_sha256'];assert sha(new.encode())==ownership['after_sha256']
    forward={ownership['path']:old.encode()};assert apply_patch(forward,patch)=={ownership['path']};assert forward[ownership['path']]==new.encode()
    old_comment="\t// The caller's deadline/cancellation bounds prefix reads. After output starts,\n\t// retain the existing usage-drain policy. Closing Body interrupts Scanner.Read."
    new_comment="\t// The caller's deadline/cancellation bounds prefix reads until replay handoff.\n\t// Ownership is separate from successful semantic output: a failed prefix or\n\t// first semantic write must retain the existing upstream usage-drain policy.\n\t// Closing Body interrupts Scanner.Read.\n\tprefixOwnsCancellation := true"
    minimal=old.replace(old_comment,new_comment).replace('\t\tstopPrefixCancel()\n','\t\tstopPrefixCancel()\n\t\tprefixOwnsCancellation = false\n').replace('if !clientOutputStarted && ctx.Err() != nil {','if prefixOwnsCancellation && ctx.Err() != nil {')
    assert minimal==new
    handoff=new[new.index('\twritePendingLines :='):new.index('\tensureResponseFailedTerminal :=')]
    assert handoff.index('stopPrefixCancel()')<handoff.index('prefixOwnsCancellation = false')<handoff.index('prefix.CommitTo(w)')
    assert new.count('if prefixOwnsCancellation && ctx.Err() != nil {')==2
    w1copy=json.loads((package/'evidence/w1-copy.json').read_text());unchanged=[]
    for rel,h in w1copy['files'].items():
        if rel.startswith(('production/','tests/')) and rel.endswith('.go') and not rel.endswith('/openai_gateway_passthrough.go'):
            assert sha((package/rel).read_bytes())==h;unchanged.append(rel)
    assert len(unchanged)==7
    repro=package/'tests/backend/internal/service/stream_memory_replay_handoff_test.go';assert sha(repro.read_bytes())==delta['files'][1]['after_sha256']
    prior=json.loads((PROJECT/'sub2api-stream-memory-review/evidence.json').read_text());summary_gates={}
    for suite,count in [('green',35),('native',292),('probe',63)]:
        r=prior['supplied_receipts'][suite]['receipt'];assert r['production_patch_sha256']==sha(full.read_bytes()) and r['exit']==0 and r['pass_count']==count and r['skip_count']==0 and r['compile_failed'] is False
        summary_gates[suite]={'count':count,'kind':'archived embedded summary only; original receipt bytes/raw logs absent from current frozen bundle'}
    result={'status':'SOURCE_AND_BINDING_VERIFIED_OFFLINE','native_baseline_files_checked':len(before_files),'native_probe_preservation_pins_verified':len(preservation),'production_patch_sha256':sha(full.read_bytes()),'real_production_patch_files_applied_and_matched':modified,'complete_merged_source_map_accepted':True,'repaired_explicit_manifest_authorization_executed':True,'merged_binary_pin':'SYNTHETIC e*64; no real build/binary pin verified','profiling_file_preserved':manifest['source_after_sha256'][profile]==legacy['source_after_sha256'][profile],'dependencies_and_toolchain_source_preserved':all(files[n]==b for n,b in before_files.items() if n not in filemap),'W2_delta_hunks_reversed_and_reapplied':hunks,'W1_before_sha256_recovered':sha(old.encode()),'minimal_ownership_repair_entire_source_identity':True,'callback_stop_then_ownership_release_then_replay':True,'both_pre_handoff_guards_use_ownership':True,'seven_W1_source_and_test_files_byte_unchanged':unchanged,'reproducer_sha256':sha(repro.read_bytes()),'profiled_frozen_source_contains_W2_ownership_state':b'prefixOwnsCancellation' in before_files[ownership['path']],'archived_summary_bindings':summary_gates,'Go':'NOT RUN','race':'NOT RUN / original receipt absent','full_root_raw':'NOT SUPPLIED HERE','goal_complete':False,'producer':'current repaired W3 analyzer and unchanged exact patch engine','limitations':'Static exact-byte/source binding and archived summary consistency; no fresh handler execution, callback race proof, merged binary, or new profile/RSS claim.'}
    (HERE/'evidence/reviewed-handoff-w3.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
