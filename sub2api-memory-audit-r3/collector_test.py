"""Exercise the actual root-modified collector with mocked reads only."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

PATH = Path(__file__).resolve().parent.parent / '.spike-inputs/actual-execution/responses/actual-collector.py'
spec = importlib.util.spec_from_file_location('actual_collector', PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

class ActualRetryContracts(unittest.TestCase):
    def fixture(self, root):
        root=Path(root); proc=root/'proc/42'; cg=root/'cg/unit'
        proc.mkdir(parents=True); cg.mkdir(parents=True); (proc/'fd').mkdir()
        (proc/'fd/9').symlink_to('socket:[999]')
        (proc/'stat').write_text('42 (fixture) '+' '.join(['S']+['0']*18+['123']))
        (proc/'cgroup').write_text('0::/unit\n'); (proc/'exe').write_bytes(b'fixture')
        (proc/'status').write_text('VmRSS: 1024 kB\nVmHWM: 2048 kB\n')
        (proc/'smaps_rollup').write_text('Rss: 1536 kB\n')
        (proc/'maps').write_text('1000-2000 rw-p 00000000 00:00 0\n')
        (cg/'cgroup.procs').write_text('42\n')
        for name,value in [('memory.current',2097152),('memory.peak',4194304),('memory.max',805306368)]:
            (cg/name).write_text(str(value))
        group,exe=cg.stat(),(proc/'exe').stat()
        return dict(instance='offline-unit',engine_pid=42,pid_start_ticks=123,cgroup_path='/unit',cgroup_device=group.st_dev,cgroup_inode=group.st_ino,exe_device=exe.st_dev,exe_inode=exe.st_ino,container_id='a'*64,batch_id='memory-responses-8-1'),root/'proc',root/'cg'

    def test_actual_fd_race_restarts_status_and_complete_snapshot(self):
        with tempfile.TemporaryDirectory(dir=PATH.parents[3]/'sub2api-memory-audit-r3') as directory:
            spec,proc,cg=self.fixture(directory)
            readlink=c.os.readlink; attempts=[]
            def raced(path):
                attempts.append(path)
                if len(attempts)==1:
                    (proc/'42/status').write_text('VmRSS: 3072 kB\nVmHWM: 4096 kB\n')
                    raise FileNotFoundError('synthetic vanished fd')
                return readlink(path)
            with patch.object(c.os,'readlink',side_effect=raced): sample=c.read_sample(spec,proc,cg)
            self.assertEqual(len(attempts),2)
            self.assertEqual(sample['rss_bytes'],3072*1024)
            self.assertEqual(sample['sockets'],1)

    def test_actual_fd_race_does_not_retry_away_new_shared_cgroup(self):
        with tempfile.TemporaryDirectory(dir=PATH.parents[3]/'sub2api-memory-audit-r3') as directory:
            spec,proc,cg=self.fixture(directory)
            def raced(path):
                (cg/'unit/cgroup.procs').write_text('42\n43\n')
                raise FileNotFoundError('synthetic vanished fd')
            with patch.object(c.os,'readlink',side_effect=raced):
                with self.assertRaisesRegex(ValueError,'CGROUP_NOT_SOLE_ENGINE'): c.read_sample(spec,proc,cg)

    def test_complete_retry_accounts_all_failed_read_time(self):
        final = dict(mono_ms=140, sample_started_ms=130, sample_duration_ms=10, sockets=7, rss_bytes=777)
        with patch.object(c,'mono',return_value=100), patch.object(c,'_read_sample',side_effect=[FileNotFoundError(),FileNotFoundError(),final]) as read:
            sample = c.read_sample({'unit_fixture':True})
        self.assertEqual(read.call_count,3)
        self.assertEqual(sample['sample_started_ms'],100)
        self.assertEqual(sample['sample_duration_ms'],40)
        self.assertEqual(sample['sockets'],7)
        self.assertEqual(sample['rss_bytes'],777)

    def test_three_failures_never_emit_partial_or_zero_snapshot(self):
        with patch.object(c,'mono',return_value=100), patch.object(c,'_read_sample',side_effect=FileNotFoundError()) as read:
            with self.assertRaises(FileNotFoundError): c.read_sample({})
        self.assertEqual(read.call_count,3)

    def test_identity_limit_or_permission_failures_are_not_retried(self):
        for error in (ValueError('CGROUP_NOT_SOLE_ENGINE'),ValueError('CGROUP_LIMIT_INVALID'),PermissionError()):
            with self.subTest(error=type(error).__name__), patch.object(c,'mono',return_value=100), patch.object(c,'_read_sample',side_effect=error) as read:
                with self.assertRaises(type(error)): c.read_sample({})
                self.assertEqual(read.call_count,1)

    def test_retry_cannot_hide_sampling_duration_overrun(self):
        with patch.object(c,'mono',return_value=100), patch.object(c,'_read_sample',side_effect=[FileNotFoundError(),dict(mono_ms=351,sample_started_ms=350,sample_duration_ms=1)]):
            sample=c.read_sample({})
        self.assertEqual(sample['sample_duration_ms'],251)
        self.assertGreater(sample['sample_duration_ms'],250)

if __name__=='__main__': unittest.main()
