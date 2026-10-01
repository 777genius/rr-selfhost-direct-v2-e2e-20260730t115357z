"""Apply both exact six-file patches in owned disposable copies; no source mutation."""
from pathlib import Path
import hashlib, json, shutil, subprocess, tempfile, os
owned = Path(__file__).resolve().parent
root = owned.parent
changes = json.loads((owned / 'changed-loc.json').read_text())
expected = {'sub2api-regression-lab/' + n for n in ['client.mjs', 'common.mjs', 'compose.example.yaml', 'mock.mjs', 'run.mjs', 'wire.mjs']}
assert set(changes) == expected
inputs = json.loads((owned / 'input-hashes.json').read_text())
report = {}
for lane, base, patch in [('canonical', root, 'lab-overlay.patch'), ('frozen-root', owned / 'historical-input/prior-code', 'frozen-root-overlay.patch')]:
    with tempfile.TemporaryDirectory(dir=owned, prefix='verify-') as directory:
        dest = Path(directory)
        for name in ['sub2api-regression-lab', 'sub2api-spike']:
            shutil.copytree(owned / 'historical-input/prior-code' / name, dest / name)
        for name, row in changes.items():
            original = base / name
            key = name if lane == 'canonical' else '.spike-inputs/prior-code/' + name
            assert hashlib.sha256(original.read_bytes()).hexdigest() == inputs[key], key
            target = dest / name
            target.chmod(0o644)
            shutil.copyfile(original, target)
        process = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(owned / patch)], cwd=dest, check=True, capture_output=True, text=True)
        assert 'offset' not in process.stdout and 'fuzz' not in process.stdout
        for name, row in changes.items():
            target = dest / name
            assert hashlib.sha256(target.read_bytes()).hexdigest() == row['result_sha256'], name
            if target.suffix == '.mjs':
                subprocess.run(['node', '--check', str(target)], check=True, capture_output=True)
        (dest / 'sub2api-transport-r4').mkdir()
        shutil.copyfile(owned / 'adapter.mjs', dest / 'sub2api-transport-r4/adapter.mjs')
        run = subprocess.run(['node', 'sub2api-regression-lab/run.mjs', '--plan'], cwd=dest, check=True, capture_output=True, text=True)
        plan = json.loads(run.stdout)
        assert {stage: sum(c['stage'] == stage for c in plan['cases']) for stage in ['cancel', 'uncertainty', 'memory', 'soak']} == {'cancel': 12, 'uncertainty': 8, 'memory': 18, 'soak': 2}
        assert [(c['count'], c['streams']) for c in plan['cases'] if c['stage'] == 'soak'] == [(250, 5), (250, 5)]
        assert plan['budget']['max_actual_upstream_attempts'] == 2000
        env = dict(os.environ, RR_LOAD_SOURCE=str(dest / 'sub2api-regression-lab/run.mjs'))
        tests = subprocess.run(['node', '--test', str(owned / 'load.test.mjs')], env=env, check=True, capture_output=True, text=True)
        report[lane] = {'zero_fuzz': True, 'zero_offset': True, 'files': 6, 'result_hashes': 'PASS', 'plan': plan, 'actual_load_tests': tests.stdout}
print(json.dumps(report, indent=2))
