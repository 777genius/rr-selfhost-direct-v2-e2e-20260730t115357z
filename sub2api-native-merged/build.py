#!/usr/bin/env python3
"""Offline hunk merge/seal. Writes this namespace only; no Go/Git/network."""
import difflib
import json
import subprocess
from pathlib import Path
from patchlib import apply, ledger, sha, tree_sha

OWN = Path(__file__).resolve().parent
ROOT = OWN.parent
INPUT = ROOT / '.spike-inputs/original-inputs/original-inputs'
SERVICE = 'backend/internal/service/'
MEMORY_PIN = '12d8302bbaae05518c284dbad41c2ef089f364a97713331348854ecd546fb239'
CANCEL_PIN = '6befb28012ae72e00676acf445cce3e0074cd8680588f9586cf3441a018eb8fb'


GAP_NAME = SERVICE + 'native_api_key_cancellation_gaps_test.go'
GAP_ORIGINAL_PIN = '89807c417d2f62126088620014661588d2bd0fc29888056f8a4ff340c902ac0f'
GAP_APPROVED_PIN = 'c43c8569d205da65679cacf975607dfbf20741a82d43929acbc9efc912caf9e5'
GAP_OLD = b'int(max(gatewayUpstreamErrorBodyReadLimit, openAIUpstreamErrorBodyReadLimit))+1'
GAP_NEW = b'max(int(gatewayUpstreamErrorBodyReadLimit), int(openAIUpstreamErrorBodyReadLimit))+1'
REVIEW = ROOT / '.spike-inputs/original-inputs/independent-cancel-review'


def normalize_gap_test(data):
    """Only the approved typed-constant adaptation; refuse unexpected bytes."""
    if sha(data) != GAP_ORIGINAL_PIN or data.count(GAP_OLD) != 1:
        raise ValueError('unexpected frozen W3 gap test bytes or expression count')
    corrected = data.replace(GAP_OLD, GAP_NEW, 1)
    if sha(corrected) != GAP_APPROVED_PIN:
        raise ValueError('approved W3 gap test hash mismatch')
    return corrected


def emit(name, value):
    p = OWN / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def changes(a, b, lane):
    return [(i, j, b[k:l], lane) for op, i, j, k, l in
            difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op != 'equal']


def intersects(x, y):
    i, j, _, _ = x
    k, l, _, _ = y
    return max(i, k) < min(j, l) or i == j == k == l or i == j and k < i < l or k == l and i < k < j


def merge(name, before, memory, cancel):
    a, m, c = [x.decode().splitlines(True) for x in (before, memory, cancel)]
    me, ce = changes(a, m, 'memory-W2'), changes(a, c, 'cancel-W3')
    resolutions = []
    if name.endswith('/openai_gateway_passthrough.go'):
        # Resolve the whole overlapping closure from memory's bounded replay,
        # then retain cancellation's trusted-only Body.Close on replay failure.
        begin = a.index('\twritePendingLines := func() bool {\n')
        end = a.index('\tensureResponseFailedTerminal := func() {\n')
        mb, mend = m.index(a[begin]), m.index(a[end])
        replacement = ''.join(m[mb:mend])
        needle = '\t\t\tclientDisconnected = true\n'
        assert replacement.count(needle) == 1
        replacement = replacement.replace(needle, needle +
            '\t\t\tif account.CancelsNativeAPIKeyOnDisconnect() {\n'
            '\t\t\t\t_ = resp.Body.Close()\n\t\t\t}\n')
        touched = [e for e in me + ce if begin <= e[0] < end]
        assert len(touched) >= 3
        me = [e for e in me if e not in touched]
        ce = [e for e in ce if e not in touched]
        me.append((begin, end, replacement.splitlines(True), 'resolved-replay'))
        resolutions.append({'before_lines': [begin + 1, end], 'decision':
            'Memory bounded CommitTo, stopPrefixCancel and ownership=false before replay; trusted-only body Close on replay error; default usage drain preserved.'})
        # Keep BOTH policies explicit. Default prefix guards stop at ownership
        # handoff; the trusted account guard remains active through completion.
        for x in list(me):
            hits = [y for y in ce if intersects(x, y)]
            if not hits:
                continue
            assert len(hits) == 1 and x[0] == x[1] == hits[0][0] == hits[0][1]
            y = hits[0]
            mt, ct = ''.join(x[2]), ''.join(y[2])
            assert 'prefixOwnsCancellation && ctx.Err()' in mt
            assert 'account.CancelsNativeAPIKeyOnDisconnect() && ctx.Err()' in ct
            if mt.startswith('\t}\n'):
                assert ct.startswith('\t}\n')
                # Existing following brace closes the final memory guard.
                replacement = ct + '\t}\n' + mt[len('\t}\n'):]
            else:
                replacement = ct + mt
            me.remove(x)
            ce.remove(y)
            me.append((x[0], x[1], replacement.splitlines(True), 'resolved-guards'))
            resolutions.append({'before_lines': [x[0] + 1, x[1]], 'decision':
                'Retain opt-in lifetime guard and separate prefixOwnsCancellation guard. Trusted canceled usage is incomplete; default handoff continues drain.'})
    edits = sorted(me + ce, key=lambda e: (e[0], e[1]))
    for i, x in enumerate(edits):
        assert not any(intersects(x, y) for y in edits[i + 1:]), (name, x)
    out, cursor = [], 0
    rows = []
    for i, j, replacement, lane in edits:
        assert i >= cursor
        out.extend(a[cursor:i])
        out.extend(replacement)
        rows.append({'before_lines': [i + 1, j], 'lane': lane,
                     'before_sha256': sha(''.join(a[i:j]).encode()),
                     'replacement_sha256': sha(''.join(replacement).encode())})
        cursor = j
    out.extend(a[cursor:])
    return ''.join(out).encode(), {'path': name, 'edits': rows, 'manual_resolutions': resolutions}


