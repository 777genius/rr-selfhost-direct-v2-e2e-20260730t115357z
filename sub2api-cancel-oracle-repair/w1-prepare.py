"""Exact offline three-file overlay; no complete runtime, Git, Go, or Docker."""
import argparse, hashlib, json, re
from pathlib import Path
OWN = Path(__file__).resolve().parent
INPUT = OWN.parent / '.spike-inputs'
MODULES = ('sub2api-spike/broker.mjs', 'sub2api-regression-lab/run.mjs', 'sub2api-regression-lab/receipts.mjs')
def digest(data): return hashlib.sha256(data).hexdigest()
def apply_delta(files, patch):
    lines = patch.splitlines(keepends=True); i = 0
    while i < len(lines):
        if not lines[i].startswith('--- a/'): raise ValueError('INVALID_PATCH_HEADER')
        name = lines[i][6:].strip(); i += 1
        if name not in files or lines[i] != '+++ b/' + name + '\n': raise ValueError('FOREIGN_PATCH_FILE')
        i += 1
        while i < len(lines) and lines[i].startswith('@@ '):
            m = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n', lines[i])
            if not m: raise ValueError('INVALID_HUNK')
            i += 1; before = []; after = []
            while i < len(lines) and lines[i][0] in ' +-':
                if lines[i].startswith('--- a/'): break
                prefix = lines[i][0]; body = lines[i][1:]
                if prefix in ' -': before.append(body)
                if prefix in ' +': after.append(body)
                i += 1
            if len(before) != int(m[2] or 1) or len(after) != int(m[4] or 1): raise ValueError('HUNK_COUNTS')
            current = files[name].splitlines(keepends=True)
            hits = [j for j in range(len(current)-len(before)+1) if current[j:j+len(before)] == before]
            if len(hits) != 1: raise ValueError('EXACT_HUNK_NOT_UNIQUE: ' + name)
            j = hits[0]; files[name] = ''.join(current[:j] + after + current[j+len(before):])
    return files

def prepare(stage=None, baseline=False):
    pins = json.loads((INPUT/'INPUT-HASHES.json').read_text())
    for name, expected in pins.items():
        if digest((INPUT/name).read_bytes()) != expected: raise ValueError('FROZEN_INPUT_MISMATCH: '+name)
    before = {n:(INPUT/'canonical'/n).read_text() for n in MODULES}
    policy = (INPUT/'fixture-policy.patch').read_text()
    base = apply_delta(dict(before), policy)
    patch = (OWN/'cancel-oracle.patch').read_text()
    changed = dict(base) if baseline else apply_delta(dict(base), patch)
    ledger = {'schema':'cancel-oracle-three-file-delta/v1', 'runtime':'NOT RUN',
      'inputs_verified':len(pins), 'input_manifest_sha256':digest((INPUT/'INPUT-HASHES.json').read_bytes()),
      'delta_sha256':digest(patch.encode()), 'fixture_policy_sha256':digest(policy.encode()),
      'composition':'canonical -> exact trusted boolean fixture-policy -> cancellation oracle delta',
      'modules':{n:{'canonical_sha256':digest(before[n].encode()), 'policy_input_sha256':digest(base[n].encode()),
                    'output_sha256':digest(changed[n].encode())} for n in MODULES},
      'preserved_runtime':{n.removeprefix('canonical/'):v for n,v in pins.items() if n.startswith('canonical/') and n.removeprefix('canonical/') not in MODULES}}
    if stage:
        stage = stage.resolve()
        if stage == INPUT.resolve() or INPUT.resolve() in stage.parents: raise ValueError('INPUT_WRITE_DENIED')
        # Require a new destination. Integration overlays these three files onto its separately owned runtime.
        stage.mkdir(parents=True, exist_ok=False)
        for n, text in changed.items():
            target = stage/n; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(text)
    return changed, ledger
if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--stage',type=Path); ap.add_argument('--baseline',action='store_true');ap.add_argument('--ledger',type=Path)
    args=ap.parse_args(); _, ledger=prepare(args.stage,args.baseline)
    if args.ledger: args.ledger.write_text(json.dumps(ledger,indent=2)+'\n')
    print(json.dumps({'verified':ledger['inputs_verified'],'changed_modules':len(MODULES),'delta_sha256':ledger['delta_sha256'],'runtime':'NOT RUN'}))
