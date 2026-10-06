#!/usr/bin/env python3
"""Independent offline byte reconstruction and actual Go JSONL review. No Go/Git/network."""
import collections
import hashlib
import json
import pathlib
import re

OWN = pathlib.Path(__file__).resolve().parent
INPUT = OWN.parent / '.spike-inputs'
CANDIDATE = INPUT / 'candidate/sub2api-native-merged'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def tree(hashes):
    return sha(''.join(k + '\0' + v + '\n' for k, v in sorted(hashes.items())).encode())


def patch(source, content, reverse=False):
    """Independent exact-context parser; reject offset/fuzz and malformed counts."""
    result = dict(source)
    lines = content.decode().splitlines(keepends=True)
    i = 0
    while i < len(lines):
        while i < len(lines) and lines[i].startswith(('diff --git ', 'index ', 'new file mode ')):
            i += 1
        assert lines[i].startswith('--- ')
        old = lines[i][4:].strip()
        assert lines[i+1].startswith('+++ b/backend/')
        name = lines[i+1][6:].strip()
        assert '..' not in pathlib.PurePosixPath(name).parts
        new_file = old == '/dev/null'
        assert new_file or old == 'a/' + name
        before = [] if new_file and not reverse else source[name].decode().splitlines(keepends=True)
        if new_file and not reverse:
            assert name not in source
        after = []
        cursor = 0
        i += 2
        while i < len(lines) and not lines[i].startswith(('--- ', 'diff --git ')):
            m = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[i])
            assert m, lines[i]
            a, n, b, q = [int(x) if x is not None else 1 for x in m.groups()]
            if reverse:
                a, n, b, q = b, q, a, n
            pos = a - bool(n)
            assert cursor <= pos <= len(before)
            after.extend(before[cursor:pos])
            cursor = pos
            assert len(after) == b - bool(q)
            seen_old = seen_new = 0
            i += 1
            while i < len(lines) and not lines[i].startswith(('@@ ', '--- ', 'diff --git ')):
                sign, value = lines[i][0], lines[i][1:]
                assert sign in ' +-'
                if reverse:
                    sign = {'+': '-', '-': '+'}.get(sign, sign)
                if sign in ' -':
                    assert cursor < len(before) and before[cursor] == value, name
                    cursor += 1
                    seen_old += 1
                if sign in ' +':
                    after.append(value)
                    seen_new += 1
                i += 1
            assert (seen_old, seen_new) == (n, q)
        after.extend(before[cursor:])
        value = ''.join(after).encode()
        if new_file and reverse:
            assert not value
            del result[name]
        else:
            result[name] = value
    return result


def ledger_for(data, initial):
    # data includes all files touched by production/regression/canonical patches.
    hashes = dict(initial)
    for name in touched:
        hashes.pop(name, None)
    hashes.update({name: sha(value) for name, value in data.items()})
    return hashes


pins = read_json(INPUT / 'INPUT-HASHES.json')
for name, digest in pins.items():
    path = INPUT / name
    assert path.is_file() and not path.is_symlink(), name
    assert sha(path.read_bytes()) == digest, name

manifest = read_json(CANDIDATE / 'manifest.json')
assert manifest['patches']['production.patch'] == '16bc1644e564847f0565dffd765af6c7e0c7a70ac5677147d3166e20c90923a5'
assert manifest['patches']['regression.patch'] == 'f6909228e016be8817057f2f3c5bd5f460550d9139dff19810c8df59d22d466d'
for name, digest in manifest['patches'].items():
    assert sha((CANDIDATE / name).read_bytes()) == digest

executed = read_json(INPUT / 'actual-gates/executed-source-hashes.json')
frozen = read_json(CANDIDATE / 'merged-hashes.json')
assert len(executed) == len(frozen) == 3332
assert {'backend/' + k: v for k, v in executed.items()} == frozen
backend = INPUT / 'executed-source/backend'
actual_paths = {p.relative_to(backend).as_posix() for p in backend.rglob('*') if p.is_file()}
assert actual_paths == set(executed)
for name, digest in executed.items():
    assert sha((backend / name).read_bytes()) == digest, name
assert tree(frozen) == manifest['merged_tree_sha256'] == '82662b8666b05b6a0a95c76c79bde630ba73a27e2ae89e72363908a1f2117c42'

patch_names = ['production.patch', 'regression.patch', 'canonical-native.patch', 'canonical-probe.patch']
touched = set()
for name in patch_names:
    touched.update(re.findall(r'^\+\+\+ b/(backend/[^\n]+)$', (CANDIDATE / name).read_text(), re.M))
