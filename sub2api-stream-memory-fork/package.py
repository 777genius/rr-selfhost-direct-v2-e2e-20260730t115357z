#!/usr/bin/env python3
"""Freeze incremental patches against the supplied actual combined native/probe source."""
from pathlib import Path
import difflib
import hashlib
import json

OWN = Path(__file__).resolve().parent
INPUT = OWN.parent / '.spike-inputs'
SOURCE = INPUT / 'actual-source'
def sha(data): return hashlib.sha256(data).hexdigest()
def emit(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
def make_patch(paths, base):
    chunks = []
    for path in sorted(paths):
        rel = path.relative_to(base).as_posix()
        before = (SOURCE / rel).read_text() if base.name == 'production' else ''
        chunks.extend(difflib.unified_diff(before.splitlines(True), path.read_text().splitlines(True),
                                         fromfile='a/' + rel if before else '/dev/null', tofile='b/' + rel))
    return ''.join(chunks)

def main():
    original_manifest = INPUT / 'INPUT-HASHES.json'
    supplied = json.loads(original_manifest.read_text())
    mismatches = [p for p, h in supplied.items() if not (INPUT / p).is_file() or sha((INPUT / p).read_bytes()) != h]
    assert not mismatches, mismatches
    emit(OWN / 'evidence/input-verification.json', {'manifest_sha256': sha(original_manifest.read_bytes()),
        'entries': len(supplied), 'mismatches': mismatches})
    prod = sorted((OWN / 'production').rglob('*.go'))
    tests = sorted((OWN / 'tests').rglob('*.go'))
    patches = {
        'production.patch': (prod, OWN / 'production'),
        'responses-prefix.production.patch': ([p for p in prod if p.name in {'openai_gateway_passthrough.go', 'openai_first_output_timeout.go'}], OWN / 'production'),
        'messages-read-ahead.production.patch': ([p for p in prod if p.name in {'gateway_anthropic_passthrough.go', 'openai_gateway_messages_anthropic_native.go'}], OWN / 'production'),
        'tests-behavior.patch': ([p for p in tests if p.name != 'stream_memory_stage_test.go'], OWN / 'tests'),
        'tests-stage.patch': ([p for p in tests if p.name == 'stream_memory_stage_test.go'], OWN / 'tests'),
    }
    patch_rows = []
    for name, (files, base) in patches.items():
        data = make_patch(files, base)
        (OWN / 'patches' / name).write_text(data)
        added = sum(line.startswith('+') and not line.startswith('+++') for line in data.splitlines())
        removed = sum(line.startswith('-') and not line.startswith('---') for line in data.splitlines())
        patch_rows.append({'path': 'patches/' + name, 'sha256': sha(data.encode()), 'added_lines': added, 'removed_lines': removed})
    rows = []
    for p in prod + tests:
        base = OWN / ('production' if p in prod else 'tests')
        rel = p.relative_to(base).as_posix()
        before = (SOURCE / rel).read_bytes() if p in prod else b''
        hunks = []
        if p in prod:
            a, b = before.decode().splitlines(True), p.read_text().splitlines(True)
            for group in difflib.SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(3):
                old_start, old_end = group[0][1], group[-1][2]
                new_start, new_end = group[0][3], group[-1][4]
                hunks.append({'before_lines': [old_start + 1, old_end], 'after_lines': [new_start + 1, new_end],
                    'before_sha256': sha(''.join(a[old_start:old_end]).encode()),
                    'after_sha256': sha(''.join(b[new_start:new_end]).encode())})
        rows.append({'path': rel, 'overlay_path': p.relative_to(OWN).as_posix(), 'kind': base.name,
            'before_sha256': sha(before) if p in prod else None, 'after_sha256': sha(p.read_bytes()), 'hunks': hunks})
    native = json.loads((OWN.parent / 'sub2api-fork/SOURCE.json').read_text())
    probe = json.loads((OWN.parent / 'sub2api-probe-fork/SOURCE.json').read_text())
    controls = []
    for row in native['files']:
        actual = sha((SOURCE / row['path']).read_bytes())
        assert actual == row['patched_sha256'], row['path']
        controls.append({'path': row['path'], 'source_sha256': actual, 'lane': 'native',
                         'production_overlap': row['path'] in {r['path'] for r in rows if r['kind'] == 'production'}})
    for name, row in probe['files'].items():
        actual = sha((SOURCE / name).read_bytes()); assert actual == row['patched_sha256'], name
        controls.append({'path': name, 'source_sha256': actual, 'lane': 'probe', 'production_overlap': False})
    emit(OWN / 'SOURCE.json', {'schema': 1, 'source_path': '.spike-inputs/actual-source',
         'source_kind': 'frozen actual combined native + disabled-probe engine source, not official unpatched upstream',
         'supplied_manifest_sha256': sha(original_manifest.read_bytes()),
         'files': rows, 'patches': patch_rows, 'preservation_sources': controls,
         'integration': 'Incremental four-file production delta. Do not reapply native/probe patches. Check before hashes; merge overlapping cancellation edits at hunk level, never overwrite root files with overlays.'})
    # W2 is also independently applicable to the exact copied W1 package.
    candidate = INPUT / 'candidate' / OWN.name
    delta_rows = []
    for kind, paths, name in (
        ('production', [p for p in prod if p.name == 'openai_gateway_passthrough.go'], 'w2-prefix-ownership.production.patch'),
        ('tests', [p for p in tests if p.name == 'stream_memory_replay_handoff_test.go'], 'w2-prefix-ownership.tests.patch'),
    ):
        chunks = []
        for path in paths:
            rel = path.relative_to(OWN / kind).as_posix()
            old = candidate / kind / rel
            before = old.read_text() if old.exists() else ''
            chunks.extend(difflib.unified_diff(before.splitlines(True), path.read_text().splitlines(True),
                fromfile='a/' + rel if before else '/dev/null', tofile='b/' + rel))
            delta_rows.append({'path': rel, 'kind': kind, 'overlay_path': path.relative_to(OWN).as_posix(),
                'before_sha256': sha(before.encode()) if before else None, 'after_sha256': sha(path.read_bytes()),
                'patch': 'patches/' + name})
        (OWN / 'patches' / name).write_text(''.join(chunks))
    emit(OWN / 'W2-DELTA.json', {'base': '.spike-inputs/candidate/sub2api-stream-memory-fork',
        'base_production_patch_sha256': sha((candidate / 'patches/production.patch').read_bytes()),
        'files': delta_rows, 'patches': {r['patch']: sha((OWN / r['patch']).read_bytes()) for r in delta_rows},
        'integration': 'Apply the full production/tests patches to exact frozen combined source, OR apply W2 delta patches to exact W1; never both. Merge changed shared source at hunk level.'})
    receipts = []
    for protocol in ('responses', 'messages'):
        execution = json.loads((INPUT / 'worker-frozen-inputs' / 'actual-execution' / protocol / 'execution.json').read_text())
        for row in execution['results']:
            receipts.append({'protocol': protocol, 'id': row['id'], 'functional_status': row['functional_status'],
                'empirical_status': row['empirical_status'], 'physical_interval_status': row['physical_interval_status']})
    emit(OWN / 'evidence/historical-verdicts.json', {'receipts': receipts,
        'functional_PASS': sum(r['functional_status'] == 'PASS' for r in receipts),
        'empirical_FAIL': sum(r['empirical_status'] == 'FAIL' for r in receipts),
        'profile_binary': json.loads((INPUT / 'worker-frozen-inputs/actual-execution/responses/source-manifest.json').read_text()),
        'new_patch_runtime_result': 'NOT RUN; old receipts cannot validate a new binary'})
    print(f'Pinned {len(supplied)} inputs; froze {len(prod)} production files and {len(tests)} actual-package tests.')

if __name__ == '__main__': main()
