"""Same boundary contract against frozen/new root driver; inert public inputs only."""
from pathlib import Path
import hashlib, importlib.util, json, os, sys, tempfile, unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
PACKAGE=Path(os.environ.get('SLOT_CONTRACT_PACKAGE',HERE)).resolve()
sys.path.insert(0,str(PACKAGE))
spec=importlib.util.spec_from_file_location('tested_driver',PACKAGE/'root-driver.py')
driver=importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data,mode=0o600):
    p.write_text(data); p.chmod(mode); return p
class Boundary(unittest.TestCase):
    def test_private_rejects_symlink_ancestor(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            p=Path(t); (p/'real').mkdir(); write(p/'real/inert','{}'); (p/'alias').symlink_to(p/'real')
            with self.assertRaises(ValueError): driver.private_file(str(p/'alias/inert'))
    def test_private_exact_0600(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            p=write(Path(t)/'inert','{}'); self.assertEqual(driver.private_file(str(p)),p)
            p.chmod(0o700)
            with self.assertRaises(ValueError): driver.private_file(str(p))
    def test_descriptor_read_does_not_reopen_replaced_leaf(self):
        if not hasattr(driver,'private_json'): self.skipTest('new safe-reader regression only')
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            p=write(Path(t)/'inert.json','{"original":true}'); expected=sha(p)
            original_open=driver.os.open
            def swapped(path,*args,**kw):
                fd=original_open(path,*args,**kw)
                if path == p.name:
                    p.unlink(); write(p,'{"replacement":true}')
                return fd
            with patch.object(driver.os,'open',side_effect=swapped):
                self.assertEqual(driver.private_json(str(p),expected),{'original':True})
    def test_final_symlink_and_nonregular_file_are_denied(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            p=Path(t); write(p/'inert','{}'); (p/'link').symlink_to(p/'inert')
            with self.assertRaises(ValueError): driver.private_file(str(p/'link'))
            if hasattr(driver,'private_read'):
                os.mkfifo(p/'pipe',0o600)
                with self.assertRaises(ValueError): driver.private_file(str(p/'pipe'))
    def test_historical_empty_build_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            p=Path(t); pins=json.loads((PACKAGE/'build-manifest.json').read_text())
            empty=write(p/'empty.patch',''); manifest=write(p/'source.json','{}')
            components={}
            for name,entry in pins['components'].items():
                source=HERE.parent/entry['public_path'] if entry.get('public_path') else empty
                components[name]={'path':str(source),'sha256':sha(source)}
            image='old@'+pins['supplied_native_probe_image_id']
            receipt={'upstream_commit':pins['upstream_commit'],'image':image,'components':components,
              'source_manifest_path':str(manifest),'source_manifest_sha256':sha(manifest),
              'binary_sha256':pins['supplied_native_probe_binary_sha256'],'image_config_sha256':'a'*64,
              'api_key_slots':'stats-only','trusted_cancel_flag':'native_api_key_cancel_on_disconnect'}
            path=write(p/'build.json',json.dumps(receipt))
            with self.assertRaises(ValueError): driver.verify_build({'engine_image':image,'build_attestation':str(path),'build_attestation_sha256':sha(path)})
if __name__=='__main__': unittest.main(verbosity=2)
