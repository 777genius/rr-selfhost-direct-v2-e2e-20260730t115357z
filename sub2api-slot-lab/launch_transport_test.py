"""Independent subprocess transport regression of emitted create requests.
Exercises launch + generic create + cmd, stops before engine start/inspection.
No root preflight, private inputs, Docker, network, or native process execution.
"""
from pathlib import Path
import importlib.util, json, os, subprocess, sys, tempfile, unittest
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent / '.spike-inputs/candidate/sub2api-slot-lab'
PACKAGE = Path(os.environ.get('SLOT_LAUNCH_PACKAGE', HERE))
CONFIG = {'Entrypoint': ['/app/docker-entrypoint.sh'], 'Cmd': ['/app/sub2api'], 'User': ''}
IMAGE = json.loads((HERE.parent / '.spike-inputs/actual-image.json').read_text())
PIN = IMAGE['repo_digests'][0]

class CapturedEngine(Exception): pass

def capture(package):
    spec = importlib.util.spec_from_file_location('launch_candidate', package / 'root-driver.py')
    root = importlib.util.module_from_spec(spec); spec.loader.exec_module(root)
    with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
        d = root.Driver({'engine_image': PIN, 'postgres_image': 'postgres:18@sha256:'+'a'*64,
                         'redis_image': 'redis@sha256:'+'b'*64, 'node_image': 'node:24@sha256:'+'c'*64}, t)
        d.private = Path(t)/'private'; d.evidence = Path(t)/'evidence'
        d.dbuser = 'synthetic'; d.dbname = 'synthetic'
        d.sql = lambda query: '180000' if query.startswith('SHOW') else '0'
        d.snapshot_bytes = lambda: b'-- inert offline snapshot'
        d.own = lambda name: {}
        requests = []; resolved = None
        real_run = subprocess.run
        def transport(argv, **kw):
            nonlocal resolved
            assert argv[0] == 'docker'
            args = argv[1:]; requests.append(args)
            if args[0] == 'create':
                # Decode the emitted payload across an actual Python process
                # boundary, independently of the producer implementation.
                r = real_run([sys.executable, str(HERE/'launch-transport.py')],
                    input=json.dumps({'argv':args, 'image_config':CONFIG}).encode(),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                assert r.returncode == 0, r.stderr
                decoded = json.loads(r.stdout)
                if decoded['image'] == PIN:
                    resolved = decoded
                    raise CapturedEngine()
            output = b'offline-network-id' if args[:2] == ['network','create'] else (b'1\n' if args[:2] == ['exec',d.owner+'-postgres'] and args[2:4] == ['sh','-c'] and args[4] == 'test "$(cat /proc/1/comm)" = postgres && PGOPTIONS="-c default_transaction_read_only=on" exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"' else b'')
            return subprocess.CompletedProcess(argv, 0, output)
        with patch.object(root.subprocess, 'run', side_effect=transport):
            try: d.launch()
            except CapturedEngine: pass
            else: raise AssertionError('engine boundary not reached')
        return requests, resolved

class NativeLaunch(unittest.TestCase):
    def test_native_process_selection_and_all_other_transport_constraints(self):
        old_requests, old = capture(BASELINE)
        new_requests, new = capture(PACKAGE)
        self.assertEqual(old['process'], ['/app/docker-entrypoint.sh','/app/sub2api'])
        self.assertEqual(old['selected'], ['su-exec','sub2api','/app/sub2api'])
        self.assertTrue(old['requires_setuid_setgid'])
        self.assertEqual(new['process'], ['/app/sub2api'])
        self.assertEqual(new['selected'], ['/app/sub2api'])
        self.assertFalse(new['requires_setuid_setgid'])
        self.assertEqual(new['uid'], '0')
        self.assertEqual(new['image'], PIN)
        opts = new['options']
        self.assertEqual(opts['--user'], ['0:0'])
        self.assertEqual(opts['--cap-drop'], ['ALL'])
        self.assertNotIn('--cap-add', opts)
        self.assertEqual(opts['--security-opt'], ['no-new-privileges'])
        self.assertEqual(opts['--entrypoint'], ['/app/sub2api'])
        self.assertTrue(opts['--mount'][0].endswith('dst=/private/config.yaml,readonly'))
        self.assertNotIn('--publish', opts)
        # Normalize only random owner/output names; every preceding PG/Redis/
        # mock request and every engine option must otherwise remain identical.
        def normalize(rows):
            owner = rows[0][rows[0].index('--label')+1].split('=',1)[1]
            engine = rows[-1]
            private = engine[engine.index('--env-file')+1].removesuffix('/private/engine.env')
            return [[a.replace(owner, 'OWNER').replace(private, 'OUTPUT') for a in row] for row in rows]
        before = normalize(old_requests); after = normalize(new_requests)
        idx = after[-1].index('--entrypoint')
        del after[-1][idx:idx+2]
        self.assertEqual(after, before)

if __name__ == '__main__': unittest.main(verbosity=2)