def make_patch(base, target, names):
    chunks, rows = [], []
    for name in sorted(names):
        before, after = base.get(name, b''), target[name]
        delta = list(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                     fromfile='a/' + name if name in base else '/dev/null', tofile='b/' + name))
        chunks.extend(delta)
        rows.append({'path': name, 'before_sha256': sha(before) if name in base else None,
                     'after_sha256': sha(after), 'before_LOC': len(before.splitlines()),
                     'after_LOC': len(after.splitlines()),
                     'added': sum(l.startswith('+') and not l.startswith('+++') for l in delta),
                     'removed': sum(l.startswith('-') and not l.startswith('---') for l in delta)})
    return ''.join(chunks).encode(), rows


def main():
    input_manifest = INPUT / 'INPUT-HASHES.json'
    pins = json.loads(input_manifest.read_bytes())
    for name, expected in pins.items():
        assert sha((INPUT / name).read_bytes()) == expected, name
    base = {p.relative_to(INPUT / 'actual-source').as_posix(): p.read_bytes()
            for p in sorted((INPUT / 'actual-source/backend').rglob('*')) if p.is_file()}
    memory_patch = (INPUT / 'memory-w2/patches/production.patch').read_bytes()
    cancel_patch = (INPUT / 'cancel-w3/native-complete.patch').read_bytes()
    assert sha(memory_patch) == MEMORY_PIN and sha(cancel_patch) == CANCEL_PIN
    memory = apply(base, memory_patch)
    cancellation = apply(base, cancel_patch)
    memory_manifest = json.loads((INPUT / 'memory-w2/SOURCE.json').read_text())
    cancel_manifest = json.loads((INPUT / 'cancel-w3/manifest.json').read_text())
    for row in memory_manifest['files']:
        p = INPUT / 'memory-w2' / row['overlay_path']
        assert sha(p.read_bytes()) == row['after_sha256']
        if row['kind'] == 'production':
            assert memory[row['path']] == p.read_bytes()
    for row in cancel_manifest['files']:
        assert sha(cancellation[row['path']]) == row['after_sha256']
        assert cancellation[row['path']] == (INPUT / 'cancel-w3/overlay' / row['path']).read_bytes()
    memory_names = {r['path'] for r in memory_manifest['files'] if r['kind'] == 'production'}
    cancel_names = {r['path'] for r in cancel_manifest['files'] if not r['path'].endswith('_test.go')}
    prod_names = memory_names | cancel_names
    merged, decisions = dict(base), []
    for name in sorted(prod_names):
        if name in memory_names & cancel_names:
            merged[name], decision = merge(name, base[name], memory[name], cancellation[name])
            decisions.append(decision)
        else:
            merged[name] = memory[name] if name in memory_names else cancellation[name]
    # Use the SAME policy-selected context for transport and prefix ownership.
    # Direct handlers still honor their supplied cancellation/deadline; default
    # production requests retain detached billing drain even before first output.
    response_path = SERVICE + 'openai_gateway_passthrough.go'
    old = b'handleStreamingResponsePassthrough(ctx, resp, c, account, startTime, reqModel, upstreamPassthroughModel)'
    assert merged[response_path].count(old) == 1
    merged[response_path] = merged[response_path].replace(old, old.replace(b'(ctx,', b'(upstreamCtx,'), 1)
    decisions.append({'path': response_path, 'repair': 'Pass policy-selected upstreamCtx to response scanner/prefix watcher; preserve direct handler cancellation and trusted caller context.'})
    test_names = set()
    for row in memory_manifest['files']:
        if row['kind'] == 'tests':
            merged[row['path']] = (INPUT / 'memory-w2' / row['overlay_path']).read_bytes()
            test_names.add(row['path'])
    for row in cancel_manifest['files']:
        if row['path'].endswith('_test.go'):
            frozen = cancellation[row['path']]
            merged[row['path']] = normalize_gap_test(frozen) if row['path'] == GAP_NAME else frozen
            test_names.add(row['path'])
    supplied_pins = json.loads((ROOT / '.spike-inputs/original-inputs/INPUT-HASHES.json').read_bytes())
    for name in ('review.json', 'evidence.json', 'required-test-compile-fix.patch',
                 'native-complete-intcast.patch', 'native-regression-intcast.patch'):
        assert sha((REVIEW / name).read_bytes()) == supplied_pins['independent-cancel-review/' + name], name
    review = json.loads((REVIEW / 'review.json').read_bytes())
    review_evidence = json.loads((REVIEW / 'evidence.json').read_bytes())
    assert review['verdict'] == 'APPROVE' and review['original_complete_sha256'] == CANCEL_PIN
    assert review_evidence['adaptation']['pins']['green-w3'] == {'before_sha256': GAP_ORIGINAL_PIN, 'after_sha256': GAP_APPROVED_PIN}
    assert merged[GAP_NAME] == (REVIEW / 'adapted-reconstruction' / GAP_NAME).read_bytes()
    assert apply(cancellation, (REVIEW / 'required-test-compile-fix.patch').read_bytes())[GAP_NAME] == merged[GAP_NAME]
    assert apply(base, (REVIEW / 'native-complete-intcast.patch').read_bytes())[GAP_NAME] == merged[GAP_NAME]
    # Native292 includes this frozen historical independent boundary control,
    # installed by the controller's original runner, absent from production base.
    historical_control = ROOT / 'sub2api-fork-review-v2/independent_boundary_test.go.txt'
    control_bytes = historical_control.read_bytes()
    assert sha(control_bytes) == '3ca97c2d50f0c3c498c51d1fb0af9b7fa5352089953f84d1224e6ea5e03887ce'
    control_name = SERVICE + 'independent_boundary_test.go'
    assert control_name not in base
    merged[control_name] = control_bytes
    test_names.add(control_name)
    interaction_name = SERVICE + 'native_stream_merged_interaction_test.go'
    assert interaction_name not in base
    merged[interaction_name] = (OWN / 'native_stream_merged_interaction_test.go').read_bytes()
    test_names.add(interaction_name)
    # Syntax/format check via standalone gofmt stdin: no source tree copy.
    for name in sorted(prod_names | test_names):
        r = subprocess.run([str(INPUT / 'gofmt')], input=merged[name], capture_output=True)
        assert r.returncode == 0 and not r.stderr, (name, r.stderr)
        if name != control_name:
            assert r.stdout == merged[name], ('format differs', name)
    production, prod_rows = make_patch(base, merged, prod_names)
    regression, test_rows = make_patch(base, merged, test_names)
    assert sha(production) == '16bc1644e564847f0565dffd765af6c7e0c7a70ac5677147d3166e20c90923a5', 'W3 exact production mismatch'
    (OWN / 'production.patch').write_bytes(production)
    (OWN / 'regression.patch').write_bytes(regression)
    assert apply(apply(base, production), regression) == merged
    # Explicit fault control for the new source interaction test. This is NEVER
    # production: lose exactly the two trusted replay actions, retain all other
    # merged bytes and the IDENTICAL test. Root must establish behavioral RED.
    interaction_path = SERVICE + 'openai_gateway_passthrough.go'
    mutant = dict(merged)
    text = merged[interaction_path].decode()
    begin = text.index('\twritePendingLines := func() bool {\n')
    end = text.index('\tensureResponseFailedTerminal := func() {\n')
    close_guard = '\t\t\tif account.CancelsNativeAPIKeyOnDisconnect() {\n\t\t\t\t_ = resp.Body.Close()\n\t\t\t}\n'
    closure = text[begin:end]
    assert closure.count(close_guard) == 1
    text = text[:begin] + closure.replace(close_guard, '') + text[end:]
    return_guard = '\t\t\t\t\tif account.CancelsNativeAPIKeyOnDisconnect() {\n\t\t\t\t\t\treturn resultWithUsage(), errors.New("stream usage incomplete after disconnect")\n\t\t\t\t\t}\n'
    assert text.count(return_guard) == 1
    text = text.replace(return_guard, '')
    mutant[interaction_path] = text.encode()
    fault_delta, fault_rows = make_patch(merged, mutant, {interaction_path})
    (OWN / 'interaction-replay-loss.RED-only.patch').write_bytes(fault_delta)
    assert apply(merged, fault_delta) == mutant
    emit('interaction-control.json', {'kind': 'RED-only explicit source fault, NEVER production',
         'patch': 'interaction-replay-loss.RED-only.patch', 'sha256': sha(fault_delta), 'files': fault_rows,
         'identical_test_sha256': sha(merged[interaction_name]), 'actual_Go_RED': 'NOT RUN',
         'fault': 'Lose trusted Body.Close AND early return after failed spilled-prefix replay; live caller leaves Scanner waiting on held terminal bytes'})
    # Bind the repair to the ACTUAL supplied merged tree, not a reconstructed
    # standalone component. Exactly one production call argument changes.
    supplied_root = ROOT / '.spike-inputs'
    supplied = json.loads((supplied_root / 'INPUT-HASHES.json').read_bytes())
    for name, expected in supplied.items():
        assert sha((supplied_root / name).read_bytes()) == expected, name
    actual = {p.relative_to(supplied_root / 'actual-source').as_posix(): p.read_bytes()
              for p in sorted((supplied_root / 'actual-source/backend').rglob('*')) if p.is_file()}
    w2 = json.loads((supplied_root / 'candidate/sub2api-native-merged/merged-hashes.json').read_bytes())
    assert ledger(actual) == w2 and tree_sha(w2) == 'fa660b8178f63dd9c385274c2f01608368227b202881ab9cc8cba29c364d96f1'
    repair_names = {k for k in actual if actual[k] != merged[k]}
    assert repair_names == {response_path, interaction_name} and set(actual) == set(merged)
    assert actual[response_path].count(old) == 1
    assert actual[response_path].replace(old, old.replace(b'(ctx,', b'(upstreamCtx,'), 1) == merged[response_path]
    repair, repair_rows = make_patch(actual, merged, repair_names)
    (OWN / 'W2-to-W3.patch').write_bytes(repair)
    drain_mutant = dict(merged)
    drain_mutant[response_path] = actual[response_path]
    drain_fault, drain_rows = make_patch(merged, drain_mutant, {response_path})
    (OWN / 'default-drain-loss.RED-only.patch').write_bytes(drain_fault)
    emit('default-drain-control.json', {'kind': 'RED-only actual old merged production regression, NEVER production',
        'patch': 'default-drain-loss.RED-only.patch', 'sha256': sha(drain_fault), 'files': drain_rows,
        'identical_test_sha256': sha(merged[SERVICE + 'native_api_key_cancellation_test.go']),
        'actual_Go_RED': 'Supplied old W2 normal raw JSONL has these exact two behavioral leaf failures; W3 paired run pending',
        'required_failed_leaves': ['TestNativeAPIKeyCancellationRealTransport/responses/before-headers/opt-in-false',
                                   'TestNativeAPIKeyCancellationRealTransport/responses/before-ack/opt-in-false']})
    history = {'status': 'SOURCE VERIFIED; W3 runtime PENDING', 'actual_W2_tree_sha256': tree_sha(w2),
        'W2_to_W3_patch_sha256': sha(repair), 'changed_files': repair_rows, 'unchanged_backend_files': len(actual)-len(repair_names),
        'historical_W1_W2_inputs': 'Immutable .spike-inputs/original-inputs and .spike-inputs/candidate; no history rewritten',
        'raw_gate_references': {str((supplied_root / ('actual-gates/' + n)).relative_to(ROOT)): sha((supplied_root / ('actual-gates/' + n)).read_bytes())
                              for n in ('normal.jsonl', 'normal-receipt.json', 'interaction-red.jsonl', 'interaction-red-receipt.json')}}
    emit('evidence/source-preservation.json', history)
    normal_events = [json.loads(line) for line in (supplied_root / 'actual-gates/normal.jsonl').read_text().splitlines()]
    red_events = [json.loads(line) for line in (supplied_root / 'actual-gates/interaction-red.jsonl').read_text().splitlines()]
    emit('evidence/actual-W2-diagnosis.json', {'source_tree_sha256': tree_sha(w2),
        'normal_passed': sum(e.get('Action') == 'pass' and bool(e.get('Test')) for e in normal_events),
        'normal_failed_tests': [e['Test'] for e in normal_events if e.get('Action') == 'fail' and e.get('Test')],
        'billing_failure_output': [e for e in normal_events if 'default final billing drain changed' in e.get('Output', '') or 'default completed before held upstream release' in e.get('Output', '')],
        'old_interaction_RED_passed': [e['Test'] for e in red_events if e.get('Action') == 'pass' and e.get('Test')],
        'cause_default': 'Transport receives detached upstreamCtx, but scanner prefix watcher receives canceled caller ctx and closes the real body before semantic replay.',
        'cause_non_discriminating_fixture': 'A buffered SSE blank line lets the replay-loss mutant reach the intact loop-bottom trusted disconnect guard; no second writer failure is needed. Hold that separator upstream to force the next real Read.',
        'W3_runtime': 'PENDING controller paired behavioral RED/GREEN and race; no execution by producer'})

    # Canonical public route: inverse the EXACT native/probe deltas, then
    # reapply them to prove all backend bytes round-trip to combined source.
    canonical = [ROOT / 'sub2api-fork/patches/native-reasoning.patch',
                 INPUT / 'probe/patches/disable-capability-probe.patch']
    official = dict(base)
    for path in reversed(canonical):
        official = apply(official, path.read_bytes(), reverse=True)
    public_combined = dict(official)
    canonical_rows = []
    for path, name in zip(canonical, ['canonical-native.patch', 'canonical-probe.patch']):
        data = path.read_bytes()
        (OWN / name).write_bytes(data)
        public_combined = apply(public_combined, data)
        canonical_rows.append({'path': name, 'sha256': sha(data), 'input_reference': str(path.relative_to(ROOT))})
    assert public_combined == base
    emit('base-hashes.json', ledger(base))
    emit('official-hashes.json', ledger(official))
    emit('merged-hashes.json', ledger(merged))
    emit('merge-hunks.json', decisions)
    emit('component-before-after.json', {'scope': 'Exact bytes, not runtime evidence',
        'files': [{'path': name, 'original_combined': sha(base[name]) if name in base else None,
                   'memory_W2': sha(memory[name]) if name in memory else None,
                   'cancel_W3': sha(cancellation[name]) if name in cancellation else None,
                   'actual_merged_W2': sha(actual[name]), 'repaired_merged_W3': sha(merged[name])}
                  for name in sorted(prod_names | test_names)],
        'original_gap_test': GAP_ORIGINAL_PIN, 'approved_gap_test': GAP_APPROVED_PIN})
    adaptation = {
        'path': GAP_NAME, 'before_sha256': GAP_ORIGINAL_PIN, 'after_sha256': GAP_APPROVED_PIN,
        'old_expression': GAP_OLD.decode(), 'new_expression': GAP_NEW.decode(), 'occurrences': 1,
        'reason': 'Existing max(int,int) shadows builtin; typed 512KiB constants fit int',
        'assertions_unchanged': True, 'production_unchanged': True,
        'supplied_review_manifest': {'path': '.spike-inputs/INPUT-HASHES.json', 'sha256': sha((ROOT / '.spike-inputs/INPUT-HASHES.json').read_bytes())},
        'root_metadata_reference': '.spike-inputs/original-inputs/independent-cancel-review/evidence.json#adaptation',
        'root_results_scope': 'Standalone corrected W3 ONLY: 527 PASS, 0 FAIL, 0 SKIP; W2 RED 12 leaf failures, 42 controls PASS; NOT merged',
        'references': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in
                       [REVIEW / name for name in ('review.json', 'evidence.json', 'required-test-compile-fix.patch',
                                                  'native-complete-intcast.patch', 'native-regression-intcast.patch')]}}
    emit('input-references.json', {
        'approved_test_adaptation': adaptation,
        'supplied_manifest': {'path': str(input_manifest.relative_to(ROOT)), 'sha256': sha(input_manifest.read_bytes()), 'entries': len(pins), 'all_verified': True},
        'immutable_component_files': {k: v for k, v in pins.items() if k.startswith(('memory-w2/', 'cancel-w3/', 'memory-review-w2/', 'actual-memory-gates/'))},
        'canonical_patches': canonical_rows,
        'native292_historical_control': {'input_reference': str(historical_control.relative_to(ROOT)), 'path': control_name, 'sha256': sha(control_bytes)},
        'new_interaction_test': {'path': interaction_name, 'sha256': sha(merged[interaction_name]), 'Go_result': 'NOT RUN',
                                 'contract': 'Opt-in spilled prefix replay failure with live caller closes real body, joins attempt, unknown usage, one dispatch/effect'},
        'public_official': {'repository': 'https://github.com/Wei-Shaw/sub2api', 'revision': '96f4c115c9749078f90cbf210a01d39baf3f53b6', 'release': 'v0.2.11',
                            'authentication': 'supplied pin; no network/Git authentication by this worker; official-hashes.json is exact backend content oracle'},
        'public_sandbox_reference': {'repository': 'https://github.com/777genius/rr-selfhost-direct-v2-e2e-20260730t115357z', 'revision': '956603247f893ece0b9d1ec08d2cbe013342c48d', 'evidence': '.spike-inputs/original-inputs/native/PLAN.md initial facts and gateway-spike/PLAN.md repository identity; historical reference, not this final integration SHA'}})
    controls = memory_manifest['preservation_sources']
    for r in controls:
        assert sha(base[r['path']]) == r['source_sha256']
        if r['path'] not in prod_names:
            assert merged[r['path']] == base[r['path']]
    emit('manifest.json', {'schema': 1, 'namespace': OWN.name,
        'source': 'exact original combined native/probe backend; full production delta includes both components',
        'components': {'memory_W2_production_sha256': MEMORY_PIN, 'cancel_W3_complete_sha256': CANCEL_PIN,
                       'cancel_W3_original_gap_test_sha256': GAP_ORIGINAL_PIN, 'cancel_W3_approved_gap_test_sha256': GAP_APPROVED_PIN,
                       'cancel_W3_production_sha256': sha((INPUT / 'cancel-w3/native-production.patch').read_bytes())},
        'patches': {'production.patch': sha(production), 'regression.patch': sha(regression), 'W2-to-W3.patch': sha(repair), 'default-drain-loss.RED-only.patch': sha(drain_fault), 'interaction-replay-loss.RED-only.patch': sha(fault_delta), **{r['path']: r['sha256'] for r in canonical_rows}},
        'base_tree_sha256': tree_sha(ledger(base)), 'official_tree_sha256': tree_sha(ledger(official)), 'merged_tree_sha256': tree_sha(ledger(merged)),
        'production': prod_rows, 'regression': test_rows, 'preservation_sources': controls,
        'gofmt': {'syntax_files': len(prod_names | test_names), 'format_files': len(prod_names | test_names) - 1,
                  'frozen_unformatted_control_retained': control_name,
                  'executable_sha256': sha((INPUT / 'gofmt').read_bytes()), 'syntax_and_format_only': True},
        'runtime': {'merged_Go': 'NOT RUN', 'merged_race': 'NOT RUN', 'cancel_W3_newgap_RED_GREEN': 'Reviewer supplies root W2 RED 12 leaves / 42 controls PASS, corrected standalone W3 527 PASS / 0 SKIP; NOT merged', 'cancel_W3_independent_review': 'APPROVE production plus exact intcast; NOT merged approval'},
        'approved_test_adaptation': adaptation, 'canonical_patches': canonical_rows})
    (OWN / 'native-patterns.json').write_bytes((INPUT / 'memory-w2/preservation-patterns.json').read_bytes())
    # Copy only small exact receipts, never historical trees/runtime archives.
    for name in ('green', 'native', 'probe', 'red'):
        data = (INPUT / ('actual-memory-gates/' + name + '-receipt.json')).read_bytes()
        p = OWN / 'evidence' / ('memory-W2-' + name + '.json')
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(data)
    (OWN / 'evidence/memory-W2-review.json').write_bytes((INPUT / 'memory-review-w2/review.json').read_bytes())
    print(json.dumps({'offline': 'PASS', 'verified_inputs': len(pins), 'production_files': len(prod_names), 'frozen_test_files': len(test_names), 'merged_Go': 'NOT RUN', 'production_sha256': sha(production)}))


if __name__ == '__main__':
    main()
