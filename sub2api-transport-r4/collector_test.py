"""Synthetic filesystem contracts; no real engine telemetry is produced."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

module = importlib.util.spec_from_file_location('collector', Path(__file__).with_name('collector.py'))
collector = importlib.util.module_from_spec(module)
module.loader.exec_module(collector)

class CollectorContracts(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        proc = root / 'proc' / '42'
        cg = root / 'cg' / 'test'
        proc.mkdir(parents=True); cg.mkdir(parents=True)
        (proc / 'fd').mkdir()
        (proc / 'stat').write_text('42 (comm with ) space) ' + ' '.join(['S'] + ['0'] * 18 + ['123']))
        (proc / 'cgroup').write_text('0::/test\n')
        (proc / 'status').write_text('VmRSS:\t1024 kB\nVmHWM:\t2048 kB\n')
        (proc / 'smaps_rollup').write_text('Rss: 1536 kB\n')
        (proc / 'maps').write_text('1000-2000 r--p 00000000 00:01 1 /unit/file\n2000-4000 rw-p 00000000 00:00 0\n')
        (proc / 'exe').write_bytes(b'unit fixture only')
        (cg / 'cgroup.procs').write_text('42\n')
        for name, n in [('memory.current', 2097152), ('memory.peak', 4194304), ('memory.max', 805306368)]:
            (cg / name).write_text(str(n)); (cg / name).chmod(0o444)
        st, exe = cg.stat(), (proc / 'exe').stat()
        spec = dict(instance='unit-test-only', engine_pid=42, pid_start_ticks=123,
            cgroup_path='/test', cgroup_device=st.st_dev, cgroup_inode=st.st_ino,
            exe_device=exe.st_dev, exe_inode=exe.st_ino, container_id='a'*64, batch_id='memory-responses-8-1')
        return spec, root / 'proc', root / 'cg'

    def test_read_only_peak_and_native_hwm_without_zero_or_reset(self):
        with tempfile.TemporaryDirectory() as root:
            spec, proc, cg = self.fixture(root)
            s = collector.read_sample(spec, proc, cg)
            self.assertEqual(s['rss_bytes'], 1048576)
            self.assertEqual(s['raw_vm_hwm_bytes'], 2097152)
            self.assertEqual(s['cgroup_peak_bytes'], 4194304)
            self.assertIsNone(s['goroutines'])
            self.assertNotIn('peak_reset_ms', s)
            self.assertEqual((cg / 'test/memory.peak').read_text(), '4194304')

    def test_pid_reuse_or_shared_cgroup_or_missing_engine_cannot_be_zero_sample(self):
        with tempfile.TemporaryDirectory() as root:
            spec, proc, cg = self.fixture(root)
            spec['pid_start_ticks'] = 124
            with self.assertRaises(ValueError): collector.read_sample(spec, proc, cg)
            spec['pid_start_ticks'] = 123
            (cg / 'test/cgroup.procs').write_text('42\n43\n')
            with self.assertRaises(ValueError): collector.read_sample(spec, proc, cg)
            (proc / '42/stat').unlink()
            with self.assertRaises(FileNotFoundError): collector.read_sample(spec, proc, cg)

    def test_raw_hwm_below_rss_is_observation_not_corruption(self):
        with tempfile.TemporaryDirectory() as root:
            spec, proc, cg = self.fixture(root)
            (proc / '42/status').write_text('VmRSS: 2048 kB\nVmHWM: 1024 kB\n')
            sample = collector.read_sample(spec, proc, cg)
            self.assertEqual(sample['raw_vm_hwm_bytes'], 1048576)
            self.assertEqual(sample['rss_bytes'], 2097152)
            self.assertIsNone(sample['physical_interval_rss_upper_bound_bytes'])
            self.assertEqual(sample['smaps_rollup_rss_bytes'], 1572864)
            self.assertEqual(sample['mapped_virtual_extent_bytes'], 12288)

    def test_limit_cgroup_counter_executable_and_missing_smaps_stay_strict(self):
        with tempfile.TemporaryDirectory() as root:
            spec, proc, cg = self.fixture(root)
            for file, bad in [('memory.max', 805306367), ('memory.peak', 1)]:
                target = cg / 'test' / file
                original = target.read_text(); target.chmod(0o600); target.write_text(str(bad))
                with self.assertRaises(ValueError): collector.read_sample(spec, proc, cg)
                target.write_text(original)
            spec['exe_inode'] += 1
            with self.assertRaises(ValueError): collector.read_sample(spec, proc, cg)
            spec['exe_inode'] -= 1
            (proc / '42/smaps_rollup').unlink()
            with self.assertRaises(FileNotFoundError): collector.read_sample(spec, proc, cg)

    def test_malformed_units_and_maps_are_not_zero(self):
        for text in ['', 'Rss: 1 bytes', 'Rss: -1 kB', 'Rss: 1 kB\nRss: 2 kB']:
            with self.assertRaises(ValueError): collector.rss_field(text)
        for text in ['', 'invalid', '2000-1000 rw-p 0 00:00 0']:
            with self.assertRaises(ValueError): collector.map_summary(text)

    def test_collect_observes_full_5sec_tail_and_done_and_denies_reuse(self):
        with tempfile.TemporaryDirectory() as root:
            spec, proc, cg = self.fixture(root)
            spec.update(fresh_container_inspected=True, container_created_ms=800, pid_created_ms=900,
                        start_path='unit-start', end_path='unit-end')
            output = Path(root) / 'output'; output.mkdir()
            clock = [1000.0]
            template = collector.read_sample(spec, proc, cg)
            def sample(_):
                return dict(template, mono_ms=clock[0], sample_started_ms=clock[0], sample_duration_ms=0)
            def boundary(path):
                if str(path) == 'unit-start' and clock[0] >= 1100:
                    return dict(spec, id=spec['batch_id'], started_ms=1100)
                if str(path) == 'unit-end' and clock[0] >= 1300:
                    return dict(spec, id=spec['batch_id'], ended_ms=1300)
                return None
            def sleep(seconds):
                clock[0] += seconds * 1000
            with patch.object(collector, 'mono', side_effect=lambda: clock[0]), \
                 patch.object(collector, 'read_sample', side_effect=sample), \
                 patch.object(collector, 'boundary', side_effect=boundary), \
                 patch.object(collector.time, 'sleep', side_effect=sleep):
                collector.collect(spec, output)
                with self.assertRaisesRegex(ValueError, 'OUTPUT_REUSE_DENIED'):
                    collector.collect(spec, output)
            rows = [json.loads(line) for line in (output / (spec['batch_id']+'.ndjson')).read_text().splitlines()]
            self.assertGreaterEqual(rows[-1]['sample_started_ms'] - 1300, 5000)
            self.assertLessEqual(rows[-1]['mono_ms'] - 1300, 5250)
            done = json.loads((output / (spec['batch_id']+'.done.json')).read_text())
            self.assertEqual(done['status'], 'DONE')
            self.assertEqual(done['last_sample_ms'], rows[-1]['mono_ms'])
            self.assertGreaterEqual(done['full_tail_ms'], 5000)
            self.assertEqual(rows[0]['phase'], 'baseline')
            self.assertEqual(rows[-1]['phase'], 'quiescent')
            self.assertTrue(all(b['mono_ms']-a['mono_ms'] <= 250 for a,b in zip(rows, rows[1:])))

    def test_collection_rejects_real_sample_gap_and_cgroup_peak_regression_without_done(self):
        for defect in ('gap', 'cgroup'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as root:
                spec, proc, cg = self.fixture(root)
                spec.update(fresh_container_inspected=True, container_created_ms=800, pid_created_ms=900,
                            start_path='unit-start', end_path='unit-end')
                output=Path(root)/'output'; output.mkdir()
                clock=[1000.0]; calls=[0]
                original=collector.read_sample
                def sample(_):
                    calls[0]+=1
                    if defect=='cgroup' and calls[0]>=3:
                        target=cg/'test/memory.peak'; target.chmod(0o600); target.write_text('3145728')
                    row=original(spec,proc,cg)
                    return dict(row,mono_ms=clock[0],sample_started_ms=clock[0],sample_duration_ms=0)
                def boundary(path):
                    if str(path)=='unit-start' and clock[0]>=1100:
                        return dict(spec,id=spec['batch_id'],started_ms=1100)
                def sleep(seconds): clock[0]+=300 if defect=='gap' else seconds*1000
                with patch.object(collector,'mono',side_effect=lambda:clock[0]), \
                     patch.object(collector,'read_sample',side_effect=sample), \
                     patch.object(collector,'boundary',side_effect=boundary), \
                     patch.object(collector.time,'sleep',side_effect=sleep):
                    with self.assertRaisesRegex(ValueError,'SAMPLING_GAP|CGROUP_PEAK_REGRESSION'):
                        collector.collect(spec,output)
                self.assertFalse((output/(spec['batch_id']+'.done.json')).exists())

    def test_two_filesystem_counter_reads_preserve_raw_linux_regression(self):
        with tempfile.TemporaryDirectory() as root:
            spec,proc,cg=self.fixture(root)
            path=proc/'42/status'
            path.write_text('VmRSS: 200000 kB\nVmHWM: 288140 kB\n')
            first=collector.read_sample(spec,proc,cg)
            path.write_text('VmRSS: 199000 kB\nVmHWM: 285280 kB\n')
            second=collector.read_sample(spec,proc,cg)
            self.assertEqual(first['raw_vm_hwm_bytes'],295055360)
            self.assertEqual(second['raw_vm_hwm_bytes'],292126720)
            self.assertLess(second['rss_bytes'],first['rss_bytes'])
            self.assertNotIn('rss_lifetime_peak_bytes',second)
            self.assertIsNone(second['physical_interval_rss_upper_bound_bytes'])

    def test_comm_parentheses_do_not_corrupt_pid_creation_identity(self):
        self.assertEqual(collector.start_ticks('42 (a ) b) ' + ' '.join(['S'] + ['0']*18 + ['987'])), 987)

if __name__ == '__main__': unittest.main()