final = {name: (INPUT / 'executed-source' / name).read_bytes() for name in touched}
base = patch(patch(final, (CANDIDATE / 'regression.patch').read_bytes(), True), (CANDIDATE / 'production.patch').read_bytes(), True)
assert ledger_for(base, frozen) == read_json(CANDIDATE / 'base-hashes.json')
rebuilt = patch(patch(base, (CANDIDATE / 'production.patch').read_bytes()), (CANDIDATE / 'regression.patch').read_bytes())
assert rebuilt == final
official = patch(patch(base, (CANDIDATE / 'canonical-probe.patch').read_bytes(), True), (CANDIDATE / 'canonical-native.patch').read_bytes(), True)
assert ledger_for(official, frozen) == read_json(CANDIDATE / 'official-hashes.json')
assert patch(patch(official, (CANDIDATE / 'canonical-native.patch').read_bytes()), (CANDIDATE / 'canonical-probe.patch').read_bytes()) == base
for kind, data in [('base', base), ('official', official)]:
    assert tree(ledger_for(data, frozen)) == manifest[kind + '_tree_sha256']

w2 = patch(final, (CANDIDATE / 'W2-to-W3.patch').read_bytes(), True)
changed_w2 = sorted(name for name in final if final[name] != w2[name])
assert changed_w2 == ['backend/internal/service/native_stream_merged_interaction_test.go', 'backend/internal/service/openai_gateway_passthrough.go']
assert tree(ledger_for(w2, frozen)) == read_json(CANDIDATE / 'evidence/source-preservation.json')['actual_W2_tree_sha256']
assert patch(w2, (CANDIDATE / 'W2-to-W3.patch').read_bytes()) == final
preserved = []
for row in manifest['preservation_sources']:
    assert sha(base[row['path']]) == row['source_sha256']
    if not row['production_overlap']:
        assert final[row['path']] == base[row['path']]
        preserved.append(row['path'])
for row in manifest['production'] + manifest['regression']:
    assert sha(final[row['path']]) == row['after_sha256']
    if row['before_sha256'] is not None:
        assert sha(base[row['path']]) == row['before_sha256']
    else:
        assert row['path'] not in base

gap = final['backend/internal/service/native_api_key_cancellation_gaps_test.go']
adaptation = manifest['approved_test_adaptation']
assert gap.count(adaptation['new_expression'].encode()) == 1
assert sha(gap.replace(adaptation['new_expression'].encode(), adaptation['old_expression'].encode())) == adaptation['before_sha256']

controls = {}
for label, control_name in [('default', 'default-drain-control.json'), ('interaction', 'interaction-control.json')]:
    control = read_json(CANDIDATE / control_name)
    mutant = patch(final, (CANDIDATE / control['patch']).read_bytes())
    changes = [name for name in final if final[name] != mutant[name]]
    assert changes == [control['files'][0]['path']]
    assert not any(name.endswith('_test.go') for name in changes)
    assert sha(mutant[changes[0]]) == control['files'][0]['after_sha256']
    assert sha(final[changes[0]]) == control['files'][0]['before_sha256']
    controls[label] = {'changed_files': changes, 'fault_source_sha256': sha(mutant[changes[0]]), 'tests_identical': True}

suites = {}
events_by_suite = {}
for suite, count in [('normal', 569), ('native', 292), ('probe', 63), ('race', 129), ('default-red', 0), ('interaction-red', 0)]:
    raw = INPUT / 'actual-gates' / (suite + '.jsonl')
    events = [json.loads(line) for line in raw.read_text().splitlines()]
    events_by_suite[suite] = events
    counts = collections.Counter(d['Action'] for d in events if d.get('Test') and d['Action'] in ('pass', 'fail', 'skip'))
    receipt = read_json(raw.with_name(suite + '-receipt.json'))
    assert counts['pass'] == count and counts['skip'] == 0
    assert not receipt['compile_failed'] and receipt['provider_requests'] == 0
    assert receipt['exit'] == (1 if suite.endswith('-red') else 0)
    if not suite.endswith('-red'):
        assert counts['fail'] == 0
        assert all(d['Action'] != 'fail' for d in events)
    if suite != 'race':
        assert receipt['production_patch_sha256'] == manifest['patches']['production.patch']
        assert receipt['original_regression_patch_sha256'] == manifest['patches']['regression.patch']
        for action, key in [('pass', 'passed_tests'), ('fail', 'failed_tests'), ('skip', 'skipped_tests')]:
            observed = [d['Package'] + ':' + d['Test'] for d in events if d.get('Test') and d['Action'] == action]
            assert sorted(observed) == sorted(receipt[key]), (suite, key)
    else:
        assert receipt['pass_count'] == count and not receipt['data_race']
        assert receipt['failed_tests'] == [] and receipt['skip_count'] == 0
        assert 'DATA RACE' not in raw.read_text()
    suites[suite] = {'test_results': dict(counts), 'exit': receipt['exit'], 'raw_sha256': sha(raw.read_bytes()), 'receipt_sha256': sha(raw.with_name(suite + '-receipt.json').read_bytes())}

