"""Execution-based rejection/order/atomic-publication tests using synthetic private inputs."""
import copy,hashlib,json,os,stat,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import analyze,operator_config
from contracts import ContractError
from launch_contracts import BASE
from test_producer import config
OWN=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class ManifestAuthorization(unittest.TestCase):
    def test_selection_before_run_evidence_and_byte_exact_legacy(self):
        with tempfile.TemporaryDirectory(dir=OWN/'evidence') as td:
            root=Path(td);expected=root/'manifest.json';legacy=OWN/'source-manifest.json'
            expected.write_bytes(legacy.read_bytes())
            digest,sm=analyze.expected_source_manifest(expected)
            self.assertEqual(digest,analyze.LEGACY_MANIFEST_SHA256)
            self.assertEqual(analyze.expected_source_manifest(),(digest,sm))
            malformed=[None,False,'',{},[],{'schema':'invalid'}]
            for receipt in ['absent']+malformed:
                bad=copy.deepcopy(sm);bad['historical']['source_sha']='UNREVIEWED';bad['source_after_sha256']={}
                if receipt!='absent':bad['reviewed_source']=receipt
                expected.write_text(json.dumps(bad))
                original=analyze.read
                def guarded_read(path):
                    if path==root/'run.json':raise AssertionError('run evidence read before authorization')
                    return original(path)
                with patch.object(analyze,'read',side_effect=guarded_read):
                    with self.assertRaises(ContractError):analyze.analyze(root,expected)
                output=root/'result.json'
                cp=subprocess.run([sys.executable,str(OWN/'analyze.py'),str(root),'--expected-manifest',str(expected),'--out',str(output)],capture_output=True,timeout=5)
                self.assertNotEqual(cp.returncode,0);self.assertFalse(output.exists())
            expected.write_text(json.dumps(sm)) # Same JSON values, different legacy bytes.
            with self.assertRaises(ContractError):analyze.expected_source_manifest(expected)

    def test_reviewed_acceptance_and_binary_binding_before_source_evidence(self):
        with tempfile.TemporaryDirectory(dir=OWN/'evidence') as td:
            root=Path(td);expected=root/'manifest.json';sm=json.loads((OWN/'source-manifest.json').read_text())
            name='backend/internal/service/future_reviewed.go';sm['source_after_sha256'][name]='e'*64
            sm['source_patch_files']=sorted(sm['source_patch_files']+[name])
            sm['reviewed_source']={'schema':'rrsub2profile-reviewed-v1','base_manifest_sha256':analyze.LEGACY_MANIFEST_SHA256,
              'base_image':BASE,'binary_sha256':'d'*64,'reviewed_manifest_sha256':'c'*64,
              'patches':[{'sha256':'f'*64,'files':{name:{'before_sha256':None,'after_sha256':'e'*64}}}]}
            expected.write_text(json.dumps(sm));self.assertEqual(analyze.expected_source_manifest(expected)[1],sm)
            (root/'stage').mkdir();(root/'stage/source-manifest.json').write_bytes(expected.read_bytes())
            run={'schema':'rrsub2profile-run-v1','status':'COMPLETE','protocol':'responses','no_forced_gc':True,
              'new_image_and_binary':True,'source_manifest_sha256':sha(expected),'build':{'binary_sha256':'a'*64}}
            (root/'run.json').write_text(json.dumps(run))
            with self.assertRaisesRegex(ContractError,'REVIEWED_BINARY_PIN'):analyze.analyze(root,expected)
            with self.assertRaisesRegex(ContractError,'SOURCE_MANIFEST_CHANGED'):analyze.analyze(root)
            for receipt in (None,False,'',{},[],{'schema':'invalid'}):
                bad=copy.deepcopy(sm);bad['reviewed_source']=receipt;expected.write_text(json.dumps(bad))
                with self.assertRaises(ContractError):analyze.expected_source_manifest(expected)

class PrivatePublication(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=OWN/'evidence');self.root=Path(self.temp.name).resolve()
        r=self.root;self.go=r/'go/bin/go';self.go.parent.mkdir(parents=True);self.go.write_bytes(b'SYNTHETIC EXECUTABLE')
        self.cache=r/'cache';self.cache.mkdir();self.collector=r/'collector.py';self.collector.write_text('# synthetic\n')
        self.freeze=r/'freeze'
        for name in ('runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go'):
            p=self.freeze/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// reviewed fixture\n')
        self.c=config(r);self.c['go_binary_sha256']=sha(self.go)
        self.old=r/'old.json';self.old.write_text(json.dumps(self.c));self.out=r/'out.json';self.receipt=r/'receipt.json'
    def tearDown(self):self.temp.cleanup()
    def migrate(self):operator_config.migrate(self.old,self.out,self.receipt,self.freeze,self.cache,self.collector)
    def test_all_config_validation_before_creation(self):
        self.c['synthetic_only']=False;self.old.write_text(json.dumps(self.c))
        with self.assertRaises(ContractError):self.migrate()
        self.assertFalse(self.out.exists());self.assertFalse(self.receipt.exists())
    def test_existing_outputs_and_symlinks_never_overwritten(self):
        for output in (self.out,self.receipt):
            output.write_bytes(b'PREEXISTING')
            with self.assertRaises(ContractError):self.migrate()
            self.assertEqual(output.read_bytes(),b'PREEXISTING');output.unlink()
        self.out.symlink_to(self.old)
        old=self.old.read_bytes()
        with self.assertRaises(ContractError):self.migrate()
        self.assertEqual(self.old.read_bytes(),old);self.assertTrue(self.out.is_symlink());self.assertFalse(self.receipt.exists())
    def test_private_parent_and_ancestor_symlink_cli(self):
        private=self.root/'private';private.mkdir(mode=0o755)
        self.out=private/'out.json'
        with self.assertRaises(ContractError):self.migrate()
        self.assertFalse(self.receipt.exists());private.chmod(0o700)
        link=self.root/'link';link.symlink_to(private,target_is_directory=True);self.out=link/'out.json'
        cp=subprocess.run([sys.executable,str(OWN/'operator_config.py'),'--old-config',str(self.old),'--out',str(self.out),
          '--receipt',str(self.receipt),'--stdlib-freeze',str(self.freeze),'--compilation-cache',str(self.cache),'--collector-source',str(self.collector)],capture_output=True,timeout=5)
        self.assertNotEqual(cp.returncode,0);self.assertFalse((private/'out.json').exists());self.assertFalse(self.receipt.exists())
    def test_check_create_race_respects_competing_output(self):
        original=os.open
        def compete(name,flags,mode=0o777,**kw):
            if name==self.out.name and flags&os.O_CREAT:
                fd=original(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,**kw);os.write(fd,b'COMPETING OUTPUT');os.close(fd)
            return original(name,flags,mode,**kw)
        with patch.object(os,'open',compete),self.assertRaises(FileExistsError):self.migrate()
        self.assertEqual(self.out.read_bytes(),b'COMPETING OUTPUT');self.assertFalse(self.receipt.exists())
    def test_failed_write_rolls_back_owned_files(self):
        original=os.write;calls=[]
        def fail(fd,data):
            calls.append(fd)
            if len(calls)==2:raise OSError('synthetic write failure')
            return original(fd,data)
        with patch.object(os,'write',fail),self.assertRaises(OSError):self.migrate()
        self.assertFalse(self.out.exists());self.assertFalse(self.receipt.exists())

if __name__=='__main__':unittest.main(verbosity=2)
