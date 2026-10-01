#!/usr/bin/env python3
"""Exact offline W1/W2 audit. Source/control-flow evidence, never Go execution."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re

OWN = Path(__file__).resolve().parent
INPUT = OWN.parent / '.spike-inputs'
W1 = INPUT / 'candidate' / OWN.name
sha = lambda data: hashlib.sha256(data).hexdigest()
spec = importlib.util.spec_from_file_location('memory_verify', OWN / 'verify.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def main():
    full = verify.verify()
    copied = json.loads((OWN / 'evidence/w1-copy.json').read_text())
    assert copied['copied_exact_before_edits']
    for rel, digest in copied['files'].items():
        assert sha((W1 / rel).read_bytes()) == digest, rel
    delta = json.loads((OWN / 'W2-DELTA.json').read_text())
    assert sha((W1 / 'patches/production.patch').read_bytes()) == delta['base_production_patch_sha256']
    applications = 0
    for row in delta['files']:
        before_path = W1 / row['kind'] / row['path']
        before = before_path.read_text() if before_path.exists() else ''
        assert (sha(before.encode()) if before else None) == row['before_sha256']
        patch = (OWN / row['patch']).read_text()
        assert sha(patch.encode()) == delta['patches'][row['patch']]
        sections = re.split(r'(?m)^--- ', patch)[1:]
        assert len(sections) == 1
        _, rest = sections[0].split('\n', 1)
        new, hunks = rest.split('\n', 1)
        assert new == '+++ b/' + row['path']
        after = verify.apply_exact(before, hunks)
        assert after == (OWN / row['overlay_path']).read_text()
        assert sha(after.encode()) == row['after_sha256']
        applications += 1

    # All W1 bounds, Messages queue/idle code and valuable Go tests remain byte exact.
    unchanged = []
    for base in ('production', 'tests'):
        for p in (W1 / base).rglob('*.go'):
            rel = p.relative_to(W1)
            if p.name == 'openai_gateway_passthrough.go':
                continue
            assert (OWN / rel).read_bytes() == p.read_bytes(), rel
            unchanged.append(str(rel))
    assert len(unchanged) == 7
    assert (OWN / 'preservation-patterns.json').read_bytes() == (W1 / 'preservation-patterns.json').read_bytes()
    # Invert precisely the ownership repair; every remaining byte, including
    # semantic/failover/accounting/default drain logic, must equal W1.
    rel = 'production/backend/internal/service/openai_gateway_passthrough.go'
    old = (W1 / rel).read_text()
    new = (OWN / rel).read_text()
    old_comment = "\t// The caller's deadline/cancellation bounds prefix reads. After output starts,\n\t// retain the existing usage-drain policy. Closing Body interrupts Scanner.Read."
    new_comment = "\t// The caller's deadline/cancellation bounds prefix reads until replay handoff.\n\t// Ownership is separate from successful semantic output: a failed prefix or\n\t// first semantic write must retain the existing upstream usage-drain policy.\n\t// Closing Body interrupts Scanner.Read.\n\tprefixOwnsCancellation := true"
    expected = old.replace(old_comment, new_comment).replace('\t\tstopPrefixCancel()\n', '\t\tstopPrefixCancel()\n\t\tprefixOwnsCancellation = false\n').replace('if !clientOutputStarted && ctx.Err() != nil {', 'if prefixOwnsCancellation && ctx.Err() != nil {')
    assert new == expected
    assert new.count('if prefixOwnsCancellation && ctx.Err() != nil {') == 2
    assert new.count('prefixOwnsCancellation = false') == 1
    handoff = new[new.index('\twritePendingLines :='):new.index('\tensureResponseFailedTerminal :=')]
    assert handoff.index('stopPrefixCancel()') < handoff.index('prefixOwnsCancellation = false') < handoff.index('prefix.CommitTo(w)')
    callback = re.search(r'stopPrefixCancel := context.AfterFunc\(ctx, (.*)\)', new)[1]
    assert 'prefix' not in callback and 'resp.Body.Close()' in callback
    repro = INPUT / 'independent-review/cancel-after-replay-repro.go.txt'
    test = OWN / 'tests/backend/internal/service/stream_memory_replay_handoff_test.go'
    assert test.read_bytes() == repro.read_bytes(), 'Prescribed independent reproducer must remain byte exact'
    assert '&Account{ID: 1, Platform: PlatformOpenAI}' in test.read_text()
    assert 'require.Equal(t, 7, r.usage.InputTokens)' in test.read_text()
    assert 'require.Equal(t, 5, r.usage.OutputTokens)' in test.read_text()

    # Extract the added guards from exact source, then evaluate the reviewed
    # lifecycle states. This is a source-derived phase model, not a handler run.
    phase_model = []
    for label, source in [('W1', old), ('W2', new)]:
        guards = re.findall(r'if ([!\w]+) && ctx.Err\(\) != nil \{\n\s*return resultWithUsage\(\), fmt.Errorf\("stream usage incomplete before output:', source)
        assert len(guards) == 2 and len(set(guards)) == 1
        for event, cancelled, handed_off in [('pre_prefix_cancel', True, False), ('pre_prefix_deadline', True, False), ('prefix_writer_error', True, True), ('first_semantic_writer_error', True, True)]:
            state = {'clientOutputStarted': False, 'prefixOwnsCancellation': not handed_off}
            predicate = guards[0]
            rejects = cancelled and (not state[predicate[1:]] if predicate.startswith('!') else state[predicate])
            assert rejects == (True if label == 'W1' else not handed_off)
            phase_model.append({'source': label, 'event': event, 'both_added_guards_reject': rejects, 'kind': 'source-derived state evaluation only'})
    supplied = {}
    for name in ('red', 'green', 'native', 'probe', 'handoff-old', 'handoff-new'):
        p = INPUT / 'actual-gates' / (name + '-receipt.json')
        r = json.loads(p.read_text())
        assert r['production_patch_sha256'] == delta['base_production_patch_sha256']
        assert r['compile_failed'] is False and r['skip_count'] == 0
        supplied[name] = {'path': str(p.relative_to(OWN.parent)), 'sha256': sha(p.read_bytes()), 'receipt': r, 'provenance': 'supplied controller summary; raw logs not supplied; not rerun by W2'}
    assert supplied['green']['receipt']['pass_count'] == 32
    assert supplied['native']['receipt']['pass_count'] == 292
    assert supplied['probe']['receipt']['pass_count'] == 63
    assert supplied['handoff-old']['receipt']['exit'] == 0
    assert supplied['handoff-new']['receipt']['exit'] == 1
    assert set(supplied['handoff-new']['receipt']['failed_tests']) == {
        'TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain',
        'TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain/prefix_writer_error',
        'TestSubreviewCancellationAfterReplayHandoffPreservesUsageDrain/first_semantic_writer_error'}
    result = {'status': 'PASS', 'full_patch_verification': full,
        'W2_delta_applications': applications, 'original_W1_files_unchanged': unchanged,
        'prescribed_test_sha256': sha(test.read_bytes()), 'default_native_flag': 'absent in exact independent reproducer',
        'phase_model': phase_model, 'supplied_controller_receipts': supplied,
        'independent_review': {'path': '.spike-inputs/independent-review/review.json', 'sha256': sha((INPUT / 'independent-review/review.json').read_bytes()), 'finding': 'P1 prefix ownership guard mismatch addressed by distinct state'},
        'repaired_actual_Go_race_profile_live': 'NOT RUN by W2; merged source absent',
        'integration': 'Four-file cancellation-worker overlap remains controller hunk merge; no shared source overwritten'}
    (OWN / 'evidence/w2-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'W2_delta_applications': applications, 'unchanged_W1_files': len(unchanged), 'reproducer_byte_exact': True, 'full_patch_applications': full['patch_file_applications_verified'], 'Go': 'NOT RUN'}))

if __name__ == '__main__':
    main()
