#!/usr/bin/env python3
"""Reproduce the exact backend in a NEW external output. Offline, no Git/Go."""
import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from patchlib import apply, ledger, sha, tree_sha

OWN = Path(__file__).resolve().parent


def load_package():
    m = json.loads((OWN / 'manifest.json').read_text())
    for name, digest in m['patches'].items():
        if sha((OWN / name).read_bytes()) != digest:
            raise ValueError('package patch hash mismatch: ' + name)
    result = {}
    for kind in ('base', 'official', 'merged'):
        h = json.loads((OWN / (kind + '-hashes.json')).read_text())
        if tree_sha(h) != m[kind + '_tree_sha256']:
            raise ValueError('package ledger mismatch: ' + kind)
        result[kind] = h
    return m, result


def read_backend(source):
    source = source.resolve(strict=True)
    backend = source / 'backend'
    if not backend.is_dir() or backend.is_symlink():
        raise ValueError('--source must contain a real backend directory')
    data = {}
    for p in sorted(backend.rglob('*')):
        if p.is_symlink():
            raise ValueError('source symlink refused: ' + str(p.relative_to(source)))
        if p.is_file():
            data[p.relative_to(source).as_posix()] = p.read_bytes()
        elif not p.is_dir():
            raise ValueError('nonregular source entry refused: ' + str(p))
    return source, data


def check_ledger(data, expected, label):
    got = ledger(data)
    mismatch = sorted(k for k in set(got) | set(expected) if got.get(k) != expected.get(k))
    if mismatch:
        raise ValueError(label + ' backend is not exact; mismatches=' + str(len(mismatch)) + ': ' + ', '.join(mismatch[:8]))


def reconstruct(data, source_kind, production_only=False):
    m, hashes = load_package()
    check_ledger(data, hashes['official' if source_kind == 'official' else 'base'], source_kind)
    if source_kind == 'official':
        for r in m['canonical_patches']:
            data = apply(data, (OWN / r['path']).read_bytes())
        check_ledger(data, hashes['base'], 'canonical combined')
    data = apply(data, (OWN / 'production.patch').read_bytes())
    if production_only:
        expected = dict(hashes['base'])
        expected.update({r['path']: r['after_sha256'] for r in m['production']})
    else:
        data = apply(data, (OWN / 'regression.patch').read_bytes())
        expected = hashes['merged']
    check_ledger(data, expected, 'reconstructed')
    return data, m, tree_sha(expected)


def prepare(source, out, source_kind='combined', production_only=False):
    # Refuse overwrite/nesting before loading even a valid source. Existing
    # symlinks (including dangling ones) are never accepted as destinations.
    raw_out = out.absolute()
    if os.path.lexists(raw_out):
        raise ValueError('output already exists: ' + str(raw_out))
    out = raw_out.resolve()
    source = source.resolve(strict=True)
    if out == source or source in out.parents or out == OWN or OWN in out.parents or out == OWN.parent or OWN.parent in out.parents:
        raise ValueError('output must be external to source and workspace')
    if not out.parent.is_dir():
        raise ValueError('output parent must already exist')
    source, original = read_backend(source)
    data, m, output_tree_sha = reconstruct(original, source_kind, production_only)
    # Complete every source/hash/hunk check before creating any output. Reserve
    # the destination exclusively and publish backend only after a verified build.
    out.mkdir(mode=0o700, exist_ok=False)
    staging = None
    try:
        staging = Path(tempfile.mkdtemp(prefix='.native-merged-', dir=out))
        for name, content in data.items():
            p = staging / name
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('xb') as f:
                f.write(content)
            os.chmod(p, 0o644)
        _, observed = read_backend(staging)
        if ledger(observed) != ledger(data):
            raise ValueError('written backend verification failed')
        (staging / 'backend').rename(out / 'backend')
        staging.rmdir()
        staging = None
        receipt = {'source': str(source), 'source_kind': source_kind, 'source_tree_sha256': tree_sha(ledger(original)),
                   'output': str(out), 'output_tree_sha256': output_tree_sha, 'backend_files': len(data),
                   'production_only': production_only, 'production_patch_sha256': m['patches']['production.patch'],
                   'regression_patch_sha256': None if production_only else m['patches']['regression.patch'],
                   'components': m['components'], 'manifest_sha256': sha((OWN / 'manifest.json').read_bytes()),
                   'runtime_verification': 'NOT RUN'}
        (out / 'native-merged-preparation.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        return receipt
    except BaseException:
        # Only remove the new directory reserved by THIS call. Never source or
        # a pre-existing destination. No publication occurs on a hash mismatch.
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Root containing exact backend/')
    parser.add_argument('--source-kind', choices=['combined', 'official'], default='combined')
    parser.add_argument('--out', type=Path, required=True, help='NEW external output, e.g. /tmp/native-merged-green')
    parser.add_argument('--production-only', action='store_true')
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.out, args.source_kind, args.production_only)
    except (ValueError, OSError) as e:
        parser.exit(1, str(e) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
