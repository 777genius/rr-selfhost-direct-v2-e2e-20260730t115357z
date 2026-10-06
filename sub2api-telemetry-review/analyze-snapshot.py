"""Read only supplied public files; derived review, never an execution receipt."""
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
inputs = base.parent / '.spike-inputs'
manifest = json.loads((inputs / 'INPUT-HASHES.json').read_text())
checks = {name: (inputs / name).is_file() and hashlib.sha256((inputs / name).read_bytes()).hexdigest() == expected
          for name, expected in manifest.items()}
if not all(checks.values()):
    raise SystemExit('SUPPLIED_INPUT_HASH_MISMATCH')
cases = []
for p in sorted((inputs / 'actual').iterdir()):
    t = p / 'telemetry' / (p.name + '.ndjson')
    samples = [json.loads(line) for line in t.read_text().splitlines() if line.strip()] if t.exists() else []
    e = p / 'evidence' / (p.name + '.json')
    receipt = json.loads(e.read_text()) if e.exists() else None
    end_path = p / 'evidence' / (p.name + '.end.json')
    end = json.loads(end_path.read_text()) if end_path.exists() else None
    regressions = []
    for i, (a, b) in enumerate(zip(samples, samples[1:]), 1):
        if b['rss_lifetime_peak_bytes'] < a['rss_lifetime_peak_bytes']:
            regressions.append(dict(line_before=i, line_after=i+1, before_ms=a['mono_ms'], after_ms=b['mono_ms'],
                before_bytes=a['rss_lifetime_peak_bytes'], after_bytes=b['rss_lifetime_peak_bytes'],
                gap_ms=b['mono_ms']-a['mono_ms']))
    cases.append(dict(case=p.name, sample_count=len(samples), receipt_status=receipt.get('status') if receipt else None,
        acceptance_status=receipt.get('acceptance_status') if receipt else None,
        memory_envelope=receipt.get('memory_envelope') if receipt else None,
        collector_error=(p/'collector-error.txt').read_text().strip(), raw_hwm_regressions=regressions,
        hwm_below_rss_lines=[i+1 for i,s in enumerate(samples) if s['rss_lifetime_peak_bytes'] < s['rss_bytes']],
        cgroup_peak_regression_lines=[i+2 for i,(a,b) in enumerate(zip(samples,samples[1:])) if b['cgroup_peak_bytes'] < a['cgroup_peak_bytes']],
        limit_invalid_lines=[i+1 for i,s in enumerate(samples) if s['cgroup_limit_bytes'] != 805306368],
        gap_over_250ms_lines=[i+2 for i,(a,b) in enumerate(zip(samples,samples[1:])) if b['mono_ms']-a['mono_ms'] > 250],
        max_sample_rss_bytes=max((s['rss_bytes'] for s in samples), default=None),
        max_raw_hwm_bytes=max((s['rss_lifetime_peak_bytes'] for s in samples), default=None),
        max_cgroup_peak_bytes=max((s['cgroup_peak_bytes'] for s in samples), default=None),
        baseline_rss_bytes=samples[0]['rss_bytes'] if samples else None,
        last_rss_bytes=samples[-1]['rss_bytes'] if samples else None,
        observed_post_end_ms=samples[-1]['mono_ms']-end['ended_ms'] if samples and end else None,
        ndjson_sha256=hashlib.sha256(t.read_bytes()).hexdigest() if t.exists() else None))
result = dict(kind='derived-public-snapshot-review', external_execution='NOT RUN',
              snapshot_scope='provided files only, not current private batch progress',
              supplied_manifest_entries_verified=len(checks), cases=cases)
(base / 'snapshot-analysis.json').write_text(json.dumps(result, indent=2)+'\n')
