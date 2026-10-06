"""Offline emitted-config contract for the pinned native logging predicate.
The independent native validator rejects !(stdout || file); no Go/Docker runs.
"""
from pathlib import Path
import hashlib, importlib.util, json, os, sys, tempfile, unittest
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
PACKAGE = Path(os.environ.get('SLOT_LOGGING_PACKAGE', HERE)).resolve()
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('logging_driver', PACKAGE/'root-driver.py')
root = importlib.util.module_from_spec(spec); spec.loader.exec_module(root)

class LoggingPreflight(unittest.TestCase):
    def test_emitted_config_and_environment_pass_native_output_predicate(self):
        # Source: frozen native-config-validator.go:2805; corroborated by the
        # actual W3 diagnostic4 failure. Predicate is independent of producer.
        def native_accepts(stdout, file):
            return not (not stdout and not file)
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            base = Path(t); fixture = base/'fixture'; fixture.mkdir()
            pin = '@sha256:'+'a'*64
            c = dict(synthetic_only=True, engine_image='engine'+pin, node_image='node:24'+pin,
                     postgres_image='postgres:18'+pin, redis_image='redis'+pin,
                     fixture_dir=str(fixture), fixture_attestation_sha256='synthetic')
            data = b'inert'; digest = hashlib.sha256(data).hexdigest()
            f = dict(source='transport-isolated-r4', status='PASS', real_provider_keys_copied=False,
                     images={'postgres':c['postgres_image'], 'redis':c['redis_image']},
                     hashes={n:digest for n in ('snapshot.sql','engine.env','lab.json')})
            e = dict(DATABASE_HOST='postgres', REDIS_HOST='redis', DATABASE_USER='synthetic',
                     DATABASE_DBNAME='synthetic', DATABASE_PASSWORD='synthetic', JWT_SECRET='synthetic')
            image = {'Id':'synthetic', 'Config':{}}
            build = dict(image_id='synthetic', image_config_sha256=hashlib.sha256(b'{}').hexdigest(),
                         image=c['engine_image'], binary_sha256='synthetic', source_manifest_sha256='synthetic')
            d = root.Driver(c, str(base/'output'))
            def private_json(path, expected=None):
                return f if Path(path).name == 'profile-fixture.json' else {'admin_bearer':'synthetic'*8}
            with patch.object(root.os, 'geteuid', return_value=0), \
                 patch.object(root, 'verify_build', return_value=build), \
                 patch.object(root, 'assemble'), \
                 patch.object(root, 'private_json', side_effect=private_json), \
                 patch.object(root, 'private_read', return_value=data), \
                 patch.object(root, 'env_file', return_value=e), \
                 patch.object(d, 'docker', return_value=json.dumps([image]).encode()):
                d.prepare()
            config = json.loads((d.private/'config.yaml').read_text())['log']
            env = dict(line.split('=',1) for line in (d.private/'engine.env').read_text().splitlines())
            with self.subTest(surface='config'):
                self.assertTrue(native_accepts(config['output_to_stdout'], config['output_to_file']),
                                'native rejects both emitted outputs false')
            with self.subTest(surface='environment'):
                self.assertTrue(native_accepts(env['LOG_OUTPUT_TO_STDOUT']=='true', env['LOG_OUTPUT_TO_FILE']=='true'),
                                'native rejects both environment outputs false')
            self.assertEqual((config['output_to_stdout'], config['output_to_file']), (True, False))
            self.assertEqual((env['LOG_OUTPUT_TO_STDOUT'], env['LOG_OUTPUT_TO_FILE']), ('true','false'))
            for name in ('config.yaml','engine.env'):
                self.assertEqual((d.private/name).stat().st_mode & 0o777, 0o600)

if __name__ == '__main__': unittest.main(verbosity=2)
