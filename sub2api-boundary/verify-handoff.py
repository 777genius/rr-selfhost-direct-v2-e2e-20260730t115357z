#!/usr/bin/env python3
"""Offline byte/apply verification; archive provenance remains coordinator-owned."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts):
        digest.update(path.relative_to(root).as_posix().encode() + b'\0' + sha(path).encode() + b'\n')
    return digest.hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate-root', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent)
parser.add_argument('--base-root', type=pathlib.Path)
parser.add_argument('--upstream-root', type=pathlib.Path)
args = parser.parse_args()
root = args.candidate_root.resolve()
report = json.loads((root / 'sub2api-boundary/report.json').read_text())
patch = root / report['patch']['path']
assert sha(patch) == report['patch']['sha256'], 'patch digest mismatch'
for item in report['patch']['files']:
    assert sha(root / item['path']) == item['after_sha256'], item['path']
if args.base_root:
    with tempfile.TemporaryDirectory(prefix='rr-boundary-patch-') as directory:
        staged = pathlib.Path(directory)
        for item in report['patch']['files']:
            source = args.base_root / item['path']
            if item['before_sha256'] is None:
                assert not source.exists(), 'added file exists in base: ' + item['path']
            else:
                assert sha(source) == item['before_sha256'], 'base mismatch: ' + item['path']
                target = staged / item['path']; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        subprocess.run(['patch', '--batch', '-p1', '-i', str(patch)], cwd=staged, check=True, capture_output=True)
        for item in report['patch']['files']:
            assert sha(staged / item['path']) == item['after_sha256'], 'apply mismatch: ' + item['path']
if args.upstream_root:
    pin = json.loads((root / 'sub2api-boundary/source-pin-check.json').read_text())
    assert tree_sha(args.upstream_root) == pin['tree_sha256'], 'fresh upstream archive byte mismatch'
    for name, digest in pin['inspected_files'].items():
        assert sha(args.upstream_root / name) == digest, name
print(json.dumps({'status': 'PASS', 'candidate_files': len(report['patch']['files']),
                  'exact_base_and_patch_apply': bool(args.base_root), 'fresh_upstream_tree_matches': bool(args.upstream_root),
                  'limits': 'Bytes only. Coordinator must independently authenticate the original base and exact revision archive.'}))
