#!/usr/bin/env python3
"""Root/controller-only offline actual-Go verification; never executed by this worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

own = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('--suite', choices=['red', 'green', 'controls', 'native', 'probe', 'handoff'], required=True)
p.add_argument('--tree', type=Path, required=True)
p.add_argument('--go', type=Path, required=True, help='Controller-supplied offline pinned Go executable')
p.add_argument('--gomodcache', type=Path, required=True, help='Existing populated offline dependency cache')
p.add_argument('--out', type=Path, required=True, help='Root-owned receipt directory')
p.add_argument('--race', action='store_true')
a = p.parse_args()
prep = json.loads((a.tree / 'memory-fork-preparation.json').read_text())
if a.suite == 'red':
    assert prep['mode'] == 'red'
    pattern = '^TestStreamMemory(MessagesReadAhead|ResponsesPrefixOverflow|ResponsesPrefixCancellationClosesReader)$'
    packages = ['./internal/service']
elif a.suite == 'controls':
    pattern = '^TestStreamMemory(ResponsesSpilledPrefixPreservesBytesAndFlush|MessagesFullVolumes|MessagesRealUpstreamIdle|ResponsesPrefixKeepaliveDoesNotReplayPrefix|ResponsesSpoolWriterErrorCleanupAndUsage)$'
    packages = ['./internal/service']
elif a.suite == 'handoff':
    pattern = '^TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain$'
    packages = ['./internal/service']
elif a.suite == 'green':
    assert prep['mode'] == 'green'
    pattern = '^(TestStreamMemory|TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain$)'
    packages = ['./internal/service']
elif a.suite == 'native':
    assert prep['mode'] == 'green' and prep['native_controls']
    pattern = '^(' + '|'.join(json.loads((own / 'preservation-patterns.json').read_text())) + ')$'
    packages = ['./internal/service', './internal/handler']
else:
    assert prep['mode'] == 'green'
    pattern = '^(TestCapabilityProbe|TestDuplicateAccountPreservesTrustedCapabilityProbeDisable|TestProbeOpenAIAPIKeyResponsesSupport|TestSelectResponsesProbeModel|TestDecideResponsesProbeSupport|TestResponsesProbe)'
    packages = ['./internal/handler/admin', './internal/service']
a.out.mkdir(parents=True, exist_ok=True)
for name in ('gocache', 'tmp'): (a.out / name).mkdir(exist_ok=True)
env = os.environ.copy()
env.update(GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', GONOPROXY='none', GONOSUMDB='none',
    GOMODCACHE=str(a.gomodcache.resolve()), GOCACHE=str((a.out / 'gocache').resolve()), GOTMPDIR=str((a.out / 'tmp').resolve()))
cmd = [str(a.go.resolve()), 'test', '-mod=readonly', '-tags=unit']
if a.race: cmd.append('-race')
cmd += packages + ['-run', pattern, '-count=1', '-timeout=240s', '-json']
result = subprocess.run(cmd, cwd=a.tree / 'backend', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
log = a.out / (a.suite + '.jsonl'); log.write_text(result.stdout)
events = []
for line in result.stdout.splitlines():
    try: events.append(json.loads(line))
    except ValueError: pass
failed = sorted({e['Test'] for e in events if e.get('Test') and e.get('Action') == 'fail'})
passed = sorted({e['Test'] for e in events if e.get('Test') and e.get('Action') == 'pass'})
skipped = sorted({e['Test'] for e in events if e.get('Test') and e.get('Action') == 'skip'})
build_failure = '[build failed]' in result.stdout or any(e.get('Action') == 'build-fail' for e in events)
missing = any(s in result.stdout for s in ('module lookup disabled', 'requires go >=', 'toolchain not available', 'missing go.sum entry', 'cannot find module'))
status = 'FAIL'
if missing: status = 'NOT RUN'
elif not build_failure and not skipped:
    if a.suite == 'red':
        required = {'TestStreamMemoryMessagesReadAhead/passthrough', 'TestStreamMemoryMessagesReadAhead/native',
            'TestStreamMemoryResponsesPrefixOverflow', 'TestStreamMemoryResponsesPrefixCancellationClosesReader'}
        allowed = required | {'TestStreamMemoryMessagesReadAhead'}
        if result.returncode and required <= set(failed) and set(failed) <= allowed: status = 'EXPECTED RED'
    elif result.returncode == 0 and passed:
        status = 'PASS'
        expected_counts = {'green': 35, 'handoff': 3, 'native': 292, 'probe': 63}
        if a.suite in expected_counts and len(passed) != expected_counts[a.suite]:
            status = 'FAIL'  # Preserve all original 32 cases plus the handoff parent/two cases.
receipt = {'suite': a.suite, 'status': status, 'exit': result.returncode, 'command': cmd,
    'build_failure': build_failure, 'skipped_tests': skipped, 'skip_count': len(skipped), 'failed_tests': failed, 'passed_test_count': len(passed), 'passed_tests': passed,
    'preparation': prep, 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
    'production_patch_sha256': hashlib.sha256((own / 'patches/production.patch').read_bytes()).hexdigest(),
    'native_historical_pass_count': 292 if a.suite == 'native' else None}
(a.out / (a.suite + '-receipt.json')).write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({k: receipt[k] for k in ('suite', 'status', 'build_failure', 'passed_test_count', 'failed_tests')}))
sys.exit(77 if status == 'NOT RUN' else 0 if status in ('PASS', 'EXPECTED RED') else 1)
