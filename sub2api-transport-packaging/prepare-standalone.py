"""Offline exact public-base reconstruction; no Git writes or network operations."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, io, json, os, subprocess, tarfile, tempfile
HERE = Path(__file__).resolve().parent
SHA = '3004a4b16e03588ee62c0ed7fe2751e0e53300e0'
ROOTS = ('sub2api-regression-lab', 'sub2api-spike')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def load(name):
    return json.loads((HERE / name).read_text())

def safe(name):
    p = PurePosixPath(name)
    if not isinstance(name, str) or p.is_absolute() or '..' in p.parts or str(p) != name or '\\' in name or not p.parts or p.parts[0] not in ROOTS:
        raise ValueError('unsafe path: ' + str(name))
    return name

def read(root, name):
    safe(name)
    root = Path(root)
    if any(p.is_symlink() for p in (root.absolute(), *root.absolute().parents)):
        raise ValueError('symlink root')
    path = root
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink: ' + name)
    if not path.is_file():
        raise ValueError('missing file: ' + name)
    return path.read_bytes()

def verified(data, manifest, label):
    if set(data) != set(manifest):
        raise ValueError(label + ' inventory')
    for name, expected in manifest.items():
        safe(name)
        if digest(data[name]) != expected:
            raise ValueError(label + ' hash: ' + name)
    return data

def base_bytes(base_root=None, repo=None):
    manifest = load('base-hashes.json')
    if base_root is not None:
        data = {safe(n): read(base_root, n) for n in manifest}
    else:
        # Only the constant full SHA is accepted. Never resolve user refs or fetch.
        proc = subprocess.run(['git', '-C', str(repo or HERE.parent), 'archive', '--format=tar', SHA, '--', *ROOTS], check=True, capture_output=True)
        data = {}
        with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as archive:
            for member in archive:
                name = safe(member.name.rstrip('/'))
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError('nonregular archive entry: ' + name)
                if name in data:
                    raise ValueError('duplicate archive entry: ' + name)
                data[name] = archive.extractfile(member).read()
        if not set(manifest).issubset(data):
            raise ValueError('missing archive files')
        data = {n: data[n] for n in manifest}
    return verified(data, manifest, 'base')

def prior_bytes(base_root=None, repo=None):
    data = base_bytes(base_root, repo)  # Verify ALL 102 base hashes before any edits.
    for name, row in load('base-to-prior.delta.json').items():
        safe(name)
        if name not in data or digest(data[name]) != row['base_sha256']:
            raise ValueError('delta base hash: ' + name)
        lines = data[name].decode('utf-8').splitlines(True)
        result, cursor = [], 0
        for edit in row['edits']:
            start, end = edit['start'], edit['end']
            if type(start) is not int or type(end) is not int or not cursor <= start <= end <= len(lines):
                raise ValueError('delta bounds: ' + name)
            if digest(''.join(lines[start:end]).encode()) != edit['old_sha256']:
                raise ValueError('delta context hash: ' + name)
            result.extend(lines[cursor:start]); result.append(edit['new']); cursor = end
        result.extend(lines[cursor:])
        data[name] = ''.join(result).encode('utf-8')
        if digest(data[name]) != row['prior_sha256']:
            raise ValueError('delta result hash: ' + name)
    return verified(data, load('prior-hashes.json'), 'prior')

def runtime_bytes(package, base_root=None, repo=None):
    data = prior_bytes(base_root, repo)
    changes = json.loads((Path(package) / 'changed-loc.json').read_text())
    expected = {'sub2api-regression-lab/' + n for n in ('client.mjs','common.mjs','compose.example.yaml','mock.mjs','run.mjs','wire.mjs')}
    if set(changes) != expected:
        raise ValueError('six-file overlay inventory')
    ledger = load('runtime-hashes.json')
    for name, row in changes.items():
        if digest(data[name]) != row['original_sha256']:
            raise ValueError('overlay base hash: ' + name)
        payload = read(Path(package) / 'overlay', name)
        if digest(payload) != row['result_sha256'] or row['result_sha256'] != ledger[name]:
            raise ValueError('overlay result hash: ' + name)
        data[name] = payload
    adapter = Path(package) / 'adapter.mjs'
    if adapter.is_symlink() or not adapter.is_file():
        raise ValueError('missing/nonregular adapter')
    name = 'sub2api-transport-r4/adapter.mjs'
    data[name] = adapter.read_bytes()
    if set(data) != set(ledger) or any(digest(data[n]) != s for n, s in ledger.items()):
        raise ValueError('103-file runtime hash/inventory')
    return data

def write_new(destination, data):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('output already exists')
    # An external output or a normal build directory is required by package instructions.
    if any(p.is_symlink() for p in (destination.parent.absolute(), *destination.parent.absolute().parents)):
        raise ValueError('symlink output parent')
    parent = destination.parent.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='transport-build-', dir=parent) as temporary:
        stage = Path(temporary) / 'tree'; stage.mkdir()
        for name, payload in data.items():
            if name != 'sub2api-transport-r4/adapter.mjs':
                safe(name)
            target = stage / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        os.rename(stage, parent / destination.name)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package-root', type=Path, default=HERE.parent / 'sub2api-transport-r4')
    p.add_argument('--base-root', type=Path)
    p.add_argument('--repo', type=Path, help='local public sandbox repository; only fixed SHA is archived')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prior-only', action='store_true')
    p.add_argument('--plan', action='store_true')
    args = p.parse_args()
    if args.plan and args.prior_only:
        p.error('--plan requires runtime')
    data = prior_bytes(args.base_root, args.repo) if args.prior_only else runtime_bytes(args.package_root, args.base_root, args.repo)
    write_new(args.output, data)
    if args.plan:
        if args.prior_only:
            raise ValueError('--plan requires runtime')
        subprocess.run(['node', 'sub2api-regression-lab/run.mjs', '--plan'], cwd=args.output, check=True)
    else:
        print(json.dumps({'integrity':'PASS','files':len(data),'output':str(args.output),'base_commit':SHA}, sort_keys=True))

if __name__ == '__main__':
    main()
