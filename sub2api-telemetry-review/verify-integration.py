"""Reconstruct supplied overlay in memory; verify proposed run delta only."""
import difflib
import json
from pathlib import Path
import re
import subprocess
base = Path(__file__).resolve().parent
root = base.parent

def apply_file(original, patch, filename):
    section = patch.split('--- a/' + filename + '\n', 1)[1]
    section = section.split('\n--- a/', 1)[0]
    chunks = re.split(r'^@@[^\n]*\n', section, flags=re.M)[1:]
    for chunk in chunks:
        lines = chunk.splitlines(keepends=True)
        old = ''.join(line[1:] for line in lines if line.startswith((' ', '-')))
        new = ''.join(line[1:] for line in lines if line.startswith((' ', '+')))
        if not old or original.count(old) != 1:
            raise AssertionError('EXACT_UNIQUE_HUNK_REQUIRED')
        original = original.replace(old, new, 1)
    return original

filename = 'sub2api-regression-lab/run.mjs'
overlay = apply_file((root / filename).read_text(),
                     (root / '.spike-inputs/root-overlay/run-integration-proposal.patch').read_text(), filename)
proposed = apply_file(overlay, (base / 'integration-proposal.patch').read_text(), filename)
# Reserve the real tail plus the existing 3sec upstream closure wait within 85sec.
start = proposed.index('async function load(')
end = proposed.index('async function runOne(', start)
load = proposed[start:end].replace('c.deadline - 3000', 'c.deadline - 8000').replace('c.deadline - mono() - 3000', 'c.deadline - mono() - 8000')
proposed = proposed[:start] + load + proposed[end:]
# Rewrite accurate line offsets against the reconstructed public overlay.
(base / 'integration-proposal.patch').write_text(''.join(difflib.unified_diff(
    overlay.splitlines(keepends=True), proposed.splitlines(keepends=True),
    fromfile='a/'+filename, tofile='b/'+filename)))
assert 'await sleep(5000);' in proposed
assert 'raw-observation-v2' in proposed
assert 'exe_device' in proposed and 'exe_inode' in proposed
result = subprocess.run(['node', '--input-type=module', '--check'], input=proposed, text=True, capture_output=True)
if result.returncode:
    raise AssertionError(result.stderr)
(base / 'integration-check.json').write_text(json.dumps(dict(
    kind='in-memory-overlay-and-syntax-check-not-engine-execution',
    exact_overlay_hunks='PASS', exact_review_delta='PASS', proposed_run_syntax='PASS',
    external_execution='NOT RUN'), indent=2)+'\n')
