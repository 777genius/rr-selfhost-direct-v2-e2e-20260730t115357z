#!/usr/bin/env python3
"""Actual offline Go packages in a disposable copy; unavailable gates exit 77."""
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
mode = parser.add_mutually_exclusive_group()
mode.add_argument('--baseline', action='store_true')
mode.add_argument('--rejected', action='store_true', help='exact rejected 7dec with current boundary tests')
mode.add_argument('--r3-rejected', action='store_true', help='exact captured 432 with current reference namespace regression')
mode.add_argument('--format', action='store_true', help='gofmt all authored Go, then refreeze and verify')
args = parser.parse_args()
owned = Path(__file__).resolve().parents[1]
source = owned.parent / '.spike-inputs/upstream'
manifest = json.loads((owned / 'SOURCE.json').read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
patch = owned / manifest['patch']['path']
assert sha(patch) == manifest['patch']['sha256']
for entry in manifest['files']:
    if entry['original_sha256'] is not None:
        assert sha(source / entry['path']) == entry['original_sha256']
    assert sha(owned / 'build-source' / entry['path']) == entry['patched_sha256']
independent = owned.parent / 'sub2api-fork-review-v2/independent_boundary_test.go.txt'
assert sha(independent) == '3ca97c2d50f0c3c498c51d1fb0af9b7fa5352089953f84d1224e6ea5e03887ce'
reference = owned.parent / 'sub2api-candidate-review/independent_reference_namespace_test.go'
assert sha(reference) == '5863f7d72bf5d31865f4a162c614895358fefdc042de9b6128f4d75021e9fa47'
assert sha(owned / 'build-source/backend/internal/service/independent_reference_namespace_test.go') == sha(reference)
r3_frozen = owned / 'checks/rejected432.patch'
assert sha(r3_frozen) == '432cffdf3b2a2659da76403242942b45177d69f60fda17efd14605d7798e7135'
frozen = owned / 'checks/rejected7dec.patch'
assert sha(frozen) == '7dec93ec55da38f15e719f5b7b7769ad2ec874ae548e1125a8a028e12cc51bdf'
run_mode = 'format' if args.format else 'baseline' if args.baseline else 'rejected' if args.rejected else 'r3-rejected' if args.r3_rejected else 'patched'
receipt = {'mode': run_mode, 'patch_sha256': sha(patch), 'source_revision': manifest['upstream']['revision'],
           'independent_test_sha256': sha(independent), 'independent_reference_test_sha256': sha(reference), 'status': 'NOT RUN', 'network': 'disabled by offline Go configuration; coordinator owns OS containment'}

def finish(code, status, reason):
    receipt.update(status=status, reason=reason, exit_code=code)
    (owned / 'checks' / (run_mode + '-execution.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(status + ': ' + reason)
    sys.exit(code)

formatter = shutil.which('gofmt')
if args.format:
    if not formatter:
        finish(77, 'NOT RUN', 'gofmt unavailable; no installation/network attempted')
    files = [owned / 'build-source' / entry['path'] for entry in manifest['files']]
    for file in files:
        file.chmod(0o644)
    subprocess.run([formatter, '-w'] + list(map(str, files)), check=True)
    for script in ('freeze-artifact.py', 'verify-artifact.py'):
        subprocess.run([sys.executable, str(owned / 'checks' / script)], check=True)
    receipt['formatted_replacement_patch_sha256'] = sha(patch)
    finish(0, 'PASS', 'All authored Go formatted; full replacement refrozen and independently verified')

go = shutil.which('go')
if not go:
    finish(77, 'NOT RUN', 'Go unavailable; actual-package compilation/behavior requires coordinator offline toolchain')
cache = owned / '.build-cache'
for name in ('gocache', 'gomodcache', 'tmp'):
    (cache / name).mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env.update(GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', GONOPROXY='none', GONOSUMDB='none',
           GOCACHE=str(cache / 'gocache'), GOTMPDIR=str(cache / 'tmp'))
if 'GOMODCACHE' not in env:
    env['GOMODCACHE'] = str(cache / 'gomodcache')
root = cache / (run_mode + '-actual-go')
if root.exists():
    shutil.rmtree(root)
shutil.copytree(source, root, ignore=shutil.ignore_patterns('.git'))
selected_patch = r3_frozen if args.r3_rejected else frozen if args.rejected else patch
if not args.baseline:
    applied = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(selected_patch)], cwd=root, capture_output=True, text=True, check=True)
    assert 'fuzz' not in applied.stdout and 'offset' not in applied.stdout
# No extracts or replacement implementations: these compile against actual Go.
for entry in manifest['files']:
    if entry['kind'] == 'test':
        target = root / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.chmod(0o644)
        shutil.copyfile(owned / 'build-source' / entry['path'], target)
shutil.copyfile(independent, root / 'backend/internal/service/independent_boundary_test.go')
patterns = json.loads((owned / 'checks/r1-r2-preserved-patterns.json').read_text())
patterns += ['TestIndependentCompatibleReferenceNamespaceHTTP', 'TestCompatibleReasoningRepair.*', 'TestIndependentCompatibleReasoning.*',
             'TestNormalizeOpenAIResponsesRejectedFieldRetryBody.*', 'TestOpenAIResponsesRejectedFieldRetryState.*',
             'TestOpenAIGatewayService_.*Rejected.*', 'TestOpenAIGatewayService_APIKeyRetries.*',
             'TestOpenAIGatewayService_OAuthRetriesExactRejectedStatus',
             'TestProxyOpenAIWSHTTPBridgeTurnRetriesRejectedFieldBeforeClientOutput',
             'TestSanitizeEmptyBase64InputImages.*', 'TestSanitizeOpenAIResponsesToolParameterTypes.*']
command = [go, 'test', '-tags=unit', './internal/service', './internal/handler', '-run', '^(' + '|'.join(patterns) + ')$',
           '-count=1', '-timeout=240s', '-json']
receipt['command'] = command
receipt['tested_patch_sha256'] = None if args.baseline else sha(selected_patch)
result = subprocess.run(command, cwd=root / 'backend', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
log = owned / 'checks' / (run_mode + '-go-test.jsonl')
log.write_text(result.stdout)
receipt.update(raw_log=str(log.relative_to(owned)), raw_log_sha256=sha(log), go_test_exit=result.returncode)
if result.returncode and re.search(r'module lookup disabled|requires go >=|toolchain not available|missing go.sum entry|cannot find module', result.stdout):
    finish(77, 'NOT RUN', 'Offline toolchain or dependencies unavailable; no behavioral result claimed')
events = []
for line in result.stdout.splitlines():
    try:
        events.append(json.loads(line))
    except ValueError:
        pass
failed = {e.get('Test') for e in events if e.get('Action') == 'fail' and e.get('Test')}
passed = {e.get('Test') for e in events if e.get('Action') == 'pass' and e.get('Test')}
receipt.update(failed_tests=sorted(failed), passed_tests=sorted(passed))
if '[build failed]' in result.stdout or 'build-fail' in result.stdout:
    finish(1, 'FAIL', 'Actual Go compilation failed; compile failure is never behavioral red')
if args.r3_rejected:
    required = [f'TestIndependentCompatibleReferenceNamespaceHTTP/pass_{mode}/opt_true' for mode in ('false', 'true')]
    controls = [f'TestIndependentCompatibleReferenceNamespaceHTTP/pass_{mode}/opt_false' for mode in ('false', 'true')]
    receipt['required_red'] = {name: name in failed for name in required}
    receipt['default_controls'] = {name: name in passed for name in controls}
    receipt['unexpected_failed_tests'] = sorted(failed - set(required) - {'TestIndependentCompatibleReferenceNamespaceHTTP'})
    if result.returncode and all(receipt['required_red'].values()) and all(receipt['default_controls'].values()) and not receipt['unexpected_failed_tests']:
        finish(0, 'EXPECTED RED', 'Exact captured 432 loses opted-in reference namespaces; both default controls pass')
    finish(1, 'FAIL', 'R3 behavioral reds or default controls were not observed')
if args.rejected or args.baseline:
    required = ['TestIndependentCompatibleReasoningRejectedContent/false',
                'TestIndependentCompatibleReasoningRejectedContent/true',
                'TestIndependentCompatibleReasoningEmptyImagePrecision/true']
    if args.rejected:
        required += [f'TestCompatibleReasoningRepairRejectedFields/{mode}/{field}/opt_true'
                     for mode in ('http', 'passthrough', 'bridge', 'native') for field in ('content', 'null', 'status', 'cache', 'reference_status')]
    controls = [f'TestCompatibleReasoningRepairRejectedFields/{mode}/{field}/opt_{opt}'
                for mode in ('http', 'passthrough', 'bridge', 'native')
                for field, opt in (('null', 'false'), ('status', 'false'), ('cache', 'false'), ('reference_status', 'false'), ('user_status', 'true'), ('user_status', 'false'), ('user_null', 'true'), ('user_null', 'false'), ('truncation', 'true'), ('truncation', 'false'))]
    # On official baseline there is no opt-in policy, so positive preservation
    # controls necessarily fail; only legacy default controls can be green.
    if args.baseline:
        required = ['TestIndependentCompatibleReasoningRejectedContent/false', 'TestIndependentCompatibleReasoningRejectedContent/true']
        controls = [c for c in controls if c.endswith('opt_false')]
    receipt['required_red'] = {name: name in failed for name in required}
    receipt['default_and_ordinary_controls'] = {name: name in passed for name in controls}
    if result.returncode and all(receipt['required_red'].values()) and all(receipt['default_and_ordinary_controls'].values()):
        finish(0, 'EXPECTED RED', 'Observed real-boundary regressions with ordinary/default controls green')
    finish(1, 'FAIL', 'Specified behavioral reds or passing controls were not observed')
if result.returncode:
    finish(result.returncode, 'FAIL', 'Actual Go behavioral suite failed; see scoped raw log')
if not passed or not all(name in passed for name in ('TestIndependentCompatibleReferenceNamespaceHTTP', 'TestCompatibleReasoningRepairRejectedFields', 'TestIndependentCompatibleReasoningRejectedContent', 'TestIndependentCompatibleReasoningEmptyImagePrecision')):
    finish(1, 'FAIL', 'Go output did not prove execution of required oracles')
reference_cases = [f'TestIndependentCompatibleReferenceNamespaceHTTP/pass_{mode}/opt_{opt}' for mode in ('false', 'true') for opt in ('false', 'true')]
if not all(name in passed for name in reference_cases):
    finish(1, 'FAIL', 'Go output did not prove all four reference policy/HTTP controls ran')
if not formatter:
    finish(77, 'NOT RUN', 'Behavior passed, but gofmt unavailable')
formatted = subprocess.run([formatter, '-l'] + [str(root / e['path']) for e in manifest['files']], capture_output=True, text=True)
receipt['gofmt_output'] = formatted.stdout + formatted.stderr
if formatted.returncode or formatted.stdout.strip():
    finish(1, 'FAIL', 'Authored Go requires gofmt; run --format then rerun exact replacement')
finish(0, 'PASS', 'Actual Go compilation and focused original/new/independent/default oracles plus gofmt')