default_fails = {d['Test'] for d in events_by_suite['default-red'] if d.get('Test') and d['Action'] == 'fail'}
required = set(read_json(CANDIDATE / 'default-drain-control.json')['required_failed_leaves'])
assert default_fails == required | {'TestNativeAPIKeyCancellationRealTransport'}
default_output = ''.join(d.get('Output', '') for d in events_by_suite['default-red'])
assert 'default final billing drain changed: {known:false input:0 output:0' in default_output
assert 'default billing drain was canceled' in default_output
interaction = events_by_suite['interaction-red']
assert [d['Test'] for d in interaction if d.get('Test') and d['Action'] == 'fail'] == ['TestNativeMergedSpilledPrefixWriterFailure']
diagnostic = 'native forward did not finish within the failure/cancellation oracle: actual held Read after replay loss'
assert diagnostic in ''.join(d.get('Output', '') for d in interaction)
for suite in ['normal', 'race']:
    passed = {d['Test'] for d in events_by_suite[suite] if d.get('Test') and d['Action'] == 'pass'}
    assert required | {'TestNativeMergedSpilledPrefixWriterFailure', 'TestNativeAPIKeyCancellationKeepaliveWriterFailure/opt-in-false', 'TestNativeAPIKeyCancellationKeepaliveWriterFailure/opt-in-true', 'TestStreamMemoryResponsesSpoolCancelAndDeadline/cancel', 'TestStreamMemoryResponsesSpoolCancelAndDeadline/deadline', 'TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain'} <= passed
    roots = sorted(x for x in passed if '/' not in x)
    suites[suite]['root_tests'] = roots

# Preserve the shared first-output deadline machinery and its request-body wrapper
# byte for byte. The production patch only modifies staging in this source file.
timeout_name = 'backend/internal/service/openai_first_output_timeout.go'
timeout_marker = b'func (s *OpenAIGatewayService) openAIFirstOutputTimeout('
assert final[timeout_name].split(timeout_marker, 1)[1] == base[timeout_name].split(timeout_marker, 1)[1]
assert final['backend/internal/service/openai_gateway_forward.go'] == base['backend/internal/service/openai_gateway_forward.go']
policy_files = set()
for path in backend.rglob('*.go'):
    if not path.name.endswith('_test.go') and 'CancelsNativeAPIKeyOnDisconnect(' in path.read_text():
        policy_files.add(path.relative_to(backend).as_posix())
assert policy_files == {'internal/service/native_api_key_cancellation.go', 'internal/service/openai_gateway_passthrough.go', 'internal/service/gateway_anthropic_passthrough.go', 'internal/service/openai_gateway_messages_anthropic_native.go'}
race_passed = [d['Test'] for d in events_by_suite['race'] if d.get('Test') and d['Action'] == 'pass']
memory_race = [name for name in race_passed if name.startswith(('TestStreamMemory', 'TestSubreviewCancellationAfterReplay'))]
assert len(memory_race) == 35

evidence = {'supplied_hashes_verified': len(pins), 'executed_backend_files_verified': len(executed), 'tree_sha256': tree(frozen), 'production_patch_sha256': manifest['patches']['production.patch'], 'regression_patch_sha256': manifest['patches']['regression.patch'], 'exact_reconstruction': ['production/regression reverse and forward', 'canonical native/probe reverse and forward', 'W2-to-W3 reverse and forward'], 'canonical_unchanged_files': preserved, 'W2_changed_files': changed_w2, 'red_controls': controls, 'actual_supplied_Go': suites, 'local_execution': 'Python offline only; no local Go, race, Docker, network, Git writes, or subagents', 'race_scope': '129 named results; merged memory, cancellation and interaction roots, not all backend tests', 'memory_race_results': len(memory_race), 'first_output_timer_and_wrapper': 'byte-identical to canonical combined base', 'native_policy_production_files': sorted(policy_files), 'interaction_red_diagnostic': diagnostic}
(OWN / 'evidence.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
print(json.dumps({'status': 'PASS', 'supplied_hashes': len(pins), 'backend_files': len(executed), 'exact_patch_reconstruction': True, 'raw_suites_verified': list(suites), 'red_controls_tests_identical': True}, sort_keys=True))
