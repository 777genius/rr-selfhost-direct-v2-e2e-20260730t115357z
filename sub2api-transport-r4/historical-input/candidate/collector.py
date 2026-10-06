"""Coordinator-only read-only proc/cgroup collector. No Docker, reset, DB or network.
One inspected fresh dedicated Go container/PID per batch. Stops after <=180 seconds. V2 preserves raw RSS/HWM; full5sec tail and exclusive DONE acknowledgment.
Spec is public identity/paths only; never supply private lab.json or deployed auth.
"""
import argparse
import collections
import json
import hashlib
import math
import os
from pathlib import Path
import re
import time

MiB = 1048576
IDENTITY = ('instance', 'engine_pid', 'pid_start_ticks', 'cgroup_path', 'cgroup_device', 'cgroup_inode', 'container_id', 'exe_device', 'exe_inode')

def mono():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC) / 1e6

def start_ticks(text):
    # comm can contain spaces or closing parentheses; field22 follows final ')'.
    return int(text[text.rindex(')') + 2:].split()[19])

def rss_field(text):
    values = []
    for line in text.splitlines():
        if line.startswith('Rss:'):
            parts = line.split()
            if len(parts) != 3 or parts[2] != 'kB' or not parts[1].isdigit():
                raise ValueError('SMAPS_RSS_INVALID')
            values.append(int(parts[1]) * 1024)
    if len(values) != 1:
        raise ValueError('SMAPS_RSS_MISSING_OR_DUPLICATE')
    return values[0]


def map_summary(text):
    # Sum virtual extents, including aliases, not cgroup charges or resident pages.
    # Numeric evidence only; paths are not exported. No between-sample guarantee.
    total, external_candidate, last_end, count = 0, 0, 0, 0
    for line in text.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) < 5:
            raise ValueError('MAPS_INVALID')
        match = re.fullmatch(r'([0-9a-f]+)-([0-9a-f]+)', fields[0])
        if not match or not re.fullmatch(r'[r-][w-][x-][ps]', fields[1]):
            raise ValueError('MAPS_INVALID')
        start, end = [int(x, 16) for x in match.groups()]
        if end <= start or start < last_end:
            raise ValueError('MAPS_INVALID')
        last_end = end
        total += end - start
        # All inode-backed mappings (private too), shared anonymous, named special
        # mappings are conservative candidates for externally charged/alias pages.
        if int(fields[4]) != 0 or fields[1][-1] == 's' or len(fields) == 6:
            external_candidate += end - start
        count += 1
    if not count:
        raise ValueError('MAPS_MISSING')
    return dict(mapped_virtual_extent_bytes=total,
                mapped_external_candidate_extent_bytes=external_candidate,
                maps_count=count, maps_sha256=hashlib.sha256(text.encode()).hexdigest(),
                maps_kind='observed-virtual-extents-not-continuous-bound')


