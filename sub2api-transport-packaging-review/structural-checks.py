from pathlib import Path
import importlib.util, io, json, os, subprocess, tarfile, tempfile, unittest
from unittest.mock import patch
root=Path.cwd();own=root/'sub2api-transport-packaging-review';helper=root/'.spike-inputs/candidate/sub2api-transport-packaging';base=root/'.spike-inputs/public-base';pkg=root/'.spike-inputs/candidate/sub2api-transport-r4'
spec=importlib.util.spec_from_file_location('prepare',helper/'prepare-standalone.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Structural(unittest.TestCase):
 def test_actual_overlay_inventory(self):
  actual={str(p.relative_to(pkg/'overlay')) for p in (pkg/'overlay').rglob('*') if p.is_file()}
  self.assertEqual(actual,set(json.loads((pkg/'changed-loc.json').read_text())))
 def test_no_symlinks_in_supplied_package_and_base(self):
  for tree in [pkg,helper,base]: self.assertFalse(any(p.is_symlink() for p in tree.rglob('*')))
 def test_archive_traversal_and_hardlink_rejected(self):
  for kind in ['traversal','hardlink']:
   buf=io.BytesIO()
   with tarfile.open(fileobj=buf,mode='w') as t:
    i=tarfile.TarInfo('../escape' if kind=='traversal' else 'sub2api-spike/broker.mjs')
    if kind=='hardlink':i.type=tarfile.LNKTYPE;i.linkname='sub2api-spike/evidence.mjs'
    t.addfile(i)
   with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=buf.getvalue())):
    with self.assertRaises(ValueError):m.base_bytes(repo=root)
 def test_unknown_revision_argument_rejected(self):
  p=subprocess.run(['python3',str(helper/'prepare-standalone.py'),'--revision','HEAD','--output','unused'],capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0);self.assertIn('unrecognized arguments',p.stderr)
 def test_base_root_parent_symlink_rejected(self):
  with tempfile.TemporaryDirectory(dir=own) as d:
   link=Path(d)/'linked';link.symlink_to(base,target_is_directory=True)
   with self.assertRaisesRegex(ValueError,'symlink root'):m.base_bytes(link)
with (own/'evidence/structural-tests.txt').open('w') as log:
 result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Structural))
assert result.wasSuccessful()
print('5 structural tests PASS')
