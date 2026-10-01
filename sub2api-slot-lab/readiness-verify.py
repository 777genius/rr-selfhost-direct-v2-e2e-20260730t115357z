"""Offline launch contracts; all Docker calls intercepted, no root entrypoint."""
from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent.parent
OWN=ROOT/'sub2api-slot-lab'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def contract(kind,side):
    package=ROOT/('sub2api-slot-lab' if kind=='slot' else 'sub2api-memory-profile')
    old=ROOT/'.spike-inputs'/('candidate/sub2api-slot-lab' if kind=='slot' else 'profile-candidate/sub2api-memory-profile')
    sys.path.insert(0,str(package))
    spec=importlib.util.spec_from_file_location('readiness_driver',(old if side=='old' else package)/'root-driver.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    class Launch(unittest.TestCase):
        def exercise(self,never=False):
            with tempfile.TemporaryDirectory(dir=OWN/'build') as td:
                base=Path(td);(base/'snapshot.sql').write_bytes(b'inert')
                pid=base/'pid';psql=base/'psql'
                psql.write_text('#!/bin/sh\n[ "$PGOPTIONS" = "-c default_transaction_read_only=on" ] || exit 2\n[ "$*" = "-X -qAt -v ON_ERROR_STOP=1 -U fixture_user -d fixture_db -c SELECT 1" ] || exit 3\n[ "$DB_READY" = yes ] || exit 1\nprintf "1\\n"\n');psql.chmod(0o700)
                d=m.Driver.__new__(m.Driver);d.deadline=600000;d.started=None;d.private=base;d.snapshot=base/'snapshot.sql'
                d.name='fixture';d.owner='fixture';d.net='fixture-net';d.c={'postgres_image':'pg','redis_image':'redis'}
                d.env={'DATABASE_USER':'fixture_user','DATABASE_DBNAME':'fixture_db'};d.dbuser='fixture_user';d.dbname='fixture_db'
                d.journal=lambda:None;d.create=lambda suffix,*a,**kw:suffix
                clock=[0];phase=[0];calls=[];realrun=subprocess.run
                states=[('sh',False),('sh',True),('sh',False),('postgres',False),('postgres',True)]
                def sleep(n):clock[0]+=n*1000;phase[0]+=1
                def run(args,**kw):
                    if args[:2]==['docker','exec']:
                        calls.append(args)
                        if '-i' in args:raise RuntimeError('RESTORE')
                        if 'pg_isready' in args:return subprocess.CompletedProcess(args,0,b'',b'')
                        if args[3:5]==['sh','-c']:
                            comm,db=states[min(phase[0],4)];pid.write_text(comm+'\n')
                            script=args[5].replace('/proc/1/comm',str(pid))
                            env=dict(os.environ,PATH=str(base)+':'+os.environ['PATH'],POSTGRES_USER='fixture_user',POSTGRES_DB='fixture_db',DB_READY='yes' if db and not never else 'no')
                            return realrun(['sh','-c',script],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,timeout=kw['timeout'])
                        raise RuntimeError('RESTORE') # slot version query is after readiness
                    return subprocess.CompletedProcess(args,0,b'network',b'')
                with patch.object(m,'mono',side_effect=lambda:clock[0]),patch.object(m.time,'sleep',side_effect=sleep),patch.object(m.os,'chown'),patch.object(m.subprocess,'run',side_effect=run):
                    if never:
                        with self.assertRaisesRegex(ValueError,'READY_TIMEOUT'):d.launch()
                        self.assertLessEqual(clock[0],30000);self.assertGreaterEqual(clock[0],29999)
                    else:
                        with self.assertRaisesRegex(RuntimeError,'RESTORE'):d.launch()
                        self.assertEqual(phase[0],4,'restore must await final PID1 and exact target DB')
                    self.assertTrue(calls)
        def test_final_exec_and_exact_db_before_restore(self):self.exercise()
        def test_not_ready_stops_within_30_seconds(self):self.exercise(True)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Launch)
    if kind=='slot':
        import logging_preflight_test as log
        log.root=m
        class Body(unittest.TestCase):
            def test_emitted_body_limit(self):
                observed=[];dump=m.dump
                def capture(path,value):
                    if Path(path).name=='config.yaml':observed.append(value)
                    return dump(path,value)
                with patch.object(m,'dump',side_effect=capture):
                    log.LoggingPreflight('test_emitted_config_and_environment_pass_native_output_predicate').test_emitted_config_and_environment_pass_native_output_predicate()
                g=observed[0]['gateway'];self.assertEqual(g['max_body_size'],2097152)
                self.assertTrue(0<g.get('text_max_body_size',32*1024*1024)<=g['max_body_size'])
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(Body))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
if len(sys.argv)>1:raise SystemExit(contract(*sys.argv[1:]))
ledger={'schema':'root-readiness-v1','actual_complete_E2E':'NOT RUN by worker; controller must run all existing real E2E gates','runs':{},'slot_before_after':{},'profile_before_after':{}}
def run(name,args,cwd=ROOT):
    cp=subprocess.run(args,cwd=cwd,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=40)
    ledger['runs'][name]={'command':args,'exit':cp.returncode,'output':cp.stdout.decode()};return cp.returncode
