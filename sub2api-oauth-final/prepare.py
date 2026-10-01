#!/usr/bin/env python3
"""Offline exact-byte preparation; no Git, Go, network or service execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(tree):
    return digest(b''.join(p.encode() + b'\0' + digest(tree[p]).encode() + b'\n'
                           for p in sorted(tree)))


def read_tree(root):
    require(root.is_dir() and not root.is_symlink(), 'source must be a real directory')
    tree = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d != '.git')
        for name in directories + files:
            require(not (Path(directory) / name).is_symlink(), 'source symlinks are unsupported')
        for name in sorted(files):
            if name == '.git':
                continue
            path = Path(directory) / name
            require(path.is_file(), 'source special files are unsupported')
            tree[path.relative_to(root).as_posix()] = path.read_bytes()
    return tree


def path_name(header, prefix):
    name = header.rstrip('\n')
    require(name.startswith(prefix), 'invalid patch path prefix')
    name = name[len(prefix):]
    parts = PurePosixPath(name).parts
    require(parts and parts[0] == 'backend' and '..' not in parts and '\\' not in name,
            'unsafe or out-of-scope patch path')
    require(str(PurePosixPath(name)) == name, 'noncanonical patch path')
    return name


def apply_exact(tree, patch):
    """Require every hunk at its declared line, with exact context and counts."""
    lines = patch.read_bytes().decode('utf-8').splitlines(keepends=True)
    cursor = 0
    touched = set()
    while cursor < len(lines):
        if lines[cursor].startswith('diff --git '):
            headers = lines[cursor].rstrip('\n').split(' ')
            require(len(headers) == 4, 'invalid diff metadata')
            declared = path_name(headers[2] + '\n', 'a/')
            require(path_name(headers[3] + '\n', 'b/') == declared, 'metadata rename unsupported')
            cursor += 1
            require(cursor < len(lines) and lines[cursor] == 'new file mode 100644\n', 'unsupported file mode metadata')
            cursor += 1
            require(cursor + 1 < len(lines) and lines[cursor] == '--- /dev/null\n'
                    and lines[cursor + 1] == '+++ b/' + declared + '\n', 'metadata path mismatch')
        old_header = lines[cursor]
        require(old_header.startswith('--- '), 'unexpected patch text')
        require(cursor + 1 < len(lines) and lines[cursor + 1].startswith('+++ '), 'missing new path')
        new_path = path_name(lines[cursor + 1][4:], 'b/')
        require(new_path not in touched, 'duplicate patch path')
        touched.add(new_path)
        is_new = old_header == '--- /dev/null\n'
        if is_new:
            require(new_path not in tree, 'new file already exists: ' + new_path)
            source = []
        else:
            require(path_name(old_header[4:], 'a/') == new_path, 'rename unsupported')
            require(new_path in tree, 'missing patch input: ' + new_path)
            source = tree[new_path].decode('utf-8').splitlines(keepends=True)
        result, old_cursor, hunks = [], 0, 0
        cursor += 2
        while cursor < len(lines) and lines[cursor].startswith('@@ '):
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[cursor])
            require(match is not None, 'invalid hunk header')
            old_start, old_count, new_start, new_count = (
                int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            offset = max(old_start - 1, 0)
            require(old_cursor <= offset <= len(source), 'hunk offset outside input')
            result.extend(source[old_cursor:offset])
            old_cursor = offset
            require(len(result) == max(new_start - 1, 0), 'new hunk offset mismatch')
            consumed = produced = 0
            cursor += 1
            while consumed < old_count or produced < new_count:
                require(cursor < len(lines), 'truncated hunk')
                line = lines[cursor]
                cursor += 1
                require(line and line[0] in ' +-' and line.endswith('\n'), 'unsupported hunk line')
                marker, content = line[0], line[1:]
                if marker in ' -':
                    require(old_cursor < len(source) and source[old_cursor] == content,
                            'exact context mismatch: ' + new_path)
                    old_cursor += 1
                    consumed += 1
                if marker in ' +':
                    result.append(content)
                    produced += 1
                require(consumed <= old_count and produced <= new_count, 'hunk count overflow')
            require((consumed, produced) == (old_count, new_count), 'hunk count mismatch')
            hunks += 1
        require(hunks > 0, 'patch file has no hunks')
        result.extend(source[old_cursor:])
        tree[new_path] = ''.join(result).encode('utf-8')
    require(touched, 'empty patch')
    return touched


def verify_files(tree, records, label):
    for path, expected in records.items():
        require(path in tree and digest(tree[path]) == expected, label + ' hash mismatch: ' + path)


def prepare(upstream, gofmt):
    manifest = json.loads((PACKAGE / 'source-manifest.json').read_text())
    tree = read_tree(upstream)
    require(set(tree) == set(manifest['upstream_files']), 'upstream file set mismatch')
    verify_files(tree, manifest['upstream_files'], 'upstream')
    require(fingerprint(tree) == manifest['upstream_tree_sha256'], 'upstream tree mismatch')
    for stage in manifest['stages']:
        patch = PACKAGE / stage['patch']
        require(digest(patch.read_bytes()) == stage['sha256'], 'patch hash mismatch: ' + stage['patch'])
        for path, expected in stage['before_hashes'].items():
            if expected is None:
                require(path not in tree, 'unexpected preexisting patch file: ' + path)
            else:
                verify_files(tree, {path: expected}, 'patch input')
        touched = apply_exact(tree, patch)
        require(touched == set(stage['after_hashes']), 'patch path set mismatch')
        verify_files(tree, stage['after_hashes'], stage['patch'])
    verify_files(tree, manifest['final_files'], 'final source')
    backend = {p: data for p, data in tree.items() if p.startswith('backend/')}
    require(fingerprint(backend) == manifest['candidate_backend']['sha256'], 'complete final backend mismatch')
    require(len(backend) == manifest['candidate_backend']['file_count'], 'final backend count mismatch')
    require(gofmt.is_file() and not gofmt.is_symlink(), 'standalone gofmt must be a regular file')
    require(digest(gofmt.read_bytes()) == manifest['gofmt_sha256'], 'standalone gofmt hash mismatch')
    for path in manifest['changed_go_paths']:
        result = subprocess.run([str(gofmt.resolve())], input=tree[path], capture_output=True, check=False)
        require(result.returncode == 0 and result.stdout == tree[path], 'gofmt parse/format mismatch: ' + path)
    return tree, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--gofmt', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='verify all bytes in memory; create no source files')
    mode.add_argument('--output', type=Path, help='create a new source directory; never overwrite')
    args = parser.parse_args()
    if args.output is not None:
        require(not os.path.lexists(args.output), 'output already exists; refusing overwrite')
        output = args.output.resolve()
        source = args.upstream.resolve()
        require(not output.is_relative_to(source) and not source.is_relative_to(output), 'output overlaps upstream')
        require(not output.is_relative_to(PACKAGE), 'output must be outside the reusable package')
    tree, manifest = prepare(args.upstream, args.gofmt)
    if args.output is not None:
        args.output.mkdir(parents=False, exist_ok=False)
        try:
            for name, data in sorted(tree.items()):
                target = args.output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(data)
            actual = read_tree(args.output)
            require(actual == tree, 'written output differs from verified reconstruction')
            # Preserve existing upstream executable/read permissions after byte verification.
            for name in set(tree) & set(manifest['upstream_files']):
                (args.output / name).chmod((args.upstream / name).stat().st_mode & 0o777)
        except BaseException:
            shutil.rmtree(args.output)
            raise
    print(json.dumps({'result': 'PASS', 'scope': 'offline exact bytes and standalone gofmt only',
                      'mode': 'check' if args.check else 'prepare', 'fuzz': 0, 'offset': 0,
                      'production_files': 41, 'final_paths_verified': len(manifest['final_files']),
                      'gofmt_files': len(manifest['changed_go_paths']),
                      'backend_sha256': manifest['candidate_backend']['sha256'],
                      'fullsource_patch_sha256': manifest['patches']['fullsource.patch'],
                      'compile': 'not executed by offline preparation; supplied actual compile verified separately', 'production_GO': False}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'result': 'FAIL', 'reason': str(error)}), file=sys.stderr)
        sys.exit(1)
