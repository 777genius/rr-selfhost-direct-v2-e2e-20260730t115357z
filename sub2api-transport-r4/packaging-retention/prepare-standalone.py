"""Build runnable owned runtime from exact frozen support plus reviewed six-file overlay."""
from pathlib import Path
import hashlib, json, shutil, subprocess
owned = Path(__file__).resolve().parent
dest = owned / 'runtime'
assert not dest.exists(), 'Runtime already exists; audit it rather than overwrite it'
dest.mkdir()
for name in ['sub2api-regression-lab', 'sub2api-spike']:
    shutil.copytree(owned / 'historical-input/prior-code' / name, dest / name)
for name, row in json.loads((owned / 'changed-loc.json').read_text()).items():
    target = dest / name
    target.chmod(0o644)
    shutil.copyfile(owned / 'overlay' / name, target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == row['result_sha256']
(dest / 'sub2api-transport-r4').mkdir()
shutil.copyfile(owned / 'adapter.mjs', dest / 'sub2api-transport-r4/adapter.mjs')
run = subprocess.run(['node', 'sub2api-regression-lab/run.mjs', '--plan'], cwd=dest, check=True, capture_output=True, text=True)
print(run.stdout, end='')
