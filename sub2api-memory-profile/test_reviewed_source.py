import copy,json,tempfile,unittest
from pathlib import Path
from contracts import ContractError
from reviewed_source import apply_reviewed,apply_patch,sha_bytes
from launch_contracts import BASE
from analyze import validate_reviewed_manifest
OWN=Path(__file__).resolve().parent
class ReviewedSource(unittest.TestCase):
    def test_exact_reviewed_patch_and_new_go_file_without_git(self):
        name='backend/internal/service/stream.go';old=b'package service\nvar limit = 1\n';new=b'package service\nvar limit = 2\n'
        added='backend/internal/service/stream_test.go';added_bytes=b'package service\n'
        text='--- a/'+name+'\n+++ b/'+name+'\n@@ -1,2 +1,2 @@\n package service\n-var limit = 1\n+var limit = 2\n--- /dev/null\n+++ b/'+added+'\n@@ -0,0 +1 @@\n+package service\n'
        with tempfile.TemporaryDirectory(dir=OWN/'evidence') as td:
            r=Path(td).resolve();legacy=r/'legacy.json';legacy.write_text('{}\n');p=r/'stream.patch';p.write_text(text)
            manifest={'schema':'rrsub2profile-reviewed-v1','base_manifest_sha256':sha_bytes(legacy.read_bytes()),'base_image':BASE,'binary_sha256':'e'*64,
              'patches':[{'path':str(p),'sha256':sha_bytes(p.read_bytes()),'files':{name:{'before_sha256':sha_bytes(old),'after_sha256':sha_bytes(new)},added:{'before_sha256':None,'after_sha256':sha_bytes(added_bytes)}}}]}
            sp=r/'reviewed.json';sp.write_text(json.dumps(manifest));files={name:old};receipt=apply_reviewed(sp,legacy,files)
            self.assertEqual(files,{name:new,added:added_bytes});self.assertEqual(receipt['binary_sha256'],'e'*64)
            for mutation in [lambda s:s.__setitem__('base_image','sha256:'+'0'*64),lambda s:s.__setitem__('base_manifest_sha256','0'*64),lambda s:s.__setitem__('binary_sha256',True),
                lambda s:s['patches'][0].__setitem__('sha256','0'*64),lambda s:s['patches'][0]['files'].pop(added),
                lambda s:s['patches'][0]['files'][name].__setitem__('after_sha256','f'*64),lambda s:s['patches'][0].__setitem__('files',[]),lambda s:s['patches'][0].pop('path')]:
                bad=copy.deepcopy(manifest);mutation(bad);sp.write_text(json.dumps(bad))
                with self.assertRaises(ContractError):apply_reviewed(sp,legacy,{name:old})
            for bad in [text.replace('var limit = 1','var limit = 3'),text.replace('-1,2','-1,8'),text.replace('+++ b/'+name,'+++ b/backend/go.mod'),text.replace(name,'backend/cmd/server/rr_sub2_profile.go')]:
                with self.assertRaises(ContractError):apply_patch({name:old},bad)
    def test_explicit_merged_manifest_keeps_legacy_base_and_exact_source_list(self):
        legacy=json.loads((OWN/'source-manifest.json').read_text());sm=copy.deepcopy(legacy)
        n='backend/internal/service/rr_reviewed_stream_test.go';after='e'*64
        sm['source_after_sha256'][n]=after;sm['source_patch_files']=sorted(sm['source_patch_files']+[n])
        sm['reviewed_source']={'schema':'rrsub2profile-reviewed-v1','base_manifest_sha256':sha_bytes((OWN/'source-manifest.json').read_bytes()),'base_image':BASE,'binary_sha256':'d'*64,'reviewed_manifest_sha256':'c'*64,
          'patches':[{'sha256':'f'*64,'files':{n:{'before_sha256':None,'after_sha256':after}}}]}
        validate_reviewed_manifest(sm)
        for mutate in [lambda s:s.__setitem__('historical',{}),lambda s:s['source_after_sha256'].__setitem__('backend/go.mod','0'*64),lambda s:s['source_patch_files'].append('backend/go.mod'),lambda s:s['operator_after_sha256'].__setitem__('new.mjs','0'*64),lambda s:s['reviewed_source'].__setitem__('base_image','wrong')]:
            bad=copy.deepcopy(sm);mutate(bad)
            with self.assertRaises(ContractError):validate_reviewed_manifest(bad)
