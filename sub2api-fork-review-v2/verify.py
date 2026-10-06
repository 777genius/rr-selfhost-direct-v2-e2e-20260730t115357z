#!/usr/bin/env python3
"""Independent offline artifact verification; does not execute producer scripts."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

owned = Path(__file__).resolve().parent
inputs = owned.parent / '.spike-inputs'
candidate = inputs / 'candidate'
manifest = json.loads((candidate / 'SOURCE.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
patch = candidate / 'patches/native-reasoning.patch'
expected_patch = '7dec93ec55da38f15e719f5b7b7769ad2ec874ae548e1125a8a028e12cc51bdf'
assert sha(patch) == expected_patch == manifest['patch']['sha256']
assert manifest['upstream']['revision'] == '96f4c115c9749078f90cbf210a01d39baf3f53b6'
rows = []
for entry in manifest['files']:
    rel = entry['path']
    original = inputs / 'upstream' / rel
    replacement = inputs / 'patched' / rel
    assert (sha(original) if original.exists() else None) == entry['original_sha256'], rel
    assert sha(replacement) == entry['patched_sha256'], rel
    rows.append(dict(entry))

def tree(root):
    return {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.is_file()}

before, after = tree(inputs / 'upstream'), tree(inputs / 'patched')
differences = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
assert differences == sorted(e['path'] for e in manifest['files']), differences
lines = patch.read_text().splitlines()
added = sum(x.startswith('+') and not x.startswith('+++') for x in lines)
removed = sum(x.startswith('-') and not x.startswith('---') for x in lines)
assert (added, removed) == (818, 42)
transcripts = {}
with tempfile.TemporaryDirectory(prefix='exact-patch-', dir=owned) as temp:
    work = Path(temp)
    for entry in rows:
        if entry['original_sha256'] is not None:
            dest = work / entry['path']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inputs / 'upstream' / entry['path'], dest)
    for mode, extra in [('apply', []), ('reverse', ['-R'])]:
        result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', *extra, '-i', str(patch)], cwd=work, capture_output=True, text=True)
        transcripts[mode] = result.stdout + result.stderr
        assert result.returncode == 0, transcripts[mode]
        assert 'offset' not in transcripts[mode].lower() and 'fuzz' not in transcripts[mode].lower()
        for entry in rows:
            target = work / entry['path']
            expected = entry['patched_sha256'] if mode == 'apply' else entry['original_sha256']
            assert (sha(target) if target.exists() else None) == expected, entry['path']
receipt_path = inputs / 'coordinator-red-green.json'
receipt = json.loads(receipt_path.read_text())
assert receipt['patch_sha256'] == expected_patch and receipt['source_pin_hashes_match']
baseline, patched = receipt['cases']
assert baseline['mode'] == 'baseline' and baseline['exit'] == 1 and not baseline['compile_failed']
assert len(baseline['actual_failed_tests']) == 33
assert patched['mode'] == 'patched' and patched['exit'] == 0 and not patched['compile_failed']
assert patched['passed_test_count'] == 116 and not patched['actual_failed_tests']
result = {
    'status': 'PASS', 'patch_sha256': sha(patch), 'source_manifest_sha256': sha(candidate / 'SOURCE.json'),
    'source_revision': manifest['upstream']['revision'], 'files': rows,
    'tree_files_upstream': len(before), 'tree_files_patched': len(after), 'only_tree_differences': differences,
    'added_lines': added, 'removed_lines': removed, 'changed_lines': added + removed,
    'zero_fuzz_zero_offset_apply_and_reverse': transcripts,
    'coordinator_receipt_sha256': sha(receipt_path), 'coordinator_receipt': receipt,
    'behavior_execution': 'Coordinator supplied; reviewer did not execute Go tests',
    'local_go_available': shutil.which('go') is not None,
    'local_gofmt_available': shutil.which('gofmt') is not None,
}
(owned / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ['status', 'patch_sha256', 'changed_lines', 'tree_files_upstream', 'tree_files_patched', 'local_go_available', 'local_gofmt_available']}))
