#!/usr/bin/env python3
"""Controller ONLY: exact-tree offline Go receipts. NOT executed by producer."""
import argparse
import json
import os
import subprocess
from pathlib import Path
import prepare
from patchlib import ledger, sha, tree_sha

OWN = Path(__file__).resolve().parent
CANCEL_NAMES = ['UsageFixture', 'RealTransport', 'WriterFailure', 'Policy',
                'UncertainTransportDoesNotRetry', 'DetachedRealBodyReader', 'HTTPErrorFence', 'AdminPolicyRoundTrip']
GAP_NAMES = ['KeepaliveWriterFailure', 'HTTPBodyUncertainty', 'AnthropicHTTPBodySameAccountRetry', 'HTTPBodyCompactRecovery']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, required=True)
    parser.add_argument('--go', type=Path, required=True)
    parser.add_argument('--gomodcache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--suite', choices=['memory', 'cancel35', 'gaps', 'interaction', 'interaction-red', 'default-drain-red', 'native', 'probe', 'nearest'], required=True)
    parser.add_argument('--race', action='store_true')
    args = parser.parse_args()
    m, hashes = prepare.load_package()
    _, data = prepare.read_backend(args.tree)
    expected = hashes['merged']
    if args.suite in ('interaction-red', 'default-drain-red'):
        control_name = 'interaction-control.json' if args.suite == 'interaction-red' else 'default-drain-control.json'
        control = json.loads((OWN / control_name).read_text())
        fault_patch = (OWN / control['patch']).read_bytes()
        if sha(fault_patch) != control['sha256']:
            raise ValueError('RED fault patch changed')
        expected = dict(expected)
        expected.update({r['path']: r['after_sha256'] for r in control['files']})
    prepare.check_ledger(data, expected, 'controller tree')
    prep = json.loads((args.tree / 'native-merged-preparation.json').read_text())
    if prep['production_patch_sha256'] != m['patches']['production.patch'] or prep['production_only']:
        raise ValueError('preparation binding mismatch or tests absent')
    packages = ['./internal/service']
    required_roots = []
    counts = {'memory': 35, 'cancel35': 35, 'native': 292, 'probe': 63, 'interaction': 1}
    if args.suite == 'memory':
        pattern = '^(TestStreamMemory|TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain$)'
    elif args.suite == 'cancel35':
        required_roots = ['TestNativeAPIKeyCancellation' + n for n in CANCEL_NAMES]
        pattern = '^(' + '|'.join(required_roots) + ')$'
    elif args.suite == 'gaps':
        required_roots = ['TestNativeAPIKeyCancellation' + n for n in GAP_NAMES]
        pattern = '^(' + '|'.join(required_roots) + ')$'
    elif args.suite == 'default-drain-red':
        pattern = '^TestNativeAPIKeyCancellationRealTransport$'
    elif args.suite.startswith('interaction'):
        pattern = '^TestNativeMergedSpilledPrefixWriterFailure$'
    elif args.suite == 'native':
        patterns = json.loads((OWN / 'native-patterns.json').read_text())
        pattern = '^(' + '|'.join(patterns) + ')$'
        packages += ['./internal/handler']
    elif args.suite == 'probe':
        pattern = '^(TestCapabilityProbe|TestDuplicateAccountPreservesTrustedCapabilityProbeDisable|TestProbeOpenAIAPIKeyResponsesSupport|TestSelectResponsesProbeModel|TestDecideResponsesProbeSupport|TestResponsesProbe)'
        packages += ['./internal/handler/admin']
    else:
        pattern = '^(TestOpenAIStreamingPassthrough|TestOpenAIFirstOutput|TestOpenAINativeFirstOutput|TestOpenAISSE|TestStartOpenAISSEKeepalive|TestPassthroughKeepalive|TestGatewayService_AnthropicAPIKeyPassthrough|Test.*NativeAnthropic|Test.*Compact.*|Test.*ClientDisconnect.*|Test.*Concurrency.*|Test.*UpstreamBillingProbe.*)'
        packages += ['./internal/handler', './internal/handler/admin', './internal/repository']
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ('gocache', 'tmp'):
        (args.out / name).mkdir(exist_ok=True)
    label = args.suite + ('-race' if args.race else '-normal')
    log_path = args.out / (label + '.jsonl')
    receipt_path = args.out / (label + '-receipt.json')
    if log_path.exists() or receipt_path.exists():
        raise ValueError('receipt already exists; retain it and choose a fresh output')
    env = os.environ.copy()
    env.update(GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', GONOPROXY='none', GONOSUMDB='none',
               GOMODCACHE=str(args.gomodcache.resolve()), GOCACHE=str((args.out / 'gocache').resolve()),
               GOTMPDIR=str((args.out / 'tmp').resolve()))
    cmd = [str(args.go.resolve()), 'test', '-mod=readonly', '-tags=unit']
    if args.race:
        cmd += ['-race']
    cmd += packages + ['-run', pattern, '-count=1', '-timeout=600s' if args.race else '-timeout=240s', '-json']
    try:
        result = subprocess.run(cmd, cwd=args.tree / 'backend', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as error:
        receipt_path.write_text(json.dumps({'suite': args.suite, 'status': 'NOT RUN', 'reason': str(error),
            'command': cmd, 'backend_tree_sha256': tree_sha(ledger(data)), 'components': m['components']}, indent=2) + '\n')
        raise SystemExit(77)
    log_path.write_text(result.stdout)
    events = []
    for line in result.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    # Package-qualified identities prevent same-named tests in different
    # packages from silently shrinking coverage or masking a failing leaf.
    def names(action):
        return sorted({(e.get('Package', '') + ':' + e['Test']) for e in events if e.get('Action') == action and e.get('Test')})
    passed, failed, skipped = names('pass'), names('fail'), names('skip')
    build_failed = '[build failed]' in result.stdout or any(e.get('Action') == 'build-fail' for e in events)
    unavailable = any(x in result.stdout for x in ('module lookup disabled', 'requires go >=', 'toolchain not available', 'missing go.sum entry', 'cannot find module'))
    status = 'FAIL'
    if unavailable:
        status = 'NOT RUN'
    elif not build_failed and not skipped:
        if args.suite == 'interaction-red':
            wanted = 'TestNativeMergedSpilledPrefixWriterFailure'
            if result.returncode != 0 and len(failed) == 1 and failed[0].endswith(':' + wanted) and 'native forward did not finish within the failure/cancellation oracle: actual held Read after replay loss' in result.stdout:
                status = 'EXPECTED RED'
        elif args.suite == 'default-drain-red':
            wanted = set(control['required_failed_leaves']) | {'TestNativeAPIKeyCancellationRealTransport'}
            observed = {name.split(':', 1)[1] for name in failed}
            if result.returncode != 0 and observed == wanted and 'default final billing drain changed' in result.stdout and 'default completed before held upstream release' in result.stdout:
                status = 'EXPECTED RED'
        elif result.returncode == 0 and passed:
            status = 'PASS'
            if args.suite in counts and len(passed) != counts[args.suite]:
                status = 'FAIL'
            if any(not any(p.endswith(':' + n) for p in passed) for n in required_roots):
                status = 'FAIL'
    after_source, after_data = prepare.read_backend(args.tree)
    prepare.check_ledger(after_data, expected, 'post-test source')
    receipt = {'suite': args.suite, 'race': args.race, 'status': status, 'exit': result.returncode,
               'command': cmd, 'build_failed': build_failed, 'passed_count': len(passed),
               'passed': passed, 'failed': failed, 'skipped': skipped, 'skip_count': len(skipped),
               'backend_tree_sha256': tree_sha(ledger(data)), 'source_tree_unchanged': str(after_source),
               'production_patch_sha256': m['patches']['production.patch'],
               'regression_patch_sha256': m['patches']['regression.patch'], 'components': m['components'],
               'log_sha256': sha(log_path.read_bytes()), 'preparation': prep,
               'expected_count': counts.get(args.suite), 'provider_coverage': 'separate controller gate; not inferred from Go'}
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'suite': args.suite, 'status': status, 'passed': len(passed), 'skipped': len(skipped)}))
    raise SystemExit(77 if status == 'NOT RUN' else 0 if status in ('PASS', 'EXPECTED RED') else 1)


if __name__ == '__main__':
    main()
