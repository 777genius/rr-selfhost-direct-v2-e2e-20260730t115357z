"""Produce exact reviewable unified diff against unchanged canonical files."""
from pathlib import Path
import difflib, hashlib, json
root = Path(__file__).resolve().parent.parent
owned = Path(__file__).resolve().parent
inputs = json.loads((owned / 'input-hashes.json').read_text())
parts, changes = [], {}
for target in sorted((owned / 'overlay').rglob('*')):
    if not target.is_file(): continue
    name = str(target.relative_to(owned / 'overlay'))
    before = (root / name).read_bytes()
    assert hashlib.sha256(before).hexdigest() == inputs[name], name
    old, new = before.decode().splitlines(True), target.read_text().splitlines(True)
    diff = list(difflib.unified_diff(old, new, fromfile='a/'+name, tofile='b/'+name))
    if not diff: continue
    parts.extend(diff)
    changes[name] = dict(added=sum(s.startswith('+') and not s.startswith('+++') for s in diff),
                         deleted=sum(s.startswith('-') and not s.startswith('---') for s in diff),
                         original_sha256=inputs[name], result_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
(owned / 'lab-overlay.patch').write_text(''.join(parts))
(owned / 'changed-loc.json').write_text(json.dumps(changes,indent=2)+'\n')

frozen_parts=[]
for target in sorted((owned / 'overlay').rglob('*')):
    if not target.is_file(): continue
    name=str(target.relative_to(owned / 'overlay'))
    baseline=root / '.spike-inputs/prior-code' / name
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == inputs[str(baseline.relative_to(root))]
    frozen_parts.extend(difflib.unified_diff(baseline.read_text().splitlines(True),target.read_text().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(owned / 'frozen-root-overlay.patch').write_text(''.join(frozen_parts))
