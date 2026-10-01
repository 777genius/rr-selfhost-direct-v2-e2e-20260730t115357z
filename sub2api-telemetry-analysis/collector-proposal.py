"""Coordinator-only read-only proc/cgroup collector. No Docker, reset, DB or network.
One inspected fresh dedicated Go container/PID per batch. Stops after <=180 seconds.
Spec is public identity/paths only; never supply private lab.json or deployed auth.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import re
import time

MiB = 1048576
IDENTITY = ('instance', 'engine_pid', 'pid_start_ticks', 'cgroup_path', 'cgroup_device', 'cgroup_inode', 'container_id')

def mono():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC) / 1e6

def start_ticks(text):
    # comm can contain spaces or closing parentheses; field22 follows final ')'.
    return int(text[text.rindex(')') + 2:].split()[19])

def read_sample(spec, proc_root=Path('/proc'), cg_root=Path('/sys/fs/cgroup')):
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
            if len(fields) != 2 or fields[1] != 'kB':
                raise ValueError('RSS_UNIT_INVALID')
            status[name] = int(fields[0]) * 1024
    # Enumerating vanished FDs is incomplete evidence, never silently substituted.
    sockets = sum(os.readlink(p).startswith('socket:') for p in (proc / 'fd').iterdir())
    current = int((cg / 'memory.current').read_text())
    peak = int((cg / 'memory.peak').read_text())  # r only: works on mode0444 kernel6.8
    limit = int((cg / 'memory.max').read_text())
    if limit != 768 * MiB or status['VmHWM'] < status['VmRSS'] or peak < current:
        raise ValueError('COUNTERS_OR_LIMIT_INVALID')
    if start_ticks((proc / 'stat').read_text()) != spec['pid_start_ticks']:
        raise ValueError('PID_CREATION_CHANGED')
    return {**{k: spec[k] for k in IDENTITY}, 'schema': 'fresh-lifetime-v1', 'collector': 'root-go-pid',
            'clock': 'linux-CLOCK_MONOTONIC', 'batch_id': spec['batch_id'], 'mono_ms': mono(),
            'rss_bytes': status['VmRSS'], 'rss_lifetime_peak_bytes': status['VmHWM'],
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
    if (spec.get('fresh_container_inspected') is not True or
        not re.fullmatch('[a-f0-9]{64}', spec['container_id']) or
        not re.fullmatch(r'(memory-(responses|messages)-(8|32|64)-(1|5|20)|soak-(responses|messages))', spec['batch_id']) or
        '..' in Path(spec['cgroup_path']).parts or spec['cgroup_path'] == '/' or
        not spec['cgroup_path'].startswith('/')):
        raise ValueError('FRESH_OWNED_SPEC_REQUIRED')
    created, pid_created = spec['container_created_ms'], spec['pid_created_ms']
    if not (0 <= created <= pid_created <= mono()):
        raise ValueError('CREATION_ORDER_INVALID')
    output = Path(output)
    if not output.is_dir():
        raise ValueError('EXISTING_OWNED_OUTPUT_REQUIRED')
    ready_path = output / (spec['batch_id'] + '.ready.json')
    data_path = output / (spec['batch_id'] + '.ndjson')
    if ready_path.exists() or data_path.exists():
        raise ValueError('OUTPUT_REUSE_DENIED')
    ring = collections.deque(maxlen=12)
    first = read_sample(spec)
    ready = {**{k: spec[k] for k in IDENTITY}, 'schema': 'fresh-lifetime-v1',
             'fresh_container_inspected': True, 'container_created_ms': created,
             'pid_created_ms': pid_created, 'first_ready_ms': first['mono_ms'],
             'first_sample': first, 'peak_method': 'read-only-lifetime-memory.peak-and-VmHWM'}
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
            ring.append(sample)
            start = boundary(Path(spec['start_path']))
            end = boundary(Path(spec['end_path']))
            if not started and start is not None:
                if start['id'] != spec['batch_id'] or any(start.get(k) != spec[k] for k in IDENTITY):
                    raise ValueError('START_IDENTITY_MISMATCH')
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
                quiescent = end is not None and sample['mono_ms'] >= end['ended_ms']
                out.write(json.dumps({**sample, 'phase': 'quiescent' if quiescent else 'active'}) + '\n')
                out.flush()
                last = sample['mono_ms']
                if quiescent and sample['mono_ms'] - end['ended_ms'] >= 2000:
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
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('COLLECTOR_FAILED_NO_VALID_COMPLETION')  # no private paths/content

if __name__ == '__main__':
    main()
