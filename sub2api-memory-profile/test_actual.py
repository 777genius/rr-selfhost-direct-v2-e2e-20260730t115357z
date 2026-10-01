import copy,json,shutil,tempfile,unittest
from pathlib import Path
from audit_actual import audit,INPUT,OWN
from contracts import ContractError
class ActualNumericAudit(unittest.TestCase):
    def test_actual_runtime_and_independent_slopes(self):
        r=audit();self.assertEqual(r['status'],'DIAGNOSTIC_ONLY')
        for p in r['protocols'].values():self.assertFalse(p['postburst_profile_cycle_eligible']);self.assertLess(max(p['postburst_natural_cycles']),2)
        responses=r['protocols']['responses']['slopes_independently_recomputed']['postwarmup_after_two_bursts']
        messages=r['protocols']['messages']['slopes_independently_recomputed']['postwarmup_after_two_bursts']
        self.assertLess(responses['rss_bytes_per_second'],0);self.assertGreater(messages['rss_bytes_per_second'],0)
        self.assertLess(responses['heap_inuse'],0);self.assertLess(messages['heap_inuse'],0)
        self.assertGreater(messages['sampled_heap_inuse_space_per_second'],0)
    def test_forged_point_trend_and_missing_runtime_scalar_rejected(self):
        with tempfile.TemporaryDirectory(dir=OWN/'evidence') as td:
            r=Path(td)/'actual';shutil.copytree(INPUT/'actual',r)
            for f in r.rglob('*'):
                if f.is_file():f.chmod(0o600)
            p=r/'profile-responses-comparison-w1.json';original=p.read_bytes()
            for mutate in [lambda x:x['checkpoints'][3].__setitem__('heap_inuse',1),lambda x:x['slopes']['postwarmup_after_two_bursts'].__setitem__('rss_bytes_per_second',0),lambda x:x['checkpoints'][3].__setitem__('postburst_profile_cycle_eligible',True)]:
                obj=json.loads(original);mutate(obj);p.write_text(json.dumps(obj))
                with self.assertRaises(ContractError):audit(r)
            p.write_bytes(original)
            rt=r/'profile-responses-fixed-00000009/profiles/runtime.ndjson';rows=rt.read_text().splitlines();first=json.loads(rows[0]);del first['num_gc'];rows[0]=json.dumps(first);rt.write_text('\n'.join(rows)+'\n')
            with self.assertRaises(ContractError):audit(r)
