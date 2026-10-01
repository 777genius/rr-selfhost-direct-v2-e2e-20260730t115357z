"""Independent boundary checks; imports frozen code, no compiler/service execution."""
import hashlib,importlib.util,json,os,pathlib,sys,tempfile,unittest,shutil
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent.parent
OWN=ROOT/'sub2api-memory-profile-review';SOURCE=ROOT/'.spike-inputs/candidate/sub2api-memory-profile'
TEMP=tempfile.TemporaryDirectory(dir=OWN);PRODUCER=pathlib.Path(TEMP.name)/'producer';PRODUCER.mkdir();(PRODUCER/'evidence').mkdir()
for p in SOURCE.iterdir():
 if p.is_file():shutil.copyfile(p,PRODUCER/p.name)
sys.path.insert(0,str(PRODUCER))
import analyze,operator_config,test_w3_regressions as regression
from contracts import ContractError

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class Boundary(unittest.TestCase):
 def test_expected_snapshot_single_read_despite_file_replacement(self):
  with tempfile.TemporaryDirectory(dir=OWN) as td:
   p=pathlib.Path(td)/'manifest.json';legacy=(PRODUCER/'source-manifest.json').read_bytes();p.write_bytes(legacy)
   original=pathlib.Path.read_bytes;reads=[]
   def replace_after_read(path):
    b=original(path)
    if path==p:
     reads.append(path);path.write_text('{"reviewed_source":false}')
    return b
   with patch.object(pathlib.Path,'read_bytes',replace_after_read):digest,manifest=analyze.expected_source_manifest(p)
   self.assertEqual(len(reads),1);self.assertEqual(digest,hashlib.sha256(legacy).hexdigest());self.assertEqual(manifest,json.loads(legacy))
 def test_compiler_pin_mutation_rejected_immediately_before_compile(self):
  original=regression.driver.Driver.build;events=[]
  def mutated(d):
   pathlib.Path(d.c['go_binary']).write_bytes(b'REPLACED EXECUTABLE AFTER PREFLIGHT')
   with self.assertRaisesRegex(ContractError,'TOOLCHAIN_PIN'):original(d)
   events.append('compiler rejected');raise RuntimeError('EXPECTED_MUTATION_STOP')
  with patch.object(regression.driver.Driver,'build',mutated),self.assertRaisesRegex(RuntimeError,'EXPECTED_MUTATION_STOP'):
   regression.Independent().test_preflight_toolchain_query_and_compile_share_sanitized_environment()
  self.assertEqual(events,['compiler rejected'])
 def test_stdlib_pin_mutation_rejected_immediately_before_compile(self):
  original=regression.driver.Driver.build;events=[]
  def mutated(d):
   (d.effective_goroot/'src/runtime/mprof.go').write_bytes(b'REPLACED STDLIB AFTER PREFLIGHT')
   with self.assertRaisesRegex(ContractError,'MATCHING_STDLIB_REQUIRED'):original(d)
   events.append('stdlib rejected');raise RuntimeError('EXPECTED_MUTATION_STOP')
  with patch.object(regression.driver.Driver,'build',mutated),self.assertRaisesRegex(RuntimeError,'EXPECTED_MUTATION_STOP'):
   regression.Independent().test_preflight_toolchain_query_and_compile_share_sanitized_environment()
  self.assertEqual(events,['stdlib rejected'])
 def test_rollback_preserves_replacement_inode(self):
  from test_w3_security import PrivatePublication
  fixture=PrivatePublication();fixture.setUp()
  try:
   original=os.write
   def fail_after_replace(fd,data):
    fixture.out.unlink();fixture.out.write_bytes(b'COMPETING REPLACEMENT')
    raise OSError('EXPECTED_WRITE_STOP')
   with patch.object(os,'write',fail_after_replace),self.assertRaisesRegex(OSError,'EXPECTED_WRITE_STOP'):fixture.migrate()
   self.assertEqual(fixture.out.read_bytes(),b'COMPETING REPLACEMENT');self.assertFalse(fixture.receipt.exists())
  finally:fixture.tearDown()
if __name__=='__main__':unittest.main(verbosity=2)
