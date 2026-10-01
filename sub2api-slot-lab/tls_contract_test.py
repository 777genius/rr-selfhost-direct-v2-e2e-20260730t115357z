"""Offline command and mount contracts, no TLS socket or openssl execution."""
from pathlib import Path
import importlib.util, tempfile, unittest
from unittest.mock import patch
from prepare import HERE
spec=importlib.util.spec_from_file_location('tls_driver', HERE/'root-driver.py')
root=importlib.util.module_from_spec(spec); spec.loader.exec_module(root)
class TLS(unittest.TestCase):
    def test_disposable_generation_is_private_and_root_only(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            d=root.Driver({},t); d.private=Path(t); calls=[]
            def record(argv):
                calls.append(argv)
                # Inert transport writes no cryptographic material.
                for flag in ('-keyout','-out'):
                    if flag in argv: Path(argv[argv.index(flag)+1]).write_text('inert')
                return b''
            with patch.object(root.os,'geteuid',return_value=1),patch.object(d,'cmd',side_effect=record):
                with self.assertRaisesRegex(ValueError,'ROOT_ONLY'):d.generate_tls()
            self.assertEqual(calls,[])
            with patch.object(root.os,'geteuid',return_value=0),patch.object(d,'cmd',side_effect=record):d.generate_tls()
            self.assertEqual(calls,root.certificate_commands(d.private/'tls'))
            self.assertEqual((d.private/'tls').stat().st_mode & 0o777,0o700)
            self.assertTrue(all(p.stat().st_mode & 0o777==0o600 for p in (d.private/'tls').iterdir()))
            self.assertIn('basicConstraints=critical,CA:TRUE',calls[0])
            extensions=(HERE/'tls-server.ext').read_text().splitlines()
            self.assertIn('basicConstraints=critical,CA:FALSE',extensions)
            self.assertIn('extendedKeyUsage=serverAuth',extensions)
            self.assertIn('subjectAltName=DNS:mock',extensions)
    def test_emitted_policy_and_native_environment(self):
        import logging_preflight_test as logging
        observed=[]; environments=[]; original=root.dump
        def capture(path,value):
            if Path(path).name in ('config.yaml','lab.json'): observed.append((Path(path).name,value))
            if Path(path).name=='lab.json':
                environments.append(dict(line.split('=',1) for line in (Path(path).parent/'engine.env').read_text().splitlines()))
            return original(path,value)
        with patch.object(logging,'root',root),patch.object(root,'dump',side_effect=capture):
            logging.LoggingPreflight('test_emitted_config_and_environment_pass_native_output_predicate').test_emitted_config_and_environment_pass_native_output_predicate()
        config=dict(observed)['config.yaml']; lab=dict(observed)['lab.json']
        self.assertEqual(config['security']['url_allowlist'],{'enabled':True,'allow_insecure_http':False,'allow_private_hosts':True,'upstream_hosts':['mock']})
        self.assertEqual(lab['mock_url'],'https://mock:8099')
        self.assertEqual(lab['engine_url'],'http://sub2api:8080')
        self.assertEqual(config['gateway']['text_max_body_size'],2097152)
        self.assertEqual(environments[0]['SSL_CERT_FILE'],'/private/tls/ca.crt')
        self.assertNotIn('NODE_TLS_REJECT_UNAUTHORIZED',environments[0])
        self.assertNotIn('SSL_CERT_DIR',environments[0])
if __name__=='__main__': unittest.main(verbosity=2)
