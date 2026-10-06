"""Offline exact-byte verification and disposable overlay assembly. No Go/Docker."""
from pathlib import Path
import argparse, difflib, hashlib, json, shutil
OWN = Path(__file__).resolve().parent
INPUT = OWN.parent / '.spike-inputs'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_inputs():
    pins = json.loads((INPUT/'INPUT-HASHES.json').read_text())
    for name, digest in pins.items():
        p = INPUT/name
        if not p.is_file() or sha(p) != digest: raise ValueError('FROZEN_INPUT_MISMATCH: '+name)
    return pins

def actual_code(name, expected):
    candidates = [INPUT/'runtime'/name,
                  INPUT/'transport-artifacts'/Path(name).name,
                  INPUT/'transport-artifacts/historical-input/prior-code'/name, OWN.parent/name]
    for p in candidates:
        if p.is_file():
            b = p.read_bytes()
            if name.endswith('/common.mjs'):
                b = b.replace(b'return { ...expected, engine_pid: observed.engine_pid, clock: observed.clock };',
                    b"must(/^[a-f0-9]{64}$/.test(observed.container_id), 'ROOT_CONTAINER_ID_REQUIRED'); return { ...expected, engine_pid: observed.engine_pid, clock: observed.clock, container_id: observed.container_id };")
            if hashlib.sha256(b).hexdigest() == expected: return b
    raise ValueError('ACTUAL_CODE_NOT_RECONSTRUCTABLE: '+name)

