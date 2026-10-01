"""Offline preparation using the public canonical verified runtime helper.
Writes only four reused runtime modules plus the small owned adapter, never Go.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, sys
sys.dont_write_bytecode = True  # Do not create bytecode in the public helper's owned package.
HERE = Path(__file__).resolve().parent
REPO = HERE.parent

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path, value): path.write_text(json.dumps(value, indent=2) + '\n')
def replace_once(text, before, after):
    if text.count(before) != 1: raise ValueError('CANONICAL_DELTA_CONTEXT_MISMATCH')
    return text.replace(before, after)

def assemble(output, base_root=None):
    helper = REPO/'sub2api-transport-packaging/prepare-standalone.py'
    modspec = importlib.util.spec_from_file_location('canonical_transport', helper)
    canonical = importlib.util.module_from_spec(modspec); modspec.loader.exec_module(canonical)
    names = [f'sub2api-regression-lab/{name}' for name in ('common.mjs', 'client.mjs', 'wire.mjs', 'mock.mjs')]
    if base_root is not None:
        all_bytes = canonical.runtime_bytes(REPO/'sub2api-transport-r4', base_root=base_root, repo=REPO)
    else:
        # A linked worktree need not have readable Git history. Use the helper's
        # safe public overlay reader and canonical runtime ledger for exactly
        # the four reused modules; do not claim a 103-file reconstruction.
        ledger = canonical.load('runtime-hashes.json')
        all_bytes = canonical.verified({n: canonical.read(REPO/'sub2api-transport-r4/overlay', n) for n in names},
                                       {n: ledger[n] for n in names}, 'selected public runtime')
    selected = {n: all_bytes[n] for n in names}
    mock = selected['sub2api-regression-lab/mock.mjs'].decode()
    mock = replace_once(mock, 'let total = 0, effects = 0, active = 0, exceeded = false;',
                        'let total = 0, effects = 0, active = 0, exceeded = false;\n  const admissions = new Set(), rejections = [];')
    mock = replace_once(mock, '{ total, effects, active, exceeded, records }',
                        '{ total, effects, active, exceeded, records, rejections }')
    mock = replace_once(mock, 'if (total > 2000)', 'if (total > 248)')
    mock = replace_once(mock, "const rule = rules.get(id) ?? { mode: 'healthy' };", """const rule = rules.get(id);
      // Fail closed: no preparation probes, pending dispatch, replay or unknown ID.
      if (!rule || rule.mode === 'pending' || admissions.has(id) || admissions.size >= 168) {
        exceeded = true; rejections.push({ id, protocol, identity, seen_ms: mono(), reason: 'FORBIDDEN_OR_DUPLICATE_DISPATCH' });
        return send(res, 409, { error: { type: 'slot_lab_admission_denied' } });
      }
      admissions.add(id);""")
    mock = replace_once(mock, "must(['healthy', 'tool', 'memory', 'hold-before', 'hold-after', 'uncertain-before', 'uncertain-after', 'tool-accepted', 'pending'].includes(b.mode), 'RULE_INVALID');",
                        "must(['healthy', 'hold-after', 'pending'].includes(b.mode), 'RULE_INVALID');")
    mock = replace_once(mock, "(rule.mode.startsWith('hold-') ? 10000 : 0)", '0')
    mock = replace_once(mock, 'records.push(r); active++;',
                        """records.push(r); active++;
      r.socket_close_ms = null;
      const onSocketClose = () => { r.socket_close_ms = mono(); };
      req.socket.once('close', onSocketClose);""")
    mock = replace_once(mock, 'r.finished = res.writableFinished; active--;',
                        "r.finished = res.writableFinished; if (r.finished) req.socket.off('close', onSocketClose); active--;")
    # Owned generated delta only: native HTTPS wraps the existing handler.
    mock = replace_once(mock, "import http from 'node:http';", "import https from 'node:https';")
    mock = replace_once(mock, 'export function createMock({ control_token, sentinels }) {',
                        'export function createMock({ control_token, sentinels, tls }) {')
    mock = replace_once(mock, 'const server = http.createServer(async (req, res) => {',
                        'const server = https.createServer(tls, async (req, res) => {')
    mock = replace_once(mock, "new URL(req.url, 'http://mock')", "new URL(req.url, 'https://mock')")
    mock = replace_once(mock, 'const server = createMock(c); server.listen',
                        "const tls = { key: await readFile('/private/tls/server.key'), cert: await readFile('/private/tls/server.crt'), minVersion: 'TLSv1.2' };\n    const server = createMock({ ...c, tls }); server.listen")
    selected['sub2api-regression-lab/mock.mjs'] = mock.encode()
    wire = selected['sub2api-regression-lab/wire.mjs'].decode()
    wire = replace_once(wire, 'export class Inspector {', 'class HistoricalInspector {')
    wire = "import { strictInspector } from '../sub2api-slot-lab/native-sse.mjs';\n" + wire + '\nexport const Inspector = strictInspector(HistoricalInspector);\n'
    selected['sub2api-regression-lab/wire.mjs'] = wire.encode()
    for name in ('contracts.mjs', 'redis.mjs', 'adapter.mjs', 'run.mjs', 'native-sse.mjs'):
        selected['sub2api-slot-lab/'+name] = (HERE/name).read_bytes()
    if output.exists(): raise ValueError('OUTPUT_REUSE_DENIED')
    output.mkdir(mode=0o700, parents=False)
    for name, data in selected.items():
        p = output/name; p.parent.mkdir(exist_ok=True); p.write_bytes(data)
    manifest = {'schema': 'slot-lab-preparation-v1', 'canonical_helper_sha256': sha(helper),
                'canonical_base_commit': canonical.SHA, 'verified_runtime_files': len(all_bytes),
                'selected_runtime_before': {n: hashlib.sha256(all_bytes[n]).hexdigest() for n in selected if n in all_bytes},
                'prepared_files': {n: hashlib.sha256(b).hexdigest() for n,b in selected.items()},
                'product_source_changes': [], 'actual_gateway_redis_docker_tests': 'NOT RUN'}
    write_json(output/'preparation.json', manifest)
    return manifest

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--base-root', type=Path, help='Optional exact canonical public 102-file base; no supplied private fixture needed')
    args=ap.parse_args(); result=assemble(args.output, args.base_root)
    print(json.dumps({'integrity':'PASS','canonical_verified':result['verified_runtime_files'], 'written_modules':len(result['prepared_files'])}))
