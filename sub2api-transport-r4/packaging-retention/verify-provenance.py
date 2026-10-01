"""Verify supplied transport-r3 JOB artifact (inherited r2 dirname), review and history."""
from pathlib import Path
import hashlib, json
owned = Path(__file__).resolve().parent
root = owned.parent
supplied = root / '.spike-inputs'
frozen = owned / 'historical-input'
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((supplied / 'INPUT-HASHES.json').read_text())
assert (supplied / 'INPUT-HASHES.json').read_bytes() == (frozen / 'INPUT-HASHES.json').read_bytes()
for name, expected in manifest.items():
    assert digest(supplied / name) == expected, name
    assert digest(frozen / name) == expected, name
for directory, manifest_name in [('candidate', 'output-hashes.json'), ('independent-review', 'artifact-hashes.json')]:
    entries = json.loads((frozen / directory / manifest_name).read_text())
    for name, expected in entries.items():
        assert digest(frozen / directory / name) == expected, directory + '/' + name
reviewed = json.loads((frozen / 'independent-review/evidence/reviewed-source-hashes.json').read_text())
prefix = '.spike-inputs/candidate/sub2api-transport-r2/'
for name, expected in reviewed.items():
    assert name.startswith(prefix), name
    assert digest(frozen / 'candidate' / name[len(prefix):]) == expected, name
execution = json.loads((frozen / 'execution.json').read_text())
historical = {status: sum(r['status'] == status for r in execution['results']) for status in ['FAIL', 'NOT RUN']}
assert historical == {'FAIL': 11, 'NOT RUN': 9}
assert execution['total_upstream_attempts'] == 686
assert sum(r['effects'] for r in execution['results']) == 686
assert all(r['cleanup']['failures'] == 0 and not r['cleanup']['remaining_resources'] for r in execution['results'])
assert json.loads((frozen / 'independent-review/review.json').read_text())['verdict'] == 'REQUESTCHANGES'
legacy = json.loads((frozen / 'candidate/input-hashes.json').read_text())
legacy_differences, legacy_absent = [], []
for name, expected in legacy.items():
    prefix_prior = '.spike-inputs/prior-code/'
    if not name.startswith(prefix_prior): continue
    path = frozen / 'prior-code' / name[len(prefix_prior):]
    if not path.is_file(): legacy_absent.append(name); continue
    actual = digest(path)
    if actual != expected:
        legacy_differences.append({'path':name, 'historical_candidate_manifest_sha256':expected, 'provided_exact_input_sha256':actual})
print(json.dumps({'integrity': 'PASS', 'provided_files': len(manifest), 'reviewed_candidate_files': len(reviewed),
    'candidate_job_identity': 'transport-r3 (user supplied)', 'candidate_artifact_directory': 'sub2api-transport-r2 (inherited)',
    'materialized_candidate': '.spike-inputs/candidate', 'review_identity': 'transport-review-r4',
    'historical_execution_sha256': digest(frozen / 'execution.json'), 'historical': historical,
    'attempts': 686, 'effects': 686, 'original_verdict': 'REQUESTCHANGES',
    'job_identity_independently_queried': False, 'history_reexecuted': False,
    'legacy_candidate_prior_manifest_differences': legacy_differences, 'legacy_candidate_prior_manifest_absent_paths': legacy_absent,
    'repacked_frozen_baseline_authority': 'exact provided INPUT-HASHES.json; legacy candidate prior baseline not reconstructed'}, indent=2))
