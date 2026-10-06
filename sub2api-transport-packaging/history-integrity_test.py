"""Independent CLI checks against real retained history and actual filesystem symlinks."""
import argparse, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / '.spike-inputs'
PACKAGE = INPUTS / 'candidate/sub2api-transport-r4'
BASE = INPUTS / 'public-base'
HELPER = ROOT / 'sub2api-transport-packaging'
RECEIPTS = []

class HistoryIntegrityTests(unittest.TestCase):
    def cli(self, package, program='verify-provenance.py'):
        command = ['python3', str(HELPER/program), '--package-root', str(package), '--base-root', str(BASE)]
        result = subprocess.run(command, capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
        RECEIPTS.append({'test':self.id(), 'command':command, 'exit':result.returncode, 'stdout':result.stdout, 'stderr':result.stderr})
        return result

    def fixture(self, parent):
        package = Path(parent)/'package'
        shutil.copytree(PACKAGE, package)
        for path in package.rglob('*'):
            if path.is_file(): path.chmod(0o644)
        return package

    def rejects(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('historical symlink', result.stderr)

    def test_regular_history_control(self):
        result = self.cli(PACKAGE)
        self.assertEqual(result.returncode, 0, result.stderr)
        proof = json.loads(result.stdout)
        self.assertEqual(proof['integrity'], 'PASS')
        self.assertEqual((proof['provided_files'], proof['prior_files']), (150, 102))
        self.assertEqual(proof['historical'], {'FAIL':11, 'NOT RUN':9})
        self.assertEqual(proof['effects'], 686)
        self.assertEqual(proof['original_verdict'], 'REQUESTCHANGES')

    def test_historical_root_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            package = self.fixture(d)
            history = package/'historical-input'
            history.rename(Path(d)/'retained-history')
            history.symlink_to(Path(d)/'retained-history', target_is_directory=True)
            self.assertTrue(history.is_symlink())
            self.rejects(self.cli(package))

    def test_ancestor_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            package = self.fixture(d)
            alias = Path(d)/'alias'
            alias.symlink_to(package, target_is_directory=True)
            self.assertTrue(alias.is_symlink())
            self.assertFalse((alias/'historical-input').is_symlink())
            self.rejects(self.cli(alias))

    def test_higher_ancestor_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d)/'real'; parent.mkdir()
            package = self.fixture(parent)
            alias = Path(d)/'alias'; alias.symlink_to(parent, target_is_directory=True)
            self.assertTrue(alias.is_symlink())
            self.rejects(self.cli(alias/package.name))

    def test_input_hashes_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            package = self.fixture(d)
            manifest = package/'historical-input/INPUT-HASHES.json'
            retained = Path(d)/'retained-manifest.json'; manifest.rename(retained)
            manifest.symlink_to(retained)
            self.assertTrue(manifest.is_symlink())
            self.rejects(self.cli(package))

    def test_appended_component_symlink_control(self):
        with tempfile.TemporaryDirectory() as d:
            package = self.fixture(d)
            child = package/'historical-input/candidate'
            child.rename(Path(d)/'retained-candidate')
            child.symlink_to(Path(d)/'retained-candidate', target_is_directory=True)
            self.rejects(self.cli(package))

    def test_corrupted_history_control(self):
        with tempfile.TemporaryDirectory() as d:
            package = self.fixture(d)
            history = package/'historical-input/execution.json'
            history.write_bytes(history.read_bytes()+b'\n')
            result = self.cli(package)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('historical input hash', result.stderr)

    def test_audit_regular_history_control(self):
        result = self.cli(PACKAGE, 'audit.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        proof = json.loads(result.stdout)
        self.assertEqual(proof['original_output_hashes_verified'], 294)
        self.assertEqual(proof['runtime_files_verified'], 103)
        self.assertEqual(proof['new_engine_gates'], 'NOT RUN')
        self.assertEqual(proof['physical_absolute_intersample_bound'], 'NOTPROVEN')

    def test_audit_root_symlink_control(self):
        with tempfile.TemporaryDirectory() as d:
            package = self.fixture(d)
            history = package/'historical-input'
            history.rename(Path(d)/'retained-history')
            history.symlink_to(Path(d)/'retained-history', target_is_directory=True)
            self.rejects(self.cli(package, 'audit.py'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--helper-root', type=Path, default=HELPER)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(); HELPER = args.helper_root.absolute()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HistoryIntegrityTests))
    args.receipt.write_text(json.dumps({'helper_root':str(HELPER), 'tests':result.testsRun, 'failures':len(result.failures), 'errors':len(result.errors), 'receipts':RECEIPTS}, indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
