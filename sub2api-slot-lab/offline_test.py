"""Offline tests; Docker calls are inert injected command recordings only."""
from pathlib import Path
import importlib.util, json, tempfile, unittest
from unittest.mock import patch
from prepare import HERE, assemble
spec=importlib.util.spec_from_file_location('root_driver',HERE/'root-driver.py')
root=importlib.util.module_from_spec(spec); spec.loader.exec_module(root)

class IsolationTests(unittest.TestCase):
    def test_exact_small_canonical_assembly_is_reproducible_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            a=assemble(Path(t)/'a'); b=assemble(Path(t)/'b')
            self.assertEqual(a['prepared_files'],b['prepared_files'])
            self.assertEqual(a['verified_runtime_files'],4)
            self.assertEqual(len(a['prepared_files']),9)
            self.assertEqual(a['product_source_changes'],[])
            with self.assertRaisesRegex(ValueError,'OUTPUT_REUSE_DENIED'): assemble(Path(t)/'a')

    def test_create_intent_is_durable_before_docker_and_no_ports_or_restart(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            d=root.Driver({},Path(t)); calls=[]
            def docker(*args,**kw):
                calls.append(args)
                if args[0]=='create':
                    j=json.loads((Path(t)/'cleanup-journal.json').read_text())
                    self.assertIn(d.owner+'-engine',j['containers'])
                return b''
            d.docker=docker; d.own=lambda _:{}
            d.create('engine','synthetic@sha256:'+'a'*64,['--memory','768m'])
            create=calls[0]
            self.assertIn('--pull=never',create); self.assertIn(root.LABEL+'='+d.owner,create)
            self.assertIn('--log-driver',create); self.assertIn('none',create)
            self.assertNotIn('-p',create); self.assertNotIn('--publish',create)
            self.assertEqual(calls[1],('start',d.owner+'-engine'))

    def test_cleanup_foreign_container_or_network_is_never_removed(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            d=root.Driver({},Path(t)); name=d.owner+'-foreign'; d.containers=[name]; calls=[]
            d.inspect=lambda *a,**k:{'Id':'foreign-id','Config':{'Labels':{root.LABEL:'another-owner'}}}
            def docker(*args,**kw):
                calls.append(args)
                if args[:2]==('network','inspect'): return json.dumps([{'Id':'foreign-net','Labels':{root.LABEL:'another-owner'}}]).encode()
                if args[:2]==('network','ls'): return (d.net+'\n').encode()
                if args[:2]==('container','ls'): return (name+'\n').encode()
                self.fail('Unexpected remove or other command')
            d.docker=docker; d.cleanup()
            self.assertFalse(d.cleaned); self.assertEqual(d.containers,[name]); self.assertEqual(len(d.cleanup_errors),2)
            self.assertTrue(all('rm' not in c for c in calls))

    def test_ambiguous_create_is_inspected_and_removed_only_if_owned(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            d=root.Driver({},Path(t)); name=d.owner+'-engine'; d.containers=[name]; calls=[]
            d.inspect=lambda *a,**k:{'Id':'owned-id','Config':{'Labels':{root.LABEL:d.owner}}}
            def docker(*args,**kw):
                calls.append(args)
                if args[:2]==('network','inspect'): return json.dumps([{'Id':'owned-net','Labels':{root.LABEL:d.owner}}]).encode()
                return b''
            d.docker=docker; d.cleanup()
            self.assertTrue(d.cleaned); self.assertIn(('rm','-f','-v','owned-id'),calls)
            self.assertIn(('network','rm','owned-net'),calls)

    def test_expired_absolute_deadline_cannot_start_docker_even_during_cleanup(self):
        d=root.Driver({},Path('/offline-do-not-create')); d.deadline=0
        with patch.object(root.subprocess,'run') as run:
            for cleanup in (False,True):
                with self.assertRaisesRegex(ValueError,'ROOT_DEADLINE'): d.cmd(['docker','inspect','inert'],cleanup=cleanup)
            run.assert_not_called()

    def test_existing_output_preflight_never_owns_or_changes_existing_directory(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as t:
            d=root.Driver({'synthetic_only':True},Path(t))
            with patch.object(root.os,'geteuid',return_value=0):
                with self.assertRaisesRegex(ValueError,'NEW_ABSOLUTE_OWNED_OUTPUT'): d.prepare()
            self.assertFalse(d.root_created); self.assertEqual(list(Path(t).iterdir()),[])

if __name__=='__main__': unittest.main(verbosity=2)