def read_sample(spec, proc_root=Path('/proc'), cg_root=Path('/sys/fs/cgroup')):
    started_ms = mono()
    proc = proc_root / str(spec['engine_pid'])
    if start_ticks((proc / 'stat').read_text()) != spec['pid_start_ticks']:
        raise ValueError('PID_CREATION_CHANGED')
    group = (proc / 'cgroup').read_text().strip()
    if group != '0::' + spec['cgroup_path']:
        raise ValueError('CGROUP_MEMBERSHIP_CHANGED')
    cg = cg_root / spec['cgroup_path'].lstrip('/')
    if any(p.is_dir() for p in cg.iterdir()):
        raise ValueError('NESTED_CGROUP_NOT_SUPPORTED')
    st = cg.stat()
    if (st.st_dev, st.st_ino) != (spec['cgroup_device'], spec['cgroup_inode']):
        raise ValueError('CGROUP_IDENTITY_CHANGED')
    if {int(x) for x in (cg / 'cgroup.procs').read_text().split()} != {spec['engine_pid']}:
        raise ValueError('CGROUP_NOT_SOLE_ENGINE')
    exe = (proc / 'exe').stat()
    if (exe.st_dev, exe.st_ino) != (spec['exe_device'], spec['exe_inode']):
        raise ValueError('EXECUTABLE_CHANGED')
    status = {}
    for line in (proc / 'status').read_text().splitlines():
        name, _, value = line.partition(':')
        if name in ('VmRSS', 'VmHWM'):
            fields = value.split()
            if name in status or len(fields) != 2 or fields[1] != 'kB' or not fields[0].isdigit():
                raise ValueError('RSS_UNIT_INVALID')
            status[name] = int(fields[0]) * 1024
    # Enumerating vanished FDs is incomplete evidence, never silently substituted.
    sockets = sum(os.readlink(p).startswith('socket:') for p in (proc / 'fd').iterdir())
    current = int((cg / 'memory.current').read_text())
    peak = int((cg / 'memory.peak').read_text())  # r only: works on mode0444 kernel6.8
    limit = int((cg / 'memory.max').read_text())
    # These status values are raw asynchronous accounting, not exact high-water bounds.
    if set(status) != {'VmRSS', 'VmHWM'}:
        raise ValueError('RSS_FIELDS_MISSING')
    if min(status.values()) < 0 or min(current, peak, limit) < 0:
        raise ValueError('NEGATIVE_COUNTER')
    if limit != 768 * MiB:
        raise ValueError('CGROUP_LIMIT_INVALID')
    if peak < current:
        raise ValueError('CGROUP_PEAK_BELOW_CURRENT')
    smaps = rss_field((proc / 'smaps_rollup').read_text())
    maps_text = (proc / 'maps').read_text()
    mappings = map_summary(maps_text)
    # Recheck full identity/occupancy after the slower page-table observation.
    if (proc / 'cgroup').read_text().strip() != '0::' + spec['cgroup_path']:
        raise ValueError('CGROUP_MEMBERSHIP_CHANGED')
    after_cg, after_exe = cg.stat(), (proc / 'exe').stat()
    if (after_cg.st_dev, after_cg.st_ino) != (spec['cgroup_device'], spec['cgroup_inode']):
        raise ValueError('CGROUP_IDENTITY_CHANGED')
    if (after_exe.st_dev, after_exe.st_ino) != (spec['exe_device'], spec['exe_inode']):
        raise ValueError('EXECUTABLE_CHANGED')
    if any(p.is_dir() for p in cg.iterdir()) or {int(x) for x in (cg / 'cgroup.procs').read_text().split()} != {spec['engine_pid']}:
        raise ValueError('CGROUP_OCCUPANCY_CHANGED')
    if start_ticks((proc / 'stat').read_text()) != spec['pid_start_ticks']:
        raise ValueError('PID_CREATION_CHANGED')
    finished_ms = mono()
    return {**{k: spec[k] for k in IDENTITY}, 'schema': 'raw-observation-v2', 'collector': 'root-go-pid',
            'clock': 'linux-CLOCK_MONOTONIC', 'batch_id': spec['batch_id'], 'mono_ms': finished_ms,
            'rss_bytes': status['VmRSS'], 'raw_vm_hwm_bytes': status['VmHWM'],
            'rss_kind': 'raw-proc-status-approximate', 'smaps_rollup_rss_bytes': smaps,
            'smaps_kind': 'page-table-walk-observation-not-interval-peak',
            'sample_started_ms': started_ms, 'sample_duration_ms': finished_ms - started_ms,
            **mappings, 'physical_interval_rss_upper_bound_bytes': None,
            'cgroup_current_bytes': current, 'cgroup_peak_bytes': peak, 'cgroup_limit_bytes': limit,
            'sockets': sockets, 'goroutines': None, 'goroutines_source': 'unavailable-instantaneous'}

