#!/usr/bin/env python3
"""Offline artifact/pin/patch verification, not a substitute for actual Go behavior."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

own = Path(__file__).resolve().parent
source = own.parent / '.spike-inputs/actual-source'
def sha(data): return hashlib.sha256(data).hexdigest()

def apply_exact(text, patch):
    lines = text.splitlines(True)
    output = []; cursor = 0
    sections = re.split(r'(?m)^@@ ', patch)[1:]
    for section in sections:
        header, body = section.split('\n', 1)
        match = re.match(r'-(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', header)
        assert match, header
        start = int(match[1]) - (1 if int(match[2] or '1') else 0)
        assert start >= cursor
        output.extend(lines[cursor:start]); cursor = start
        for line in body.splitlines(True):
            if line[:1] in (' ', '-'):
                assert cursor < len(lines) and lines[cursor] == line[1:], (cursor, line)
                cursor += 1
            if line[:1] in (' ', '+'): output.append(line[1:])
    output.extend(lines[cursor:])
    return ''.join(output)

def verify():
    manifest = json.loads((own / 'SOURCE.json').read_text())
    by_path = {r['path']: r for r in manifest['files']}
    checked = 0
    for row in manifest['patches']:
        patch = (own / row['path']).read_text(); assert sha(patch.encode()) == row['sha256']
        sections = re.split(r'(?m)^--- ', patch)[1:]
        for section in sections:
            old, rest = section.split('\n', 1)
            new, hunks = rest.split('\n', 1)
            assert new.startswith('+++ b/')
            path = new[len('+++ b/'):]; file_row = by_path[path]
            before = '' if old == '/dev/null' else (source / path).read_text()
            if before: assert sha(before.encode()) == file_row['before_sha256']
            actual = apply_exact(before, hunks)
            assert actual == (own / file_row['overlay_path']).read_text(), path
            checked += 1
    files = [str(own / row['overlay_path']) for row in manifest['files']]
    formatter = own.parent / '.spike-inputs/gofmt'
    result = subprocess.run([str(formatter), '-l'] + files, capture_output=True, text=True)
    assert result.returncode == 0 and not result.stdout and not result.stderr, result.stdout + result.stderr
    preserved = manifest['preservation_sources']
    for row in preserved:
        assert sha((source / row['path']).read_bytes()) == row['source_sha256']
        if row['lane'] == 'probe' or '/handler/' in row['path'] or row['path'].endswith('_test.go'):
            assert row['path'] not in {r['path'] for r in manifest['files'] if r['kind'] == 'production'}
    assert (own.parent / 'sub2api-fork/checks/coordinator-w5-exact.json').is_file()
    for p in own.glob('*.py'): compile(p.read_text(), str(p), 'exec')
    verdicts = json.loads((own / 'evidence/historical-verdicts.json').read_text())
    assert len(verdicts['receipts']) == 20 and verdicts['functional_PASS'] == 20 and verdicts['empirical_FAIL'] == 20
    return {'status':'PASS', 'kind':'offline packaging and frozen-source verification only',
        'patch_file_applications_verified': checked, 'standalone_gofmt_files': len(files),
        'preservation_input_files':len(preserved), 'actual_Go_execution':'NOT RUN per instruction',
        'Go_compilation':'NOT RUN', 'new_binary_RSS':'NOT RUN'}

if __name__ == '__main__':
    result = verify()
    (own / 'evidence/offline-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
