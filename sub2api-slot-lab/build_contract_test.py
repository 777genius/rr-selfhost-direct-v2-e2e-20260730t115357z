"""Offline receipt schema and exact-source bindings using inert synthetic pins.
Production component pins remain fixed; these inputs cannot authorize root use.
"""
from pathlib import Path
import copy, importlib.util, json, tempfile, unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('gate',HERE/'build-gate.py'); gate=importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
def save(path,value):
    path.write_text(json.dumps(value)); return gate.digest(path.read_bytes())
class Build(unittest.TestCase):
    def setup_receipt(self,p):
        self.expected={}; components={}
        for k in ['native','probe','cancellation_w3','memory_w2']:
            path=p/(k+'.patch'); path.write_text('public inert component '+k)
            h=gate.digest(path.read_bytes()); self.expected[k]=h; components[k]={'path':str(path),'sha256':h}
        self.pins={'upstream_commit':'a'*40,'components':{k:{'sha256':v} for k,v in self.expected.items()},
          'supplied_native_probe_binary_sha256':'e'*64,'supplied_native_probe_image_id':'sha256:'+'f'*64}
        source={'backend/go.mod':'a'*64,'backend/file.go':'b'*64}; base={**source,'backend/file.go':'c'*64}
        patch=p/'merged.patch'; patch.write_text('diff --git a/backend/file.go b/backend/file.go\n--- a/backend/file.go\n+++ b/backend/file.go\n@@ -1 +1 @@\n-before\n+after\n')
        self.m={'schema':'slot-reviewed-merged-source-v1','review_status':'APPROVED','inventory_scope':'full-build-context',
          'upstream_commit':'a'*40,'component_provenance':self.expected,'base_files':base,'merged_files':source,
          'production_changes':{'backend/file.go':{'before_sha256':'c'*64,'after_sha256':'b'*64}},
          'production_patch_sha256':gate.digest(patch.read_bytes()),'source_fingerprint_sha256':gate.fingerprint(source)}
        self.c={'engine_image':'inert@sha256:'+'1'*64,'production_patch':str(patch),'production_patch_sha256':self.m['production_patch_sha256'],
          'reviewed_merged_manifest':str(p/'manifest.json'),'build_attestation':str(p/'receipt.json')}
        self.b={'schema':'slot-root-actual-image-build-v1','status':'BUILT','trust_model':'external-root-build-receipt','build_id':'inert-build-1',
          'components':components,'component_provenance':self.expected,'upstream_commit':'a'*40,'image':self.c['engine_image'],
          'image_id':'sha256:'+'2'*64,'binary_sha256':'3'*64,'image_config_sha256':'4'*64,
          'production_patch_sha256':self.m['production_patch_sha256'],'source_fingerprint_sha256':self.m['source_fingerprint_sha256'],
          'build_input_source_fingerprint_sha256':self.m['source_fingerprint_sha256'],
          'api_key_slots':'stats-only','trusted_cancel_flag':'native_api_key_cancel_on_disconnect'}
    def verify(self):
        # Independently expected byte pins provided by this inert test fixture.
        self.c['reviewed_merged_manifest_sha256']=save(Path(self.c['reviewed_merged_manifest']),self.m)
        self.b['source_manifest_sha256']=self.c['reviewed_merged_manifest_sha256']
        self.c['build_attestation_sha256']=save(Path(self.c['build_attestation']),self.b)
        return gate.verify(self.c,self.pins,lambda p:Path(p).read_bytes())
    def test_complete_inert_schema_accepts_and_mismatched_actual_build_rejects(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            self.setup_receipt(Path(t)); self.assertEqual(self.verify()['build_id'],'inert-build-1')
            original=copy.deepcopy(self.b)
            for field,value in [('schema',None),('build_id',''),('components',{}),('component_provenance',{}),
                ('build_input_source_fingerprint_sha256','0'*64),('production_patch_sha256','0'*64),
                ('source_fingerprint_sha256','0'*64),('binary_sha256','e'*64),('image_id','sha256:'+'f'*64)]:
                with self.subTest(field=field):
                    self.b=copy.deepcopy(original); self.b[field]=value
                    with self.assertRaises(ValueError): self.verify()
    def test_empty_unreviewed_missing_maps_and_source_patch_disagreement_reject(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            self.setup_receipt(Path(t)); original=copy.deepcopy(self.m)
            for field,value in [('base_files',{}),('merged_files',{}),('production_changes',{}),('review_status','UNREVIEWED'),
                ('component_provenance',{}),('production_patch_sha256','0'*64),('source_fingerprint_sha256','0'*64)]:
                with self.subTest(field=field):
                    self.m=copy.deepcopy(original); self.m[field]=value
                    with self.assertRaises(ValueError): self.verify()
    def test_external_pin_is_required_and_rejects_changed_manifest_bytes(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            self.setup_receipt(Path(t)); self.verify()
            Path(self.c['reviewed_merged_manifest']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'EXTERNAL_ROOT_BYTE_BINDING'): gate.verify(self.c,self.pins,lambda p:Path(p).read_bytes())
            self.c.pop('production_patch_sha256')
            with self.assertRaises(ValueError): gate.verify(self.c,self.pins,lambda p:Path(p).read_bytes())
if __name__=='__main__': unittest.main(verbosity=2)
