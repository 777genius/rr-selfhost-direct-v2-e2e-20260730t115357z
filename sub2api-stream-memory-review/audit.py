"""Independent offline W2 audit; writes only in this review directory."""
from pathlib import Path
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time

OWN = Path(__file__).resolve().parent
INPUT = OWN.parent / '.spike-inputs'
PKG = INPUT / 'candidate/sub2api-stream-memory-fork'
W1 = INPUT / 'worker-frozen-inputs/candidate/sub2api-stream-memory-fork'
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda p: json.loads(p.read_text())
evidence = {'reviewed_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'locally_executed_Go': False, 'race': 'NOT RUN / not supplied',
            'scope': 'exact isolated W2 package; future W3 merge excluded'}

manifest = read(INPUT / 'INPUT-HASHES.json')
for path, digest in manifest.items():
    assert sha((INPUT / path).read_bytes()) == digest, path
evidence['frozen_inputs'] = {'checked': len(manifest), 'manifest_sha256': sha((INPUT / 'INPUT-HASHES.json').read_bytes())}
inventory = read(PKG / 'artifact-manifest.json')
for path, row in inventory['files'].items():
    data = (PKG / path).read_bytes()
    assert len(data) == row['bytes'] and sha(data) == row['sha256'], path
evidence['package_inventory_checked'] = len(inventory['files'])

source = read(PKG / 'SOURCE.json')
rows = {r['path']: r for r in source['files']}
for row in rows.values():
    after = (PKG / row['overlay_path']).read_bytes()
    assert sha(after) == row['after_sha256']
    if row['before_sha256']:
        before = (INPUT / 'actual-source' / row['path']).read_bytes()
        assert sha(before) == row['before_sha256']
        for hunk in row['hunks']:
            for side, data in [('before', before), ('after', after)]:
                lo, hi = hunk[side + '_lines']
                assert sha(b''.join(data.splitlines(True)[lo-1:hi])) == hunk[side + '_sha256']
evidence['source_files'] = [{k: r[k] for k in ('path', 'kind', 'before_sha256', 'after_sha256')} for r in rows.values()]

def apply_exact(patch, tree):
    outputs = {}
    for section in re.split(r'(?m)^--- ', patch)[1:]:
        old, new, rest = section.split('\n', 2)
        path = new.removeprefix('+++ b/')
        original = [] if old == '/dev/null' else (tree / path).read_text().splitlines(True)
        cursor, output = 0, []
        for hunk in re.split(r'(?m)^@@ ', rest)[1:]:
            header, body = hunk.split('\n', 1)
            m = re.match(r'-(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', header)
            assert m, header
            old_count, new_count = int(m[2] or 1), int(m[4] or 1)
            start = int(m[1]) - (1 if old_count else 0)
            assert start >= cursor
            output.extend(original[cursor:start])
            cursor = start
            assert len(output) == int(m[3]) - (1 if new_count else 0)
            removed, added = 0, 0
            for line in body.splitlines(True):
                assert line[0] in ' +-'
                if line[0] in ' -':
                    assert original[cursor] == line[1:], (path, cursor)
                    cursor += 1
                    removed += 1
                if line[0] in ' +':
                    output.append(line[1:])
                    added += 1
            assert (removed, added) == (old_count, new_count)
        output.extend(original[cursor:])
        outputs[path] = ''.join(output).encode()
        assert outputs[path] == (PKG / rows[path]['overlay_path']).read_bytes(), path
    return outputs

applications = 0
for patch in source['patches']:
    data = (PKG / patch['path']).read_bytes()
    assert sha(data) == patch['sha256']
    applications += len(apply_exact(data.decode(), INPUT / 'actual-source'))
delta = read(PKG / 'W2-DELTA.json')
for path, digest in delta['patches'].items():
    data = (PKG / path).read_bytes()
    assert sha(data) == digest
    apply_exact(data.decode(), W1 / ('production' if 'production' in path else 'tests'))
evidence['exact_patch_applications'] = {'full': applications, 'W1_delta': 2, 'delta_hashes': delta['patches']}
unchanged = []
for row in rows.values():
    if row['path'].endswith(('openai_gateway_passthrough.go', 'stream_memory_replay_handoff_test.go')):
        continue
    assert (W1 / row['overlay_path']).read_bytes() == (PKG / row['overlay_path']).read_bytes()
    unchanged.append(row['overlay_path'])
