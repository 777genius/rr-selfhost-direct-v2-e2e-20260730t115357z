#!/usr/bin/env python3
"""Freeze the full owned replacement and remediation delta against official 96f4."""
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

owned = Path(__file__).resolve().parents[1]
source = owned.parent / '.spike-inputs/upstream'
editable = owned / 'build-source'
rejected = json.loads((owned / 'checks/r3-rejected-source.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert rejected['patch']['sha256'] == '432cffdf3b2a2659da76403242942b45177d69f60fda17efd14605d7798e7135'
for entry in rejected['files']:
    if entry['original_sha256'] is not None:
        assert sha(source / entry['path']) == entry['original_sha256']
prior_root = owned / '.build-cache/r3-rejected-files'
if not prior_root.exists():
    prior_root.mkdir(parents=True)
    for entry in rejected['files']:
        if entry['original_sha256'] is not None:
            target = prior_root / entry['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / entry['path'], target)
    frozen = owned / 'checks/rejected432.patch'
    assert sha(frozen) == rejected['patch']['sha256']
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(frozen)], cwd=prior_root, check=True, capture_output=True)
for entry in rejected['files']:
    assert sha(prior_root / entry['path']) == entry['patched_sha256']
entries, chunks, repair_chunks = [], [], []
added = removed = repair_added = repair_removed = 0

def diff(relative, before, after, exists):
    delta = list(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                 fromfile='a/' + relative if exists else '/dev/null', tofile='b/' + relative))
    header = 'diff --git a/' + relative + ' b/' + relative + '\n'
    if not exists:
        header += 'new file mode 100644\n'
    return header + ''.join(delta), sum(s.startswith('+') and not s.startswith('+++') for s in delta), sum(s.startswith('-') and not s.startswith('---') for s in delta)

for path in sorted((editable / 'backend/internal').rglob('*.go')):
    relative = path.relative_to(editable).as_posix()
    original = source / relative
    before = original.read_text() if original.exists() else ''
    after = path.read_text()
    if before == after:
        continue
    entries.append({'path': relative, 'kind': 'test' if path.name.endswith('_test.go') else 'production',
                    'original_sha256': sha(original) if original.exists() else None, 'patched_sha256': sha(path)})
    chunk, plus, minus = diff(relative, before, after, original.exists())
    chunks.append(chunk); added += plus; removed += minus
    prior = owned / '.build-cache/r3-rejected-files' / relative
    prior_exists = prior.exists() or original.exists()
    prior_text = prior.read_text() if prior.exists() else before
    if prior_text != after:
        chunk, plus, minus = diff(relative, prior_text, after, prior_exists)
        repair_chunks.append(chunk); repair_added += plus; repair_removed += minus
assert added + removed < 1500, 'Bounded replacement exceeded 1500 changed lines'
patch = owned / 'patches/native-reasoning.patch'
patch.write_text(''.join(chunks))
delta = owned / 'checks/r3-repair.patch'
delta.write_text(''.join(repair_chunks))
manifest = json.loads((owned / 'SOURCE.json').read_text())
manifest['patch'] = {'path': 'patches/native-reasoning.patch', 'sha256': sha(patch), 'strip': 1,
                     'added_lines': added, 'removed_lines': removed, 'changed_lines': added + removed}
manifest['files'] = entries
manifest['supersedes'] = {'patch_sha256': rejected['patch']['sha256'],
    'repo_output_sha256_user_supplied': '28a380dc1c346d34a0a9cc145efcb628560b4b8112654faebc1182929d0f7350',
    'peer_decision': 'REQUEST_CHANGES_R3', 'review': '../sub2api-candidate-review/REPORT.md',
    'old_validation_applies_to_replacement': False}
formatter = shutil.which('gofmt')
format_status = 'NOT RUN: gofmt unavailable locally'
if formatter:
    formatted = subprocess.run([formatter, '-l'] + [str(editable / e['path']) for e in entries], capture_output=True, text=True)
    format_status = 'PASS' if formatted.returncode == 0 and not formatted.stdout.strip() else 'REQUIRED: run focused runner --format'
manifest['remediation'] = {'delta_path': 'checks/r3-repair.patch', 'delta_sha256': sha(delta),
                          'added_lines': repair_added, 'removed_lines': repair_removed,
                          'rejected_manifest': 'checks/r3-rejected-source.json',
                          'local_go_compilation_behavior': 'NOT RUN: coordinator-owned offline gate', 'authored_go_formatting': format_status}
(owned / 'SOURCE.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'patch': manifest['patch'], 'remediation': manifest['remediation']}))
