#!/usr/bin/env python3
"""Offline package/application/negative-boundary checks, NEVER Go behavior."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import prepare
import build
from patchlib import apply, ledger, sha, tree_sha

OWN = Path(__file__).resolve().parent
INPUT = OWN.parent / '.spike-inputs/original-inputs/original-inputs'


class PatchBoundaries(unittest.TestCase):
    def setUp(self):
        self.base = {'backend/x.go': b'one\ntwo\nthree\n'}
        self.delta = b'--- a/backend/x.go\n+++ b/backend/x.go\n@@ -1,3 +1,3 @@\n one\n-two\n+changed\n three\n'

    def test_apply_and_inverse(self):
        new = apply(self.base, self.delta)
        self.assertEqual(new['backend/x.go'], b'one\nchanged\nthree\n')
        self.assertEqual(apply(new, self.delta, reverse=True), self.base)

    def test_reapplication_refused(self):
        with self.assertRaises(ValueError):
            apply(apply(self.base, self.delta), self.delta)

    def test_wrong_context_refused(self):
        with self.assertRaises(ValueError):
            apply({'backend/x.go': b'one\nwrong\nthree\n'}, self.delta)

    def test_offset_refused(self):
        with self.assertRaises(ValueError):
            apply({'backend/x.go': b'extra\none\ntwo\nthree\n'}, self.delta)

    def test_wrong_destination_coordinate_refused(self):
        with self.assertRaises(ValueError):
            apply(self.base, self.delta.replace(b'+1,3', b'+2,3'))

    def test_bad_count_refused(self):
        with self.assertRaises(ValueError):
            apply(self.base, self.delta.replace(b'-1,3', b'-1,4'))

    def test_path_escape_refused(self):
        with self.assertRaises(ValueError):
            apply(self.base, self.delta.replace(b'backend/x.go', b'backend/../../escape'))

    def test_new_file_collision_refused(self):
        with self.assertRaises(ValueError):
            apply(self.base, b'--- /dev/null\n+++ b/backend/x.go\n@@ -0,0 +1 @@\n+new\n')


class NormalizationBoundaries(unittest.TestCase):
    def test_refuse_wrong_or_extra_expression_without_mutation(self):
        original = (INPUT / 'cancel-w3/overlay' / build.GAP_NAME).read_bytes()
        for bad in (original.replace(build.GAP_OLD, build.GAP_NEW),
                    original + b'\n' + build.GAP_OLD, original + b'\n'):
            with self.subTest(digest=sha(bad)), self.assertRaises(ValueError):
                build.normalize_gap_test(bad)
        self.assertEqual(sha(original), build.GAP_ORIGINAL_PIN)


class OutputBoundaries(unittest.TestCase):
    def test_refuse_existing_output_without_mutation(self):
        with tempfile.TemporaryDirectory(dir=OWN) as directory:
            root = Path(directory)
            original = root / 'existing'
            original.mkdir()
            (original / 'marker').write_bytes(b'retain')
            with self.assertRaises(ValueError):
                prepare.prepare(root, original)
            self.assertEqual((original / 'marker').read_bytes(), b'retain')

    def test_refuse_dangling_destination_link(self):
        with tempfile.TemporaryDirectory(dir=OWN) as directory:
            root = Path(directory)
            link = root / 'output'
            link.symlink_to(root / 'missing')
            with self.assertRaises(ValueError):
                prepare.prepare(root, link)
            self.assertTrue(link.is_symlink())

    def test_refuse_source_link(self):
        with tempfile.TemporaryDirectory(dir=OWN) as directory:
            root = Path(directory)
            (root / 'backend').mkdir()
            (root / 'backend/link').symlink_to(OWN / 'production.patch')
            with self.assertRaises(ValueError):
                prepare.read_backend(root)

    def test_written_output_round_trip_and_source_unchanged(self):
        # Exercise the real filesystem publication with a tiny package fixture,
        # keeping all disposable bytes inside the owned namespace. Full actual
        # backend reconstruction is independently checked below in memory.
        with tempfile.TemporaryDirectory(dir=OWN) as directory:
            root = Path(directory)
            package = root / 'fixture-workspace/package'
            package.mkdir(parents=True)
            (package / 'manifest.json').write_text('{}\n')
            source = root / 'source'
            (source / 'backend').mkdir(parents=True)
            (source / 'backend/x.go').write_bytes(b'original\n')
            target = {'backend/x.go': b'changed\n', 'backend/new.go': b'new\n'}
            manifest = {'patches': {'production.patch': 'prod', 'regression.patch': 'test'}, 'components': {}}
            output = root / 'output'
            with patch.object(prepare, 'OWN', package), patch.object(prepare, 'reconstruct', return_value=(target, manifest, tree_sha(ledger(target)))):
                receipt = prepare.prepare(source, output)
            self.assertEqual((output / 'backend/x.go').read_bytes(), b'changed\n')
            self.assertEqual((output / 'backend/new.go').read_bytes(), b'new\n')
            self.assertEqual((source / 'backend/x.go').read_bytes(), b'original\n')
            self.assertFalse((source / 'backend/new.go').exists())
            self.assertEqual(receipt['output_tree_sha256'], tree_sha(ledger(target)))


def verify():
    m, hashes = prepare.load_package()
    source, base = prepare.read_backend(INPUT / 'actual-source')
    merged, _, _ = prepare.reconstruct(base, 'combined')
    production, _, _ = prepare.reconstruct(base, 'combined', production_only=True)
    official = dict(base)
    for row in reversed(m['canonical_patches']):
        official = apply(official, (OWN / row['path']).read_bytes(), reverse=True)
    prepare.check_ledger(official, hashes['official'], 'inverse canonical')
    public_result, _, _ = prepare.reconstruct(official, 'official')
    public_production, _, _ = prepare.reconstruct(official, 'official', production_only=True)
    assert public_result == merged and public_production == production
    control = json.loads((OWN / 'interaction-control.json').read_text())
    fault_patch = (OWN / control['patch']).read_bytes()
    assert sha(fault_patch) == control['sha256']
    mutant = apply(merged, fault_patch)
    assert apply(mutant, fault_patch, reverse=True) == merged
    assert {k for k in merged if merged[k] != mutant[k]} == {r['path'] for r in control['files']}
    for row in control['files']:
        assert sha(merged[row['path']]) == row['before_sha256']
        assert sha(mutant[row['path']]) == row['after_sha256']
        result = subprocess.run([str(INPUT / 'gofmt')], input=mutant[row['path']], capture_output=True)
        assert result.returncode == 0 and not result.stderr and result.stdout == mutant[row['path']]
    interaction = 'backend/internal/service/native_stream_merged_interaction_test.go'
    assert merged[interaction] == mutant[interaction] == (OWN / 'native_stream_merged_interaction_test.go').read_bytes()
    assert sha(merged[interaction]) == control['identical_test_sha256']
    for row in m['production'] + m['regression']:
        assert sha(merged[row['path']]) == row['after_sha256']
        assert (sha(base[row['path']]) if row['path'] in base else None) == row['before_sha256']
    unchanged = [name for name in base if base[name] == merged[name]]
    changed = {name for name in base if base[name] != merged[name]}
    assert changed == {r['path'] for r in m['production'] if r['before_sha256'] is not None}
    memory = json.loads((INPUT / 'memory-w2/SOURCE.json').read_text())
    cancellation = json.loads((INPUT / 'cancel-w3/manifest.json').read_text())
    frozen_path = OWN.parent / '.spike-inputs/candidate/sub2api-native-merged/merged-hashes.json'
    supplied_pins = json.loads((OWN.parent / '.spike-inputs/INPUT-HASHES.json').read_bytes())
    assert sha(frozen_path.read_bytes()) == supplied_pins['candidate/sub2api-native-merged/merged-hashes.json']
    frozen_ledger = json.loads(frozen_path.read_bytes())
    assert set(hashes['merged']) == set(frozen_ledger)
    assert sorted(k for k in hashes['merged'] if hashes['merged'][k] != frozen_ledger[k]) == ['backend/internal/service/native_stream_merged_interaction_test.go', 'backend/internal/service/openai_gateway_passthrough.go']
    assert m['patches']['production.patch'] == '16bc1644e564847f0565dffd765af6c7e0c7a70ac5677147d3166e20c90923a5'
    _, actual = prepare.read_backend(OWN.parent / '.spike-inputs/actual-source')
    prepare.check_ledger(actual, frozen_ledger, 'actual W2 merged')
    repaired = apply(actual, (OWN / 'W2-to-W3.patch').read_bytes())
    assert repaired == merged
    assert apply(repaired, (OWN / 'W2-to-W3.patch').read_bytes(), reverse=True) == actual
    drain_control = json.loads((OWN / 'default-drain-control.json').read_bytes())
    drain_patch = (OWN / drain_control['patch']).read_bytes()
    assert sha(drain_patch) == drain_control['sha256']
    old_drain = apply(merged, drain_patch)
    assert old_drain['backend/internal/service/openai_gateway_passthrough.go'] == actual['backend/internal/service/openai_gateway_passthrough.go']
    assert apply(old_drain, drain_patch, reverse=True) == merged
    frozen_tests = 0
    for row in memory['files']:
        if row['kind'] == 'tests':
            assert merged[row['path']] == (INPUT / 'memory-w2' / row['overlay_path']).read_bytes()
            frozen_tests += 1
    for row in cancellation['files']:
        if row['path'].endswith('_test.go'):
            original = (INPUT / 'cancel-w3/overlay' / row['path']).read_bytes()
            if row['path'] == build.GAP_NAME:
                assert merged[row['path']] == build.normalize_gap_test(original)
            else:
                assert merged[row['path']] == original
                frozen_tests += 1
    # Helpers that do not overlap are EXACT reviewed component bytes.
    for name, lane in [('openai_first_output_timeout.go', 'memory-w2/production'),
                       ('native_api_key_cancellation.go', 'cancel-w3/overlay'),
                       ('openai_compact_sse_keepalive.go', 'cancel-w3/overlay')]:
        path = 'backend/internal/service/' + name
        assert merged[path] == (INPUT / lane / path).read_bytes()
    formatter = INPUT / 'gofmt'
    for row in m['production'] + m['regression']:
        data = merged[row['path']]
        result = subprocess.run([str(formatter)], input=data, capture_output=True)
        assert result.returncode == 0 and not result.stderr
        if not row['path'].endswith('/independent_boundary_test.go'):
            assert result.stdout == data
    bad = dict(base)
    bad['backend/go.mod'] += b'\n// wrong source\n'
    try:
        prepare.reconstruct(bad, 'combined')
    except ValueError:
        pass
    else:
        raise AssertionError('modified go.mod was accepted')
    bad = dict(base)
    bad['backend/unreviewed.go'] = b'package unknown\n'
    try:
        prepare.reconstruct(bad, 'combined')
    except ValueError:
        pass
    else:
        raise AssertionError('unexpected source accepted')
    suite = unittest.TestSuite()
    for case in (PatchBoundaries, NormalizationBoundaries, OutputBoundaries):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful()
    if (OWN / 'artifact-hashes.json').exists():
        sealed = json.loads((OWN / 'artifact-hashes.json').read_text())
        for name, row in sealed['files'].items():
            assert sha((OWN / name).read_bytes()) == row['sha256'], ('sealed package changed', name)
    return {'status': 'PASS', 'scope': 'offline package/source/application only',
            'negative_and_output_tests': result.testsRun, 'base_backend_files': len(base),
            'unchanged_backend_files': len(unchanged), 'changed_existing_files': len(changed),
            'production_files': len(m['production']), 'byte_exact_component_test_files': frozen_tests, 'approved_adapted_component_test_files': 1,
            'W2_ledger_difference': sorted(k for k in hashes['merged'] if hashes['merged'][k] != frozen_ledger[k]),
            'historical_native_control': 'byte exact, syntax checked; original unformatted bytes retained',
            'canonical_public_route': 'exact inverse/forward content round-trip; no network authentication',
            'production_only_routes': 'same exact backend result',
            'interaction_RED_fault': 'exact forward/inverse; identical test bytes; runtime RED NOT RUN',
            'source_never_written': str(source), 'production_patch_sha256': m['patches']['production.patch'],
            'regression_patch_sha256': m['patches']['regression.patch'],
            'actual_Go_typecheck_behavior_race': 'NOT RUN', 'W3_newgap_receipt': 'Reviewer-supplied root corrected standalone W3 527 PASS / 0 SKIP; NOT merged',
            'approved_gap_test_sha256': build.GAP_APPROVED_PIN}


if __name__ == '__main__':
    result = verify()
    (OWN / 'evidence/offline-checks.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
