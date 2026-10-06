"""Strict UTF-8 unified patches: exact coordinates, context, paths and counts."""
import hashlib
import re
from pathlib import PurePosixPath


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not name.startswith('backend/'):
        raise ValueError('unsafe patch path: ' + name)
    return name


def sections(data):
    lines = data.decode('utf-8').splitlines(True)
    result = []
    i = 0
    while i < len(lines):
        while i < len(lines) and lines[i].startswith(('diff --git ', 'new file mode ', 'index ')):
            i += 1
        if not lines[i].startswith('--- '):
            raise ValueError('unexpected patch header')
        old = lines[i][4:].rstrip('\n')
        new = lines[i + 1][4:].rstrip('\n')
        if not lines[i + 1].startswith('+++ b/'):
            raise ValueError('unexpected destination')
        name = safe_path(new[2:])
        if old != '/dev/null' and old != 'a/' + name:
            raise ValueError('rename or deletion unsupported')
        i += 2
        hunks = []
        while i < len(lines) and not lines[i].startswith(('--- ', 'diff --git ')):
            m = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[i])
            if not m:
                raise ValueError('invalid hunk header')
            coords = tuple(int(x) if x is not None else 1 for x in m.groups())
            i += 1
            body = []
            while i < len(lines) and not lines[i].startswith(('@@ ', '--- ', 'diff --git ')):
                if lines[i][:1] not in (' ', '+', '-'):
                    raise ValueError('unsupported patch line')
                body.append(lines[i])
                i += 1
            if sum(x[0] in ' -' for x in body) != coords[1] or sum(x[0] in ' +' for x in body) != coords[3]:
                raise ValueError('hunk count mismatch')
            hunks.append((coords, body))
        result.append((name, old == '/dev/null', hunks))
    if len({x[0] for x in result}) != len(result):
        raise ValueError('duplicate patch file')
    return result


def apply(data, patch, reverse=False):
    """Return new map; never mutate input. Missing/extra context is fatal."""
    output = dict(data)
    for name, created, hunks in sections(patch):
        if created and not reverse:
            if name in data:
                raise ValueError('new file already exists: ' + name)
            before = b''
        else:
            if name not in data:
                raise ValueError('missing original: ' + name)
            before = data[name]
        lines = before.decode('utf-8').splitlines(True)
        merged, cursor = [], 0
        for coords, body in hunks:
            os, oc, ns, nc = coords
            start, count, destination, dest_count = (ns, nc, os, oc) if reverse else coords
            pos = start - (1 if count else 0)
            dest_pos = destination - (1 if dest_count else 0)
            if pos < cursor or pos > len(lines):
                raise ValueError('invalid hunk position: ' + name)
            merged.extend(lines[cursor:pos])
            cursor = pos
            if len(merged) != dest_pos:
                raise ValueError('hunk destination mismatch: ' + name)
            for line in body:
                sign = {'+': '-', '-': '+'}.get(line[0], line[0]) if reverse else line[0]
                if sign in ' -':
                    if cursor >= len(lines) or lines[cursor] != line[1:]:
                        raise ValueError('exact context mismatch: ' + name)
                    cursor += 1
                if sign in ' +':
                    merged.append(line[1:])
        merged.extend(lines[cursor:])
        after = ''.join(merged).encode('utf-8')
        if reverse and created:
            if after:
                raise ValueError('new-file inverse not empty: ' + name)
            del output[name]
        else:
            output[name] = after
    return output


def ledger(data):
    return {k: sha(v) for k, v in sorted(data.items())}


def tree_sha(hashes):
    return sha(''.join(k + '\0' + v + '\n' for k, v in sorted(hashes.items())).encode())
