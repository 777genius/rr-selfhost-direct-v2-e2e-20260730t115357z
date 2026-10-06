import importlib.util, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location('prepare', HERE / 'prepare-standalone.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
BASE = ROOT / '.spike-inputs/public-base'
PACKAGE = ROOT / '.spike-inputs/candidate'

class PackagingTests(unittest.TestCase):
    def test_exact_prior_and_runtime_and_plan(self):
        prior = m.prior_bytes(BASE)
        source = PACKAGE / 'historical-input/prior-code'
        self.assertEqual(len(prior), 102)
        for n, b in prior.items(): self.assertEqual(b, (source/n).read_bytes(), n)
        runtime = m.runtime_bytes(PACKAGE, BASE)
        self.assertEqual(len(runtime), 103)
        for n in json.loads((PACKAGE/'changed-loc.json').read_text()):
            self.assertEqual(runtime[n], (PACKAGE/'overlay'/n).read_bytes())
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'runtime'; m.write_new(out, runtime)
            proc = subprocess.run(['node','sub2api-regression-lab/run.mjs','--plan'],cwd=out,check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(proc.stdout), json.loads((PACKAGE/'evidence/standalone-plan.json').read_text()))

    def damaged_base(self, mode):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'base'; shutil.copytree(BASE, root)
            file = root/'sub2api-spike/broker.test.mjs'
            if mode == 'hash': file.chmod(0o644); file.write_bytes(file.read_bytes()+b'\n')
            elif mode == 'missing': file.unlink()
            elif mode == 'symlink': file.unlink(); file.symlink_to(BASE/'sub2api-spike/broker.test.mjs')
            with self.assertRaisesRegex(ValueError, {'hash':'base hash','missing':'missing file','symlink':'symlink'}[mode]): m.runtime_bytes(PACKAGE, root)
    def test_wrong_base_hash(self): self.damaged_base('hash')
    def test_missing_base_file(self): self.damaged_base('missing')
    def test_symlink_base_file(self): self.damaged_base('symlink')
    def test_path_traversal_and_absolute_and_noncanonical(self):
        for n in ('../evil','/tmp/evil','sub2api-spike/../evil','sub2api-spike//evil','sub2api-spike\\evil'):
            with self.assertRaises(ValueError): m.safe(n)
    def test_bad_delta_context_and_result_and_bounds(self):
        original = m.load
        for mutation in ('context','result','bounds','path'):
            delta = original('base-to-prior.delta.json'); name = next(iter(delta)); row = delta[name]
            if mutation == 'context': row['edits'][0]['old_sha256'] = '0'*64
            if mutation == 'result': row['prior_sha256'] = '0'*64
            if mutation == 'bounds': row['edits'][0]['start'] = -1
            if mutation == 'path': delta['../escape'] = delta.pop(name)
            with patch.object(m,'load',side_effect=lambda n: delta if n=='base-to-prior.delta.json' else original(n)):
                with self.assertRaises(ValueError): m.prior_bytes(BASE)
    def test_overlay_and_adapter_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); shutil.copytree(PACKAGE/'overlay',root/'overlay')
            shutil.copyfile(PACKAGE/'changed-loc.json',root/'changed-loc.json'); shutil.copyfile(PACKAGE/'adapter.mjs',root/'adapter.mjs')
            n=next(iter(json.loads((root/'changed-loc.json').read_text())))
            (root/'overlay'/n).chmod(0o644); (root/'adapter.mjs').chmod(0o644)
            original=(root/'overlay'/n).read_bytes(); (root/'overlay'/n).write_bytes(original+b'\n')
            with self.assertRaisesRegex(ValueError,'overlay result hash'): m.runtime_bytes(root,BASE)
            (root/'overlay'/n).write_bytes(original); (root/'adapter.mjs').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'runtime hash'): m.runtime_bytes(root,BASE)
    def test_full_base_verified_before_delta(self):
        original=m.load
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'base'; shutil.copytree(BASE,root); (root/'sub2api-spike/util.mjs').chmod(0o644); (root/'sub2api-spike/util.mjs').write_bytes(b'wrong')
            def guard(n):
                self.assertNotEqual(n,'base-to-prior.delta.json','delta read before full base verification')
                return original(n)
            with patch.object(m,'load',side_effect=guard):
                with self.assertRaisesRegex(ValueError,'base hash'): m.prior_bytes(root)
    def test_controller_replacements_and_audit_without_prior_delivery(self):
        actions=json.loads((HERE/'action-manifest.json').read_text())
        ledger=json.loads((PACKAGE/'output-hashes.json').read_text())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); package=root/'sub2api-transport-r4'; package.mkdir()
            # External disposable integration fixture; never an owned delivery tree.
            for name in [*ledger,'output-hashes.json']:
                if name.startswith(('runtime/','historical-input/prior-code/')): continue
                target=package/name; target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((PACKAGE/name).read_bytes())
            (root/'sub2api-transport-packaging').symlink_to(HERE,target_is_directory=True)
            for row in actions['replace']:
                target=root/row['target']; self.assertEqual(m.digest(target.read_bytes()),row['before_sha256'])
                retained=root/row['retain_original_as']; retained.parent.mkdir(parents=True,exist_ok=True)
                retained.write_bytes(target.read_bytes()); target.write_bytes((ROOT/row['source']).read_bytes())
            self.assertFalse((package/'historical-input/prior-code').exists())
            proc=subprocess.run(['python3',str(package/'audit.py'),'--base-root',str(BASE)],check=True,capture_output=True,text=True)
            result=json.loads(proc.stdout); self.assertEqual(result['original_output_hashes_verified'],294)
            self.assertEqual(result['integrity'],'PASS')
            out=root/'runtime'
            run=subprocess.run(['python3',str(package/'prepare-standalone.py'),'--base-root',str(BASE),'--output',str(out),'--plan'],check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(run.stdout),json.loads((PACKAGE/'evidence/standalone-plan.json').read_text()))

    def test_default_archive_is_fixed_sha_and_rejects_links(self):
        import io, tarfile
        def archive(link=False):
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w') as tar:
                for name in m.load('base-hashes.json'):
                    payload=(BASE/name).read_bytes(); info=tarfile.TarInfo(name); info.size=len(payload)
                    if link: info.type=tarfile.SYMTYPE; info.linkname='/outside'; info.size=0
                    tar.addfile(info,io.BytesIO(payload) if not link else None)
                    if link: break
            return stream.getvalue()
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=archive())) as run:
            self.assertEqual(m.base_bytes(repo=ROOT),m.base_bytes(BASE))
            command=run.call_args.args[0]
            self.assertEqual(command,['git','-C',str(ROOT),'archive','--format=tar',m.SHA,'--',*m.ROOTS])
        with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=archive(True))):
            with self.assertRaisesRegex(ValueError,'nonregular archive'): m.base_bytes(repo=ROOT)

    def test_no_output_on_bad_input_or_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'runtime'
            r=subprocess.run(['python3',str(HERE/'prepare-standalone.py'),'--base-root',d,'--package-root',str(PACKAGE),'--output',str(out)],capture_output=True)
            self.assertNotEqual(r.returncode,0); self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaisesRegex(ValueError,'already exists'): m.write_new(out,{})

if __name__ == '__main__': unittest.main(verbosity=2)
