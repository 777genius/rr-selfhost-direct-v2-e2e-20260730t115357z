#!/usr/bin/env python3
"""Root/controller-only preparation. No Go, Git, network, or shared-source edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

own = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('--mode', choices=['red', 'green'], required=True)
p.add_argument('--dest', type=Path, required=True, help='New disposable directory, never a shared worker source tree')
p.add_argument('--native-controls', action='store_true', help='Include the unchanged historical independent boundary control')
a = p.parse_args()
manifest = json.loads((own / 'SOURCE.json').read_text())
source = own.parent / manifest['source_path']
sha = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
for row in manifest['files']:
    if row['before_sha256'] is not None:
        assert sha(source / row['path']) == row['before_sha256'], row['path']
    assert sha(own / row['overlay_path']) == row['after_sha256'], row['path']
for row in manifest['patches']:
    assert sha(own / row['path']) == row['sha256'], row['path']
assert not a.dest.exists(), 'Refusing to overwrite an existing directory; choose a fresh disposable path'
a.dest.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, a.dest, ignore=shutil.ignore_patterns('.git'))
for row in manifest['files']:
    if row['kind'] == 'production' and a.mode == 'red':
        continue
    if row['path'].endswith('stream_memory_stage_test.go') and a.mode == 'red':
        continue  # New strict constructor is unavailable in baseline; behavioral RED must compile.
    target = a.dest / row['path']
    if target.exists(): target.chmod(0o644)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(own / row['overlay_path'], target)
if a.native_controls:
    control = own.parent / 'sub2api-fork-review-v2/independent_boundary_test.go.txt'
    assert sha(control) == '3ca97c2d50f0c3c498c51d1fb0af9b7fa5352089953f84d1224e6ea5e03887ce'
    target = a.dest / 'backend/internal/service/independent_boundary_test.go'
    assert not target.exists(), 'Historical boundary control would collide with existing source'
    shutil.copyfile(control, target)
(a.dest / 'memory-fork-preparation.json').write_text(json.dumps({'mode': a.mode,
    'source_manifest_sha256': sha(own / 'SOURCE.json'), 'native_controls': a.native_controls}, indent=2) + '\n')
print(a.dest)