evidence['seven_W1_files_byte_unchanged'] = unchanged
for row in source['preservation_sources']:
    assert sha((INPUT / 'actual-source' / row['path']).read_bytes()) == row['source_sha256']
evidence['native_probe_source_pins_checked'] = len(source['preservation_sources'])

review = read(INPUT / 'previous-review/review.json')
assert review['findings'][0]['severity'] == 'P1'
prescribed = (INPUT / 'previous-review/cancel-after-replay-repro.go.txt').read_bytes()
assert prescribed == (PKG / 'tests/backend/internal/service/stream_memory_replay_handoff_test.go').read_bytes()
assert b'require.True(t, w.failed)' in prescribed
assert b'require.Equal(t, 7, r.usage.InputTokens)' in prescribed
assert b'require.Equal(t, 5, r.usage.OutputTokens)' in prescribed
assert b'require.NoError(t, err)' in prescribed
assert b'&Account{ID: 1, Platform: PlatformOpenAI}' in prescribed
evidence['mandatory_P1_review_sha256'] = sha((INPUT / 'previous-review/review.json').read_bytes())
evidence['byte_exact_reproducer_sha256'] = sha(prescribed)

path = 'production/backend/internal/service/openai_gateway_passthrough.go'
new = (PKG / path).read_text()
old = (W1 / path).read_text()
assert sha(old.encode()) == '93baafd90df032bb5880ecf44037bcfb82e928ff7826324cd124edd46bf73c4b'
evidence['W1_passthrough_sha256'] = sha(old.encode())
assert old.count('if !clientOutputStarted && ctx.Err() != nil {') == 2
assert new.count('if prefixOwnsCancellation && ctx.Err() != nil {') == 2
assert new.count('prefixOwnsCancellation := true') == 1
assert new.count('prefixOwnsCancellation = false') == 1
assert 'stopPrefixCancel()\n\t\tprefixOwnsCancellation = false\n\t\tstopKeepalive()' in new
assert new.index('prefixOwnsCancellation = false') < new.index('if err := prefix.CommitTo(w)')
assert 'context.AfterFunc(ctx, func() { _ = resp.Body.Close() })' in new
expected = old.replace(
    '\t// The caller\'s deadline/cancellation bounds prefix reads. After output starts,\n'
    '\t// retain the existing usage-drain policy. Closing Body interrupts Scanner.Read.\n',
    '\t// The caller\'s deadline/cancellation bounds prefix reads until replay handoff.\n'
    '\t// Ownership is separate from successful semantic output: a failed prefix or\n'
    '\t// first semantic write must retain the existing upstream usage-drain policy.\n'
    '\t// Closing Body interrupts Scanner.Read.\n\tprefixOwnsCancellation := true\n')
expected = expected.replace('\t\tstopPrefixCancel()\n\t\tstopKeepalive()',
                            '\t\tstopPrefixCancel()\n\t\tprefixOwnsCancellation = false\n\t\tstopKeepalive()')
expected = expected.replace('if !clientOutputStarted && ctx.Err() != nil {',
                            'if prefixOwnsCancellation && ctx.Err() != nil {')
assert expected == new, 'Additional policy or drain change outside minimal ownership repair'
evidence['minimal_ownership_delta'] = 'PASS: exact entire W1 source plus declaration, handoff assignment, both guard replacements and explanatory comment'
# State transitions from the audited source; expressly not handler execution.
phases = []
for name, owner, output in [('pre_cancel', True, False), ('pre_deadline', True, False),
                            ('prefix_writer_failure', False, False), ('semantic_writer_failure', False, False),
                            ('successful_output', False, True)]:
    phases.append({'phase': name, 'W1_guard_rejects': not output,
                   'W2_both_guards_reject': owner, 'semantic_output': output})
evidence['source_derived_phase_evaluation'] = phases
evidence['AfterFunc_limit'] = 'Stop does not join an already firing callback. Body close/read failure can still leave terminal usage incomplete; no join or complete-usage guarantee.'