for kind in ('slot','profile'):
    assert run(kind+'-old-RED',[sys.executable,str(Path(__file__).resolve()),kind,'old'])==1
    assert run(kind+'-new-GREEN',[sys.executable,str(Path(__file__).resolve()),kind,'new'])==0
# Unchanged slot tests, relocate historical input paths in memory only.
real=Path.read_text
with patch.object(Path,'read_text',lambda p,*a,**k:real(ROOT/'.spike-inputs/slot-original-inputs/original-inputs/actual-image.json' if p==ROOT/'.spike-inputs/actual-image.json' else p,*a,**k)):
    sys.path.insert(0,str(OWN));suite=unittest.defaultTestLoader.discover(str(OWN),pattern='*_test.py')
sys.modules['launch_transport_test'].BASELINE=ROOT/'.spike-inputs/slot-original-inputs/original-inputs/candidate/sub2api-slot-lab'
import io
out=io.StringIO()
# Frozen engine transport test assumes services ready; retain its recorded old
# readiness stub. Real new readiness is exercised independently above.
loader=importlib.machinery.SourceFileLoader.exec_module
def load_fixture(self,module):
    loader(self,module)
    if module.__name__=='launch_candidate' and hasattr(module.Driver,'wait_postgres'):
        module.Driver.wait_postgres=lambda d,pg:d.docker('exec',pg,'pg_isready','-U',d.dbuser,'-d',d.dbname,timeout=2)
with patch.object(importlib.machinery.SourceFileLoader,'exec_module',load_fixture):
    result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
ledger['runs']['slot-python-16']={'tests':result.testsRun,'exit':0 if result.wasSuccessful() else 1,'output':out.getvalue()}
print(out.getvalue(),flush=True)
assert result.wasSuccessful() and result.testsRun==16
assert run('slot-node-34',['node','--test',str(OWN/'offline.test.mjs'),str(OWN/'recovery-contract.test.mjs')])==0
# Preserve all profile files: disposable harness only relocates frozen fixtures.
with tempfile.TemporaryDirectory(dir=OWN/'build') as td:
    harness=Path(td);p=harness/'sub2api-memory-profile';p.symlink_to(ROOT/'sub2api-memory-profile',target_is_directory=True)
    (harness/'.spike-inputs').symlink_to(ROOT/'.spike-inputs/profile-original-inputs/original-inputs',target_is_directory=True)
    for n in ('sub2api-spike','sub2api-transport-r4'):(harness/n).symlink_to(ROOT/n,target_is_directory=True)
    # Tests derive roots from __file__; copied files retain disposable layout.
    p.unlink();shutil.copytree(ROOT/'sub2api-memory-profile',p)
    assert run('profile-python',[sys.executable,'-m','unittest','discover','-s',str(p),'-p','test_*.py','-v'],harness)==0
    assert run('profile-node-7',['node','--test',str(p/'offline.test.mjs')],harness)==0
for kind,package,baseline in [('slot',OWN,ROOT/'.spike-inputs/candidate/sub2api-slot-lab'),('profile',ROOT/'sub2api-memory-profile',ROOT/'.spike-inputs/profile-candidate/sub2api-memory-profile')]:
    before={str(p.relative_to(baseline)):sha(p) for p in baseline.rglob('*') if p.is_file()}
    after={n:sha(package/n) for n in before}
    ledger[kind+'_before_after']={'before':before,'after':after,'changed':[n for n in before if before[n]!=after[n]]}
    assert ledger[kind+'_before_after']['changed']==['root-driver.py']
ledger['fixture_adaptation']='Legacy slot engine transport assumed-ready stub retained in memory; separate actual readiness launch contracts execute emitted shell. Profile frozen fixtures relocated in disposable harness.'
ledger['new_artifact_hashes']={n:sha(OWN/n) for n in ('readiness-verify.py','ROOT-READINESS.md')}
ledger['slot_file_count']=sum(p.is_file() for p in OWN.rglob('*'))+1
assert ledger['slot_file_count']<65
(OWN/'ROOT-READINESS-LEDGER.json').write_text(json.dumps(ledger,indent=2)+'\n')
print('PASS root startup contracts and unchanged offline suites; E2E NOT RUN')
