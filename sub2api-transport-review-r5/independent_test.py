import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parent.parent/'.spike-inputs/candidate/sub2api-transport-r4'
spec=importlib.util.spec_from_file_location('original_contracts',BASE/'collector_test.py')
contracts=importlib.util.module_from_spec(spec);spec.loader.exec_module(contracts)
collector=contracts.collector
class IndependentCollector(unittest.TestCase):
    def test_identity_race_during_smaps_read_cannot_emit_valid_observation(self):
        for mutation in ['pid','occupancy','membership','nested']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                identity,proc,cg=contracts.CollectorContracts().fixture(directory)
                original=Path.read_text
                def read(path,*args,**kwargs):
                    result=original(path,*args,**kwargs)
                    if path.name=='smaps_rollup':
                        if mutation=='pid':(proc/'42/stat').write_text('42 (worker) '+' '.join(['S']+['0']*18+['124']))
                        if mutation=='occupancy':(cg/'test/cgroup.procs').write_text('42\n43\n')
                        if mutation=='membership':(proc/'42/cgroup').write_text('0::/different\n')
                        if mutation=='nested':(cg/'test/child').mkdir()
                    return result
                with patch.object(Path,'read_text',read),self.assertRaises(ValueError):collector.read_sample(identity,proc,cg)
    def test_duplicate_resident_fields_and_missing_metrics_cannot_be_zero(self):
        for target,text in [('status','VmRSS: 1024 kB\nVmRSS: 1024 kB\nVmHWM: 2048 kB\n'),('status','VmHWM: 2048 kB\n'),('smaps_rollup','Rss: 1024 kB\nRss: 1024 kB\n'),('smaps_rollup','Rss: 1 MB\n')]:
            with self.subTest(target=target,text=text),tempfile.TemporaryDirectory() as directory:
                identity,proc,cg=contracts.CollectorContracts().fixture(directory)
                (proc/'42'/target).write_text(text)
                with self.assertRaises(ValueError):collector.read_sample(identity,proc,cg)
    def test_virtual_aliases_remain_extent_observations_without_physical_bound(self):
        maps='1000-3000 r--p 00000000 00:01 1 /fixture\n3000-5000 r--p 00000000 00:01 1 /fixture\n'
        observed=collector.map_summary(maps)
        self.assertEqual(observed['mapped_virtual_extent_bytes'],16384)
        self.assertEqual(observed['mapped_external_candidate_extent_bytes'],16384)
        self.assertEqual(observed['maps_kind'],'observed-virtual-extents-not-continuous-bound')
        self.assertNotIn('physical_interval_rss_upper_bound_bytes',observed)
if __name__=='__main__':unittest.main()