def write_new(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        out.write(json.dumps(value) + '\n')

def boundary(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:  # canonical save() writes in place
        return None

def collect(spec, output):
    if (any(type(spec.get(k)) is not int or spec[k] <= 0 for k in ('engine_pid', 'pid_start_ticks', 'cgroup_device', 'cgroup_inode', 'exe_device', 'exe_inode')) or
        not isinstance(spec.get('instance'), str) or not spec['instance'] or
        spec.get('fresh_container_inspected') is not True or
        not re.fullmatch('[a-f0-9]{64}', spec['container_id']) or
        not re.fullmatch(r'(memory-(responses|messages)-(8|32|64)-(1|5|20)|soak-(responses|messages))', spec['batch_id']) or
        '..' in Path(spec['cgroup_path']).parts or spec['cgroup_path'] == '/' or
        not spec['cgroup_path'].startswith('/')):
        raise ValueError('FRESH_OWNED_SPEC_REQUIRED')
    created, pid_created = spec['container_created_ms'], spec['pid_created_ms']
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in (created, pid_created)) or not (0 <= created <= pid_created <= mono()):
        raise ValueError('CREATION_ORDER_INVALID')
    output = Path(output)
    if not output.is_dir():
        raise ValueError('EXISTING_OWNED_OUTPUT_REQUIRED')
    ready_path = output / (spec['batch_id'] + '.ready.json')
    data_path = output / (spec['batch_id'] + '.ndjson')
    done_path = output / (spec['batch_id'] + '.done.json')
    if ready_path.exists() or data_path.exists() or done_path.exists():
        raise ValueError('OUTPUT_REUSE_DENIED')
    ring = collections.deque(maxlen=12)
    first = read_sample(spec)
    if first['sample_duration_ms'] > 250:
        raise ValueError('SAMPLING_GAP')
    previous = first
    ready = {**{k: spec[k] for k in IDENTITY}, 'schema': 'raw-observation-v2',
             'fresh_container_inspected': True, 'container_created_ms': created,
             'pid_created_ms': pid_created, 'first_ready_ms': first['mono_ms'],
             'first_sample': first, 'peak_method': 'raw-status-and-smaps-observations-plus-read-only-cgroup-lifetime-peak',
             'peak_scope': 'fresh-lifetime-including-startup-and-preparation'}
    # Create telemetry before releasing ready to coordinator. Exclusive creation.
    fd = os.open(data_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        ring.append(first)
        write_new(ready_path, ready)
        deadline = mono() + 180000
        started = False
        while mono() < deadline:
            tick = mono()
            sample = read_sample(spec)
            if sample['cgroup_peak_bytes'] < previous['cgroup_peak_bytes']:
                raise ValueError('CGROUP_PEAK_REGRESSION')
            if sample['mono_ms'] - previous['mono_ms'] > 250 or sample['sample_started_ms'] - previous['sample_started_ms'] > 250 or sample['sample_duration_ms'] > 250:
                raise ValueError('SAMPLING_GAP')
            previous = sample
            ring.append(sample)
            start = boundary(Path(spec['start_path']))
            end = boundary(Path(spec['end_path']))
            if not started and start is not None:
                if start['id'] != spec['batch_id'] or any(start.get(k) != spec[k] for k in IDENTITY):
                    raise ValueError('START_IDENTITY_MISMATCH')
                if not isinstance(start.get('started_ms'), (int, float)) or isinstance(start['started_ms'], bool) or not math.isfinite(start['started_ms']) or start['started_ms'] > mono():
                    raise ValueError('START_TIME_INVALID')
                prior = [s for s in ring if s['mono_ms'] <= start['started_ms']]
                if not prior or start['started_ms'] - prior[-1]['mono_ms'] > 1000:
                    raise ValueError('BASELINE_MISSING')
                baseline = prior[-1]
                out.write(json.dumps({**baseline, 'phase': 'baseline'}) + '\n')
                started = True
                deadline = min(deadline, start['started_ms'] + 95000)
                last = baseline['mono_ms']
            if started and sample['mono_ms'] > last:
                if end is not None and (end['id'] != spec['batch_id'] or any(end.get(k) != spec[k] for k in IDENTITY)):
                    raise ValueError('END_IDENTITY_MISMATCH')
                if end is not None and (not isinstance(end.get('ended_ms'), (int, float)) or not math.isfinite(end['ended_ms']) or end['ended_ms'] < start['started_ms'] or end['ended_ms'] > mono()):
                    raise ValueError('END_TIME_INVALID')
                quiescent = end is not None and sample['mono_ms'] >= end['ended_ms']
                out.write(json.dumps({**sample, 'phase': 'quiescent' if quiescent else 'active'}) + '\n')
                out.flush()
                last = sample['mono_ms']
                if quiescent and sample['sample_started_ms'] - end['ended_ms'] >= 5000:
                    os.fsync(out.fileno())
                    write_new(done_path, {**{k: spec[k] for k in IDENTITY},
                        'schema': 'raw-observation-v2', 'batch_id': spec['batch_id'], 'status': 'DONE',
                        'ended_ms': end['ended_ms'], 'last_sample_ms': sample['mono_ms'],
                        'full_tail_ms': sample['sample_started_ms'] - end['ended_ms']})
                    return
            time.sleep(max(0, .1 - (mono() - tick) / 1000))
        raise ValueError('BOUNDED_COLLECTION_DEADLINE')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        collect(json.loads(Path(args.spec).read_text()), args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Emit only known safe codes; never exception paths or private contents.
        code = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z_]+', str(error)) else type(error).__name__
        raise SystemExit('COLLECTOR_FAILED_NO_VALID_COMPLETION:' + code)  # no private paths/content

if __name__ == '__main__':
    main()
