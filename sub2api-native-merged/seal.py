#!/usr/bin/env python3
"""Plain <=60-file normal handoff inventory. Does NOT disable/run root scanner."""
import json
from pathlib import Path
from patchlib import sha

OWN = Path(__file__).resolve().parent


def inventory():
    rows = {}
    for p in sorted(OWN.rglob('*')):
        if p.is_symlink():
            raise ValueError('package symlink refused')
        if not p.is_file() or p.name == 'artifact-hashes.json':
            continue
        rel = p.relative_to(OWN).as_posix()
        if any(part.startswith('.') for part in p.relative_to(OWN).parts):
            raise ValueError('hidden package payload refused: ' + rel)
        if p.suffix not in {'.json', '.md', '.py', '.go', '.patch'}:
            raise ValueError('unexpected package format: ' + rel)
        rows[rel] = {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size, 'LOC': len(p.read_bytes().splitlines())}
    if len(rows) + 1 > 60:
        raise ValueError('thin package exceeds 60 files')
    return rows


def main():
    for p in OWN.glob('*.py'):
        compile(p.read_text(), str(p), 'exec')
    data = {'kind': 'plain source/delta handoff', 'inventory_excludes_self': True,
            'files': inventory(), 'scanner': {'required': 'ON', 'normal_handoff_limit': 250,
            'integration_scanner_execution': 'NOT RUN by worker; controller-owned', 'no_encoding_or_archives': True}}
    data['file_count_including_inventory'] = len(data['files']) + 1
    (OWN / 'artifact-hashes.json').write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    observed = inventory()
    assert observed == data['files']
    print(json.dumps({'inventory': 'PASS', 'files': data['file_count_including_inventory'], 'limit': 60, 'scanner': 'remain ON; root gate pending'}))


if __name__ == '__main__':
    main()
