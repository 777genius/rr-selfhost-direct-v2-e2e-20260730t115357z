"""Offline frozen-input audit; never reads host proc, auth, or external services."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
INPUT = ROOT / '.spike-inputs'
MIB = 1048576

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    manifest = json.loads((INPUT / 'INPUT-HASHES.json').read_text())
    mismatches = [name for name, expected in manifest.items()
                  if not (INPUT / name).is_file() or sha(INPUT / name) != expected]
    assert not mismatches, mismatches
    cases = []
    for directory in sorted((INPUT / 'actual-execution').glob('*/*')):
        if not (directory / 'case.json').is_file():
            continue
        case = json.loads((directory / 'case.json').read_text())
        done = json.loads((directory / 'telemetry.done.json').read_text())
        rows = [json.loads(line) for line in (directory / 'telemetry.ndjson').read_text().splitlines()]
        boundary = case['telemetry_boundary']
        base = rows[0]
        end = done['ended_ms']
        endpoint = [r for r in rows if r['phase'] == 'quiescent' and r['mono_ms'] <= end + 5000][-1]
        identities = ('instance', 'engine_pid', 'pid_start_ticks', 'cgroup_path', 'cgroup_device', 'cgroup_inode', 'container_id', 'exe_device', 'exe_inode')
        assert all(all(row[k] == boundary[k] for k in identities) for row in rows)
        assert all(done[k] == boundary[k] for k in identities)
        assert done['full_tail_ms'] >= 5000
        assert done['last_sample_ms'] == rows[-1]['mono_ms']
        assert rows[-1]['sample_started_ms'] - end == done['full_tail_ms']
        assert all(abs(r['mono_ms'] - r['sample_started_ms'] - r['sample_duration_ms']) < .001 for r in rows)
        assert all(r['sample_duration_ms'] <= 250 for r in rows)
        assert all(b['mono_ms'] - a['mono_ms'] <= 250 for a,b in zip(rows, rows[1:]))
        assert all(b['sample_started_ms'] - a['sample_started_ms'] <= 250 for a,b in zip(rows, rows[1:]))
        assert all(b['cgroup_peak_bytes'] >= a['cgroup_peak_bytes'] for a,b in zip(rows, rows[1:]))
        assert all(r['cgroup_limit_bytes'] == 768*MIB and r['goroutines'] is None and r['physical_interval_rss_upper_bound_bytes'] is None for r in rows)
        n = boundary['streams']
        volume = int(case['id'].split('-')[-2]) * MIB
        assert case['functional_status'] == 'PASS'
        assert case['downstream']['requests'] == case['downstream']['successful'] == n
        assert case['downstream']['bytes'] == volume*n
        assert 1.9*MIB <= case['downstream']['max_frame_bytes'] < 2*MIB
        assert len(case['upstream']) == n
        assert all(r['bytes'] == volume and r['effects'] == 1 and r['finished'] and r['identity'] == case['protocol'] and r['close_ms'] is not None for r in case['upstream'])
        envelope = case['memory_envelope']
        assert envelope['baseline_raw_vm_rss_bytes'] == base['rss_bytes']
        assert envelope['quiescent_raw_vm_rss_bytes'] == endpoint['rss_bytes']
        assert envelope['baseline_smaps_rollup_rss_bytes'] == base['smaps_rollup_rss_bytes']
        assert envelope['quiescent_smaps_rollup_rss_bytes'] == endpoint['smaps_rollup_rss_bytes']
        observed_exceeded = any(max(r[k] for r in rows)>512*MIB or max(r[k] for r in rows)-base[k]>(128+16*n)*MIB for k in ('rss_bytes','smaps_rollup_rss_bytes'))
        residual = {k: endpoint[k]-base[k] for k in ('rss_bytes','smaps_rollup_rss_bytes')}
        cases.append(dict(id=case['id'], streams=n, functional=case['functional_status'], empirical=envelope['empirical_qualified_status'], physical=envelope['physical_interval_rss_status'], reason=envelope['reason'], samples=len(rows), baseline_rss_bytes=base['rss_bytes'], final_rss_bytes=endpoint['rss_bytes'], residual_bytes=residual, sampled_peak_bytes=max(r['smaps_rollup_rss_bytes'] for r in rows), observed_envelope_exceeded=observed_exceeded, endpoint_after_end_ms=endpoint['mono_ms']-end, full_tail_ms=done['full_tail_ms'], max_duration_ms=max(r['sample_duration_ms'] for r in rows), max_gap_ms=max(b['mono_ms']-a['mono_ms'] for a,b in zip(rows,rows[1:])), baseline_sockets=base['sockets'], final_sockets=endpoint['sockets'], active_at_boundary=case.get('active_at_boundary'), cleanup=case['cleanup'], completed_requests=n, streamed_bytes=volume*n))
    files = {str(p.relative_to(ROOT)):sha(p) for p in INPUT.rglob('*') if p.is_file()}
    for name in ('sub2api-spike/evidence.mjs','sub2api-spike/run-client.mjs','sub2api-spike/evidence.test.mjs','sub2api-evidence-r2/client-contract.test.mjs','sub2api-evidence-r2/numeric-jsonl-fixture.json','gateway-spike/evidence.mjs','sub2api-spike/fixture/wallet.mjs'):
        files[name] = sha(ROOT/name)
    (OUT/'input-hashes.json').write_text(json.dumps(files,indent=2)+'\n')
    result = dict(input_manifest_sha256=sha(INPUT/'INPUT-HASHES.json'), manifest_entries_verified=len(manifest), manifest_mismatches=mismatches, frozen_completed_cases=len(cases), missing=['memory-responses-64-20','memory-messages-64-20','soak-responses','soak-messages'], cases=cases, totals=dict(completed_requests=sum(r['completed_requests'] for r in cases), streamed_bytes=sum(r['streamed_bytes'] for r in cases)), limits='Offline public receipt replay; no actual engine/runtime, repeated bursts, pprof, live heap, slots or pending cancellation evidence')
    (OUT/'snapshot-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}))

if __name__ == '__main__':
    main()
