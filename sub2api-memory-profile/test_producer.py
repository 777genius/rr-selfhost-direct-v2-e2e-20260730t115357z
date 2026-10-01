"""Exercise the actual driver at subprocess.run; no Go/Docker/root actions."""
import copy,importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from contracts import ContractError
from launch_contracts import BASE,NODE,MACHINE,BASE_TAG,config_gate,toolchain_gate,build_gate,dockerfile_gate,service_gate
OWN=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('root_driver',OWN/'root-driver.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)

def config(root):
    return dict(machine_id=MACHINE,synthetic_only=True,base_image=BASE,node_image=NODE,
      postgres_image='postgres:18@sha256:'+'a'*64,redis_image='redis:7@sha256:'+'b'*64,
      fixture_dir=str(root/'fixture'),fixture_attestation_sha256='a'*64,
      go_binary=str(root/'go/bin/go'),go_binary_sha256='b'*64,modules_cache=str(root/'modules'),
      compilation_cache=str(root/'cache'),toolchain_receipt=str(root/'toolchain.json'),toolchain_receipt_sha256='c'*64,
      collector_source=str(root/'actual-collector.py'))

class Producer(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=OWN/'evidence');self.root=Path(self.tmp.name).resolve()/'producer00000001';self.root.mkdir();self.c=config(self.root)
        self.d=driver.Driver(self.c,self.root,'responses','fixed',None);self.d.private=self.root/'private';self.d.private.mkdir()
        self.d.env={'DATABASE_USER':'offline_fixture','DATABASE_DBNAME':'offline_fixture','REDIS_PASSWORD':'offline-synthetic-test-sentinel'}
        self.d.profile=self.root/'profiles';self.d.profile.mkdir();self.d.source=json.loads((OWN/'source-manifest.json').read_text())
        (self.d.private/'engine.env').write_text('OFFLINE=1\n')
        self.d.prepare_redis()
        self.calls=[]
    def tearDown(self):self.tmp.cleanup()
    def intercept(self,args,**kw):
        self.calls.append((args,kw));out=b''
        if args[0]==self.c['go_binary']:
            if 'build' in args:Path(args[args.index('-o')+1]).write_bytes(b'OFFLINE TEST BINARY PLACEHOLDER')
            else:out=b'profile-server: go1.27.1\n build -tags=rrsub2profile\n'
        elif args[:3]==['docker','image','inspect']:
            out=json.dumps([{'Id':('sha256:'+'f'*64 if args[3]==self.d.name+'-image' else BASE)}]).encode()
        elif args[:3]==['docker','network','create']:out=b'offline-network-id'
        elif args[:2]==['docker','inspect']:out=json.dumps([{'Config':{'Labels':{'rrsub2profile.owner':self.d.name}}}]).encode()
        elif args[:2]==['docker','exec']:raise RuntimeError('OFFLINE_STOP_BEFORE_SERVICE_EXEC')
        return subprocess.CompletedProcess(args,0,out,b'')
    def test_actual_build_subprocess_and_generated_dockerfile(self):
        with patch.object(driver.subprocess,'run',side_effect=self.intercept):self.d.build()
        args,kw=next((a,k) for a,k in self.calls if a[0]==self.c['go_binary'] and 'build' in a)
        self.assertEqual(kw['env']['GOMAXPROCS'],'2');self.assertEqual(kw['env']['GOCACHE'],self.c['compilation_cache'])
        self.assertEqual({k:kw['env'].get(k) for k in ('GOGC','GOMEMLIMIT','GODEBUG')},{'GOGC':None,'GOMEMLIMIT':None,'GODEBUG':None})
        build=next(a for a,k in self.calls if a[:2]==['docker','build'])
        self.assertIn('--network',build);self.assertIn('none',build);self.assertIn('--pull=false',build)
        text=(Path(build[-1])/'Dockerfile').read_text();dockerfile_gate(text,self.d.base_tag)
        inspect_index=next(i for i,(a,k) in enumerate(self.calls) if a==['docker','image','inspect',self.d.base_tag])
        build_index=next(i for i,(a,k) in enumerate(self.calls) if a[:2]==['docker','build'])
        self.assertLess(inspect_index,build_index)
        receipt=json.loads((self.root/'root-base-pin.json').read_text());self.assertEqual(receipt['base_image_id'],BASE)
        actual=json.loads((OWN.parent/'.spike-inputs/actual/profile-responses-fixed-00000009/root-base-pin.json').read_text())
        self.assertEqual(receipt['dockerfile_sha256'],actual['dockerfile_sha256'])
        self.assertNotIn(self.d.env['REDIS_PASSWORD'],(self.root/'build-receipt.json').read_text())
        for bad in [text.replace('--chmod=755','--chmod=644'),text.replace(self.d.base_tag,BASE),text.replace('USER 1000:1000','USER 0:0')]:
            with self.assertRaises(ContractError):dockerfile_gate(bad,self.d.base_tag)
        for key in ('GOMAXPROCS','GOCACHE','GOTOOLCHAIN','GOPROXY'):
            for value in (None,True,2,[],{},'wrong'):
                env=dict(kw['env']);env[key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ContractError):build_gate(args,env,self.c)
    def test_wrong_local_tag_id_stops_before_image_build(self):
        original=self.intercept
        def bad(args,**kw):
            if args==['docker','image','inspect',BASE_TAG]:
                self.calls.append((args,kw));return subprocess.CompletedProcess(args,0,json.dumps([{'Id':'sha256:'+'0'*64}]).encode(),b'')
            return original(args,**kw)
        with patch.object(driver.subprocess,'run',side_effect=bad),self.assertRaisesRegex(ContractError,'BASE_TAG_ID'):self.d.build()
        self.assertFalse(any(a[:2]==['docker','build'] for a,k in self.calls))
    def test_actual_service_create_payloads_at_subprocess_boundary(self):
        with patch.object(driver.os,'chown'),patch.object(driver.subprocess,'run',side_effect=self.intercept),self.assertRaisesRegex(RuntimeError,'OFFLINE_STOP'):
            self.d.launch()
        creates=[a for a,k in self.calls if a[:2]==['docker','create']];self.assertEqual(len(creates),2)
        pg,redis=creates
        self.assertEqual(pg[pg.index('--tmpfs')+1],'/var/lib/postgresql');self.assertEqual(pg[-1],self.c['postgres_image'])
        self.assertEqual(redis[-3:],[self.c['redis_image'],'redis-server','/rr-profile-redis.conf'])
        self.assertTrue(redis[redis.index('--mount')+1].endswith(',readonly'))
        self.assertFalse(any(self.d.env['REDIS_PASSWORD'] in x for a,k in self.calls for x in a))
        service_args=['--network-alias','postgres','--env-file',str(self.d.private/'postgres.env'),'--tmpfs','/var/lib/postgresql','--memory','512m']
        for image in (BASE,None,True,[],{},self.c['redis_image']):
            with self.assertRaises(ContractError):service_gate('postgres',image,service_args,(),self.c,self.d.private,None)
        with self.assertRaises(ContractError):service_gate('postgres',self.c['postgres_image'],service_args[:-2],(),self.c,self.d.private,None)
        with self.assertRaises(ContractError):service_gate('postgres',self.c['postgres_image'],service_args+['--tmpfs','/wrong'],(),self.c,self.d.private,None)
        for extra in (['--privileged'],['--publish','5432:5432'],['--env','SYNTHETIC_VALUE=unapproved']):
            with self.assertRaises(ContractError):service_gate('postgres',self.c['postgres_image'],service_args+extra,(),self.c,self.d.private,None)
    def test_config_required_fields_types_and_toolchain_receipt(self):
        config_gate(self.c)
        for key in self.c:
            for bad in (None,False,1,[],{}):
                c=copy.deepcopy(self.c);c[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ContractError):config_gate(c)
            c=copy.deepcopy(self.c);del c[key]
            with self.assertRaises(ContractError):config_gate(c)
        receipt={'go_version':'go1.27.1','go_binary_sha256':self.c['go_binary_sha256'],'compilation_cache':self.c['compilation_cache'],
          'stdlib_sha256':{n:'f'*64 for n in ('runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go')}}
        toolchain_gate(receipt,self.c)
        for key in receipt:
            for value in (None,True,[],{},'wrong'):
                r=copy.deepcopy(receipt);r[key]=value
                with self.assertRaises(ContractError):toolchain_gate(r,self.c)