def generate(stage=None, collector_source=None, reviewed=None, verify_only=False):
    pins = verify_inputs()
    if sha(OWN/'source-manifest.json')!=sha(INPUT/'candidate/sub2api-memory-profile/source-manifest.json'): raise ValueError('LEGACY_MANIFEST_CHANGED')
    source = {str(p.relative_to(INPUT/'actual-source')):sha(p)
              for p in (INPUT/'actual-source').rglob('*') if p.is_file()}
    # The combined native/probe bytes are already present; never apply their
    # patches again. Independently compare all 21 pinned changed source files.
    legacy = json.loads((INPUT/'candidate/sub2api-memory-profile/source-manifest.json').read_text())
    expected = dict(legacy['source_after_sha256'])
    expected.pop('backend/cmd/server/rr_sub2_profile.go')
    if source != expected: raise ValueError('COMBINED_SOURCE_PIN_MISMATCH')
    op = {'hashes': legacy['operator_after_sha256']}
    needed = ['common.mjs','run.mjs','client.mjs','mock.mjs','wire.mjs','plan.mjs','receipts.mjs']
    names = ['sub2api-regression-lab/'+n for n in needed] + [
        'sub2api-spike/broker.mjs','sub2api-spike/util.mjs','sub2api-spike/native-errors.mjs',
        'sub2api-transport-r4/adapter.mjs']
    code = {n:(INPUT/'runtime'/n).read_bytes() if n.endswith('/run.mjs') else actual_code(n,op['hashes'][n]) for n in names}
    run = 'sub2api-regression-lab/run.mjs'
    original = code[run].decode()
    changed = original
    for name in ['setup','load']:
        token = 'async function '+name+'('
        if changed.count(token) != 1: raise ValueError('RUNNER_EXPORT_AMBIGUOUS')
        changed = changed.replace(token,'export '+token)
    replacements = [
        ("state.records.filter(r => r.id === id)", "state.records.filter(r => r.id === id || r.id.startsWith(id + '.r'))"),
        ("const key = await admin(c, '/keys'", "owned.intent = { kind: 'keys', name }; await save(owned.path, owned);\n  const key = await admin(c, '/keys'"),
        ("owned.resources.push({ kind: 'keys', id: key.id }); await save", "owned.resources.push({ kind: 'keys', id: key.id }); owned.intent = null; await save"),
        ("await control(c, 'rule', { id: spec.id, mode: spec.stage === 'memory' ? 'memory' : 'healthy', mib: spec.mib });",
         "row.admitted_request_ids = spec.request_ids ?? [spec.id];\n    for (const id of row.admitted_request_ids) await control(c, 'rule', { id, mode: spec.stage === 'memory' ? 'memory' : 'healthy', mib: spec.mib });"),
        ("Array.from({ length: n }, () => request(c.engine_url, tenant.key, spec.protocol, spec.id,",
         "Array.from({ length: n }, (_, j) => request(c.engine_url, tenant.key, spec.protocol, spec.request_ids?.[results.length+j] ?? spec.id,")
    ]
    replacements.append(("row.downstream = { requests: results.length", "row.request_results = results.map((r,j) => ({id: spec.request_ids?.[j] ?? spec.id, ...r}));\n    row.downstream = { requests: results.length"))
    for before,after in replacements:
        if changed.count(before)!=1: raise ValueError('ROOT_ADAPTER_OVERLAY_AMBIGUOUS')
        changed=changed.replace(before,after)
    code[run] = changed.encode()
    code['sub2api-memory-profile/profile-runner.mjs'] = (OWN/'profile-runner.mjs').read_bytes()
    for n,b in code.items():
        if hashlib.sha256(b).hexdigest()!=op['hashes'][n]: raise ValueError('OPERATOR_AFTER_PIN_MISMATCH: '+n)
    source['backend/cmd/server/rr_sub2_profile.go']=sha(OWN/'overlay/backend/cmd/server/rr_sub2_profile.go')
    if source!=legacy['source_after_sha256']: raise ValueError('SOURCE_AFTER_PIN_MISMATCH')
    if verify_only:
        return {'status':'SOURCE_ONLY','current_input_entries_verified':len(pins),'current_input_manifest_sha256':sha(INPUT/'INPUT-HASHES.json'),
          'source_files_verified':len(source),'operator_files_verified':len(code),'legacy_manifest_sha256':sha(OWN/'source-manifest.json'),
          'collector_after_sha256_required':op['hashes']['sub2api-transport-r4/collector.py'],
          'missing_runtime_inputs':['exact root collector source (before or after burst suffix overlay)','externally reviewed matching Go1.27.1 stdlib/toolchain/cache receipt'],
          'runtime':'NOT RUN','legacy_receipts_promoted':False},None
    collector_path=collector_source or INPUT/'actual-execution/responses/actual-collector.py'
    if not collector_path.is_file(): raise ValueError('MISSING_PINNED_ROOT_COLLECTOR: supply collector_source; legacy bytes required')
    collector_before = collector_path.read_text()
    after_needle='(memory-(responses|messages)-(8|32|64)-(1|5|20)(-b[0-9]{2})?|soak-(responses|messages))'
    if hashlib.sha256(collector_before.encode()).hexdigest()==op['hashes']['sub2api-transport-r4/collector.py']:
        collector_before=collector_before.replace(after_needle,'(memory-(responses|messages)-(8|32|64)-(1|5|20)|soak-(responses|messages))')
    needle = '(memory-(responses|messages)-(8|32|64)-(1|5|20)|soak-(responses|messages))'
    if collector_before.count(needle) != 1: raise ValueError('COLLECTOR_ID_OVERLAY_AMBIGUOUS')
    collector_after = collector_before.replace(needle, '(memory-(responses|messages)-(8|32|64)-(1|5|20)(-b[0-9]{2})?|soak-(responses|messages))')
    code['sub2api-transport-r4/collector.py'] = collector_after.encode()
    code['sub2api-memory-profile/profile-runner.mjs'] = (OWN/'profile-runner.mjs').read_bytes()
    for n,b in code.items():
        if hashlib.sha256(b).hexdigest() != op['hashes'][n]: raise ValueError('OPERATOR_AFTER_PIN_MISMATCH: '+n)
    go = OWN/'overlay/backend/cmd/server/rr_sub2_profile.go'
    source['backend/cmd/server/rr_sub2_profile.go'] = sha(go)
    source=dict(sorted(source.items()))
    parts = list(difflib.unified_diff([],go.read_text().splitlines(True),
                 fromfile='/dev/null',tofile='b/backend/cmd/server/rr_sub2_profile.go'))
    parts += list(difflib.unified_diff(collector_before.splitlines(True), collector_after.splitlines(True),
                  fromfile='a/sub2api-transport-r4/collector.py',tofile='b/sub2api-transport-r4/collector.py'))
    parts += list(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),
                  fromfile='a/'+run,tofile='b/'+run))
    # Keep the W1 default manifest byte-for-byte fixed; current custody is
    # reported separately, never substituted for old execution provenance.
    if source != legacy['source_after_sha256']: raise ValueError('SOURCE_AFTER_PIN_MISMATCH')
    manifest=legacy
    source_bytes=None
    if reviewed:
        from reviewed_source import apply_reviewed
        source_bytes={str(p.relative_to(INPUT/'actual-source')):p.read_bytes() for p in (INPUT/'actual-source').rglob('*') if p.is_file()}
        receipt=apply_reviewed(reviewed,INPUT/'candidate/sub2api-memory-profile/source-manifest.json',source_bytes)
        source_bytes['backend/cmd/server/rr_sub2_profile.go']=go.read_bytes()
        manifest=dict(legacy)
        manifest['reviewed_source']=receipt
        manifest['source_after_sha256']={n:hashlib.sha256(b).hexdigest() for n,b in sorted(source_bytes.items())}
        manifest['source_patch_files']=sorted(set(legacy['source_patch_files'])|{n for p in receipt['patches'] for n in p['files']})
    if stage:
        stage.mkdir(mode=0o700)
        shutil.copytree(INPUT/'actual-source/backend',stage/'backend')
        shutil.copyfile(go,stage/'backend/cmd/server/rr_sub2_profile.go')
        if source_bytes is not None:
            for name,b in source_bytes.items():
                p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        for name,b in code.items():
            p = stage/'code'/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
        if reviewed: (stage/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        else: shutil.copyfile(OWN/'source-manifest.json',stage/'source-manifest.json')
        (stage/'input-verification.json').write_text(json.dumps({'current_input_manifest_sha256':sha(INPUT/'INPUT-HASHES.json'),'entries_verified':len(pins),'legacy_manifest_sha256':sha(OWN/'source-manifest.json')},indent=2)+'\n')
        (stage/'profiling.patch').write_text(''.join(parts))
    return manifest, ''.join(parts)

if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--stage',type=Path); ap.add_argument('--record',action='store_true');ap.add_argument('--collector-source',type=Path);ap.add_argument('--reviewed-source',type=Path);ap.add_argument('--verify-only',action='store_true');ap.add_argument('--out',type=Path)
    a=ap.parse_args(); manifest,patch=generate(a.stage,a.collector_source,a.reviewed_source,a.verify_only)
    if a.verify_only:
        if a.out:a.out.write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps(manifest));raise SystemExit(0)
    if a.record:
        if a.reviewed_source: raise ValueError('LEGACY_MANIFEST_REPLACEMENT_DENIED')
        if (OWN/'profiling.patch').read_text()!=patch: raise ValueError('LEGACY_PATCH_CHANGED')
    print(json.dumps({'verified':len(verify_inputs()),'source_files':len(manifest['source_after_sha256']),'runtime':'NOT RUN'}))
