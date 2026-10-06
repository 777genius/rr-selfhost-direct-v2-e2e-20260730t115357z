"""Synthetic filesystem contracts; no real engine telemetry is produced."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

module = importlib.util.spec_from_file_location('collector', Path(__file__).with_name('collector-proposal.py'))
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
            self.assertEqual(s['rss_lifetime_peak_bytes'], 2097152)
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

    def test_comm_parentheses_do_not_corrupt_pid_creation_identity(self):
        self.assertEqual(collector.start_ticks('42 (a ) b) ' + ' '.join(['S'] + ['0']*18 + ['987'])), 987)

if __name__ == '__main__': unittest.main()