patch_hash = sha((PKG / 'patches/production.patch').read_bytes())
assert patch_hash == '12d8302bbaae05518c284dbad41c2ef089f364a97713331348854ecd546fb239'
receipts = {}
for suite, count in [('green', 35), ('native', 292), ('probe', 63), ('red', None)]:
    path = INPUT / 'actual-gates' / (suite + '-receipt.json')
    r = read(path)
    assert r['production_patch_sha256'] == patch_hash
    assert r['skip_count'] == 0 and not r['compile_failed'] and r['provider_requests'] == 0
    if count:
        assert r['pass_count'] == count and r['exit'] == 0 and not r['failed_tests']
    else:
        required = {'TestStreamMemoryMessagesReadAhead/passthrough', 'TestStreamMemoryMessagesReadAhead/native',
                    'TestStreamMemoryResponsesPrefixOverflow', 'TestStreamMemoryResponsesPrefixCancellationClosesReader'}
        assert required <= set(r['failed_tests']) and r['exit'] == 1
    receipts[suite] = {'sha256': sha(path.read_bytes()), 'receipt': r, 'kind': 'supplied actual normal Go summary; not independently rerun'}
for suite, success in [('handoff-old', True), ('handoff-new', False)]:
    path = INPUT / 'worker-frozen-inputs/actual-gates' / (suite + '-receipt.json')
    r = read(path)
    assert r['production_patch_sha256'] == delta['base_production_patch_sha256']
    assert r['skip_count'] == 0 and not r['compile_failed']
    if success:
        assert r['pass_count'] == 3 and r['exit'] == 0
    else:
        assert r['exit'] == 1 and any(x.endswith('/prefix_writer_error') for x in r['failed_tests'])
        assert any(x.endswith('/first_semantic_writer_error') for x in r['failed_tests'])
    receipts[suite] = {'sha256': sha(path.read_bytes()), 'receipt': r, 'kind': 'supplied independent old/W1 control summary'}
evidence['production_patch_sha256'] = patch_hash
evidence['supplied_receipts'] = receipts

gofmt = INPUT / 'worker-frozen-inputs/gofmt'
with tempfile.TemporaryDirectory(dir=OWN) as directory:
    formatter = Path(directory) / 'gofmt'
    formatter.write_bytes(gofmt.read_bytes())
    formatter.chmod(0o700)
    assert sha(formatter.read_bytes()) == sha(gofmt.read_bytes())
    for row in rows.values():
        p = PKG / row['overlay_path']
        result = subprocess.run([str(formatter), str(p)], capture_output=True, check=True)
        assert result.stdout == p.read_bytes(), p
evidence['standalone_gofmt'] = {'files': len(rows), 'executable_sha256': sha(gofmt.read_bytes())}

# Independent OS replay check demonstrates only descriptor/framing assumptions.
with tempfile.TemporaryDirectory(dir=OWN) as directory:
    fd, path = tempfile.mkstemp(dir=directory)
    assert stat.S_IMODE(os.fstat(fd).st_mode) == 0o600
    os.unlink(path)
    assert not Path(path).exists()
    data = b': waiting  \n\nid: opaque-9007199254740993\nevent: response.created\ndata: {"type":"response.created"}\n\n'
    assert os.write(fd, data) == len(data)
    os.lseek(fd, 0, os.SEEK_SET)
    assert os.read(fd, len(data)) == data
    os.close(fd)
    try:
        os.fstat(fd)
        raise AssertionError('descriptor retained')
    except OSError:
        pass
evidence['offline_OS_check'] = 'PASS: 0600, unlink-before-data, exact LF/opaque bytes, closed FD; Python OS check, not Go'
history = INPUT / 'worker-frozen-inputs/worker-frozen-inputs/actual-execution'
historical = []
for p in sorted(history.glob('*/execution.json')):
    for r in read(p)['results']:
        assert r['empirical_status'] == 'FAIL' and r['functional_status'] == 'PASS'
        assert r['physical_interval_status'] == 'NOTPROVEN'
        historical.append(r['id'])
assert len(historical) == 20
evidence['historical_memory_FAIL_retained'] = historical
evidence['verdict'] = 'APPROVE'
(OWN / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps({'verdict': evidence['verdict'], 'frozen_inputs': len(manifest),
                  'patch_applications': applications + 2, 'gofmt_files': len(rows),
                  'production_patch_sha256': patch_hash}))
