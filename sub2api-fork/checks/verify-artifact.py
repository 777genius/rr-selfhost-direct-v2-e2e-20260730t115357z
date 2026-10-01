#!/usr/bin/env python3
"""Local immutable-artifact checks; never a substitute for Go behavior."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

owned = Path(__file__).resolve().parents[1]
source = owned.parent / '.spike-inputs/upstream'
editable = owned / 'build-source'
manifest = json.loads((owned / 'SOURCE.json').read_text())
rejected = json.loads((owned / 'checks/r3-rejected-source.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
patch = owned / manifest['patch']['path']
assert sha(patch) == manifest['patch']['sha256']
assert manifest['patch']['changed_lines'] < 1500
assert not any(editable.rglob('.git'))
root = owned / '.build-cache/artifact-verification'
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)
entries = {e['path']: e for e in manifest['files']}
# Verify the full materialized production/test tree difference, not just
# entries already claimed in SOURCE.json. Independent probe files are included.
actual_changed = set()
for path in (editable / 'backend').rglob('*'):
    if path.is_file():
        relative = path.relative_to(editable).as_posix()
        original = source / relative
        if not original.exists() or sha(path) != sha(original):
            actual_changed.add(relative)
for path in (source / 'backend').rglob('*'):
    if path.is_file():
        assert (editable / path.relative_to(source)).is_file(), str(path)
assert actual_changed == set(entries)
for entry in manifest['files']:
    assert sha(editable / entry['path']) == entry['patched_sha256']
    if entry['original_sha256'] is not None:
        assert sha(source / entry['path']) == entry['original_sha256']
        target = root / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / entry['path'], target)

def apply(path, reverse=False):
    cmd = ['patch', '--batch', '--fuzz=0'] + (['-R'] if reverse else []) + ['-p1', '-i', str(path)]
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True)
    assert 'fuzz' not in result.stdout and 'offset' not in result.stdout
    return result.stdout

apply_output = apply(patch)
for entry in manifest['files']:
    assert sha(root / entry['path']) == entry['patched_sha256']
delta = owned / manifest['remediation']['delta_path']
assert sha(delta) == manifest['remediation']['delta_sha256']
apply(delta, reverse=True)
# Reconstruct the exact rejected full patch to bind preservation to 432.
prior_chunks = []
for entry in rejected['files']:
    relative = entry['path']
    assert sha(root / relative) == entry['patched_sha256']
    original = source / relative
    before = original.read_text() if original.exists() else ''
    prior_chunks.append('diff --git a/' + relative + ' b/' + relative + '\n')
    if not original.exists():
        prior_chunks.append('new file mode 100644\n')
    prior_chunks.extend(difflib.unified_diff(before.splitlines(keepends=True), (root / relative).read_text().splitlines(keepends=True),
                       fromfile='a/' + relative if original.exists() else '/dev/null', tofile='b/' + relative))
assert hashlib.sha256(''.join(prior_chunks).encode()).hexdigest() == rejected['patch']['sha256']
assert sha(owned / 'checks/rejected432.patch') == rejected['patch']['sha256']
for relative in set(entries) - {e['path'] for e in rejected['files']}:
    original = source / relative
    if original.exists():
        assert sha(root / relative) == sha(original)
    else:
        assert not (root / relative).exists()
apply(delta)
for entry in manifest['files']:
    assert sha(root / entry['path']) == entry['patched_sha256']
preserved_tests = [e for e in rejected['files'] if e['path'].endswith('_test.go')]
for entry in preserved_tests:
    assert sha(editable / entry['path']) == entry['patched_sha256']
independent = owned.parent / 'sub2api-fork-review-v2/independent_boundary_test.go.txt'
assert sha(independent) == '3ca97c2d50f0c3c498c51d1fb0af9b7fa5352089953f84d1224e6ea5e03887ce'
assert sha(editable / 'backend/internal/service/independent_reference_namespace_test.go') == sha(owned.parent / 'sub2api-candidate-review/independent_reference_namespace_test.go') == '5863f7d72bf5d31865f4a162c614895358fefdc042de9b6128f4d75021e9fa47'
for excluded in ('backend/internal/handler/admin/account_handler.go', 'backend/internal/service/openai_apikey_responses_probe.go'):
    assert excluded not in entries
    assert sha(editable / excluded) == sha(source / excluded)
for entry in json.loads((owned / 'checks/historical-preservation.json').read_text())['files']:
    assert sha(owned / entry['path']) == entry['sha256']
reverse_output = apply(patch, reverse=True)
for entry in manifest['files']:
    if entry['original_sha256'] is None:
        assert not (root / entry['path']).exists()
    else:
        assert sha(root / entry['path']) == entry['original_sha256']
for script in (owned / 'checks').glob('*.py'):
    ast.parse(script.read_text())
result = {'status': 'PASS_ARTIFACT_ONLY', 'patch_sha256': sha(patch),
          'changed_lines': manifest['patch']['changed_lines'], 'file_count': len(entries),
          'production_file_count': sum(e['kind'] == 'production' for e in entries.values()),
          'full_backend_tree_difference': 'PASS: exactly manifest files', 'apply_reverse': 'PASS: zero fuzz/offset with exact hashes',
          'rejected_exact_patch_reconstruction': rejected['patch']['sha256'],
          'previous_authored_test_files_preserved': [e['path'] for e in preserved_tests],
          'previous_287_observed_records': 'Preserved test bytes and focused selection; current execution NOT RUN',
          'independent_test_sha256': sha(independent), 'independent_probe_files': 'PASS: untouched and excluded',
          'historical_preservation': 'PASS', 'python_syntax': 'PASS',
          'go_compilation_behavior_formatting': 'NOT RUN: unavailable locally',
          'independent_reference_namespace_test_sha256': sha(owned.parent / 'sub2api-candidate-review/independent_reference_namespace_test.go'),
          'apply_output': apply_output, 'reverse_output': reverse_output}
(owned / 'checks/artifact-verification.json').write_text(json.dumps(result, indent=2) + '\n')
shutil.rmtree(root)
print(json.dumps(result, indent=2))
