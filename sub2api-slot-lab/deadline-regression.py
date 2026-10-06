from pathlib import Path
import importlib.util, os, sys, subprocess, unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent.parent
old=os.environ.get('SLOT_DEADLINE_OLD')=='1'
class Deadlines(unittest.TestCase):
 def module(self,kind):
  package=ROOT/('sub2api-slot-lab' if kind=='slot' else 'sub2api-memory-profile')
  sys.path.insert(0,str(package))
  sys.modules.pop('prepare',None)
  path=(ROOT/'.spike-inputs/candidate/sub2api-slot-lab/root-driver.py' if kind=='slot' else ROOT/'.spike-inputs/profile-w5-root-driver.py') if old else package/'root-driver.py'
  spec=importlib.util.spec_from_file_location('driver_'+kind,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_late_success_actual_command_boundary(self):
  for kind in ('slot','profile'):
   for limit,start,finish in [(60000,0,30001),(30000,29990,30010),(30000,29999.99,30000)]:
    with self.subTest(kind=kind,limit=limit,start=start):
     m=self.module(kind);d=m.Driver.__new__(m.Driver);d.deadline=limit;now=[start];timeouts=[]
     def transport(argv,**kw):timeouts.append(kw['timeout']);now[0]=finish;return subprocess.CompletedProcess(argv,0,b'1\n')
     with patch.object(m,'mono',side_effect=lambda:now[0]),patch.object(m.subprocess,'run',side_effect=transport),patch.object(m.time,'sleep',side_effect=lambda s:now.__setitem__(0,now[0]+s*1000)):
      with self.assertRaisesRegex(ValueError,'PRIVATE_DB_READY_TIMEOUT'):d.wait_postgres('pg')
     self.assertLessEqual(timeouts[0],min(2,(limit-start)/1000))
 def test_requested_near_zero_timeout_not_raised(self):
  for kind in ('slot','profile'):
   m=self.module(kind);d=m.Driver.__new__(m.Driver);d.deadline=100;calls=[]
   with patch.object(m,'mono',return_value=99.99),patch.object(m.subprocess,'run',side_effect=lambda a,**k:calls.append(k['timeout']) or subprocess.CompletedProcess(a,0,b'1')):
    d.cmd(['inert'],timeout=.000001)
   self.assertEqual(calls,[.000001])
 def test_remaining_supervisor_budget_not_raised(self):
  for kind in ('slot','profile'):
   m=self.module(kind);d=m.Driver.__new__(m.Driver);d.deadline=100;calls=[]
   with patch.object(m,'mono',return_value=99.99),patch.object(m.subprocess,'run',side_effect=lambda a,**k:calls.append(k['timeout']) or subprocess.CompletedProcess(a,0,b'1')):d.cmd(['inert'],timeout=2)
   self.assertLessEqual(calls[0],(100-99.99)/1000)
 def test_on_time_success_is_accepted(self):
  for kind in ('slot','profile'):
   m=self.module(kind);d=m.Driver.__new__(m.Driver);d.deadline=30000;now=[29999.99];calls=[]
   def transport(argv,**kw):calls.append(kw['timeout']);now[0]=29999.995;return subprocess.CompletedProcess(argv,0,b'1\n')
   with patch.object(m,'mono',side_effect=lambda:now[0]),patch.object(m.subprocess,'run',side_effect=transport):d.wait_postgres('pg')
   self.assertEqual(len(calls),1)
 def test_expired_no_dispatch(self):
  for kind in ('slot','profile'):
   m=self.module(kind);d=m.Driver.__new__(m.Driver);d.deadline=100
   with patch.object(m,'mono',return_value=100),patch.object(m.subprocess,'run') as run:
    with self.assertRaises(ValueError):d.cmd(['inert'],timeout=2)
    run.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
