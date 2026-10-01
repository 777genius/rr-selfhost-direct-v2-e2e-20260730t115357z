from pathlib import Path
from unittest.mock import patch
import importlib.util, json, shutil, subprocess, tempfile, unittest, os
root=Path.cwd(); own=root/'sub2api-transport-packaging-review'; pkg=root/'.spike-inputs/candidate/sub2api-transport-r4'; helper=root/'.spike-inputs/candidate/sub2api-transport-packaging'; base=root/'.spike-inputs/public-base'
spec=importlib.util.spec_from_file_location('review_provenance',helper/'verify-provenance.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
receipts=[]
class Integrity(unittest.TestCase):
 def test_four_link_types_before_any_history_read_and_real_clis(self):
  for kind in ['root','package-ancestor','higher-ancestor','manifest']:
   with self.subTest(kind=kind),tempfile.TemporaryDirectory(dir=own) as d:
    d=Path(d); pack=d/'real/package';pack.parent.mkdir();shutil.copytree(pkg,pack)
    history=pack/'historical-input';entry=pack
    if kind=='root':
     history.rename(d/'history');history.symlink_to(d/'history',target_is_directory=True)
    elif kind=='package-ancestor':
     (d/'alias').symlink_to(pack,target_is_directory=True);entry=d/'alias'
    elif kind=='higher-ancestor':
     (d/'alias').symlink_to(pack.parent,target_is_directory=True);entry=d/'alias/package'
    else:
     (history/'INPUT-HASHES.json').rename(d/'manifest');(history/'INPUT-HASHES.json').symlink_to(d/'manifest')
    for pathroot in [entry/'historical-input',Path(os.path.relpath(entry/'historical-input',root))]:
     with patch.object(Path,'read_bytes',side_effect=AssertionError('forbidden read')) as read:
      with self.assertRaisesRegex(ValueError,'historical symlink'):v.checked_read(pathroot,'INPUT-HASHES.json')
      read.assert_not_called()
     with patch.object(v.m,'prior_bytes',return_value={}),patch.object(Path,'read_bytes',side_effect=AssertionError('forbidden read')) as read:
      with self.assertRaisesRegex(ValueError,'historical symlink'):v.verify(pathroot.parent,base)
      read.assert_not_called()
    for program in ['verify-provenance.py','audit.py']:
     for location in ['helper','installed']:
      script=(helper if location=='helper' else pkg)/program
      command=['python3',str(script),'--package-root',str(entry),'--base-root',str(base)]
      result=subprocess.run(command,capture_output=True,text=True)
      receipts.append(dict(kind=kind,location=location,program=program,command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
      self.assertNotEqual(result.returncode,0);self.assertIn('historical symlink',result.stderr)
 def test_unsafe_history_names_before_read(self):
  for name in ['../escape','/absolute','candidate/../execution.json','candidate//REPORT.md','candidate\\REPORT.md']:
   with patch.object(Path,'read_bytes',side_effect=AssertionError('forbidden read')) as read:
    with self.assertRaisesRegex(ValueError,'unsafe historical path'):v.checked_read(pkg/'historical-input',name)
    read.assert_not_called()
 def test_unchanged_leaf_and_corruption_controls(self):
  with tempfile.TemporaryDirectory(dir=own) as d:
   pack=Path(d)/'package';shutil.copytree(pkg,pack);history=pack/'historical-input'
   original=history/'execution.json';original.rename(Path(d)/'execution');original.symlink_to(Path(d)/'execution')
   with patch.object(Path,'read_bytes',side_effect=AssertionError('forbidden read')) as read:
    with self.assertRaisesRegex(ValueError,'historical symlink'):v.checked_read(history,'execution.json')
    read.assert_not_called()
   original.unlink();original.write_bytes((Path(d)/'execution').read_bytes()+b'\n')
   with self.assertRaisesRegex(ValueError,'historical input hash'):v.verify(pack,base)
 def test_regular_history_control(self):
  proof=v.verify(pkg,base)
  self.assertEqual(proof,{'integrity':'PASS','provided_files':150,'prior_files':102,'historical':{'FAIL':11,'NOT RUN':9},'effects':686,'history_reexecuted':False,'original_verdict':'REQUESTCHANGES'})
with (own/'evidence/integrity-tests.txt').open('w') as f:
 result=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Integrity))
(own/'evidence/integrity-cli.json').write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'receipts':receipts},indent=2)+'\n')
assert result.wasSuccessful()
print('4 independent integrity tests PASS; 16 actual helper/installed CLI symlink rejections; 16 zero-read assertions')
