#!/usr/bin/env python3
"""Offline focused checks. Exit 77 means NOT RUN; never install a toolchain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--baseline', action='store_true', help='run the same behavioral tests against untouched staged production code')
args = parser.parse_args()
owned = Path(__file__).resolve().parents[1]
workspace = owned.parent
source = workspace / '.spike-inputs/upstream'
manifest = json.loads((owned / 'SOURCE.json').read_text())
patch = owned / manifest['patch']['path']
sha256 = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
if sha256(patch) != manifest['patch']['sha256']:
    sys.exit('FAIL: patch hash mismatch')
for entry in manifest['files']:
    if entry['original_sha256'] is not None and sha256(source / entry['path']) != entry['original_sha256']:
        sys.exit('FAIL: original file hash mismatch: ' + entry['path'])
    if sha256(owned / 'build-source' / entry['path']) != entry['patched_sha256']:
        sys.exit('FAIL: editable file hash mismatch: ' + entry['path'])

go = shutil.which('go')
if not go:
    print('NOT RUN: Go unavailable; executable behavioral checks prepared.')
    sys.exit(77)
env = os.environ.copy()
cache = owned / '.build-cache'
for name in ('gocache', 'gomodcache', 'tmp'):
    (cache / name).mkdir(parents=True, exist_ok=True)
env.update(GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off',
           GOCACHE=str(cache / 'gocache'), GOTMPDIR=str(cache / 'tmp'))
# Use only already-present dependencies if the coordinator supplies a cache.
if 'GOMODCACHE' not in env:
    env['GOMODCACHE'] = str(cache / 'gomodcache')
root = owned / 'build-source'
if args.baseline:
    root = cache / 'baseline'
    if not root.exists():
        shutil.copytree(source, root, ignore=shutil.ignore_patterns('.git'))
    for entry in manifest['files']:
        target = root / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.chmod(target.stat().st_mode | 0o200)
        origin = source / entry['path'] if entry['original_sha256'] is not None else owned / 'build-source' / entry['path']
        shutil.copyfile(origin, target)
    for entry in manifest['files']:
        if entry['original_sha256'] is not None:
            assert sha256(root / entry['path']) == entry['original_sha256']
pattern = r'^(TestCompatibleReasoningPolicy.*|TestNormalizeOpenAIAPIKeyStoreFalseReasoningReplay.*|TestNormalizeOpenAIResponsesReasoningContentReplay.*|TestNormalizeOpenAIResponsesWebSocketCompatibilityBodyStripsReasoningContentOnlyForOpenAI|TestOpenAIGatewayService_APIKeyPassthrough_StripsInvalidInputItemIDs|TestOpenAIGatewayService_OAuthPassthrough_SanitizesNativeToolItemIDs)$'
command = [go, 'test', '-tags=unit', './internal/service', '-run', pattern, '-count=1', '-timeout=120s', '-v']
print(json.dumps({'mode': 'baseline' if args.baseline else 'patched', 'cwd': str(root / 'backend'), 'command': command}), flush=True)
result = subprocess.run(command, cwd=root / 'backend', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
print(result.stdout, end='')
missing = r'module lookup disabled|requires go >=|toolchain not available|missing go.sum entry|cannot find module'
if result.returncode and re.search(missing, result.stdout):
    print('NOT RUN: local toolchain or cached dependencies unavailable; coordinator must supply them.')
    sys.exit(77)
if args.baseline:
    if result.returncode and '--- FAIL: TestCompatibleReasoningPolicy' in result.stdout and '[build failed]' not in result.stdout:
        print('EXPECTED RED: untouched production code fails opt-in replay assertions.')
        sys.exit(0)
    sys.exit('FAIL: baseline did not produce an observed behavioral regression')
if result.returncode:
    sys.exit(result.returncode)
formatter = shutil.which('gofmt')
if not formatter:
    print('NOT RUN: behavioral tests passed, but gofmt unavailable.')
    sys.exit(77)
formatted = subprocess.run([formatter, '-l'] + [str(root / entry['path']) for entry in manifest['files']], capture_output=True, text=True)
if formatted.returncode or formatted.stdout.strip():
    print(formatted.stdout + formatted.stderr)
    sys.exit('FAIL: patch files require gofmt')
print('PASS: targeted behavioral tests and formatting')
