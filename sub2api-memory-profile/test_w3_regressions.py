"""Independent offline regression probes; synthetic files, no Go/Docker/root/network."""
import copy,gzip,hashlib,importlib.util,json,os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
BASE=pathlib.Path(__file__).resolve().parent/'evidence'
PRODUCER=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(PRODUCER))
import analyze,operator_config
from contracts import SAMPLE_INTS,ContractError
from test_contracts import proto
from test_producer import config
spec=importlib.util.spec_from_file_location('review_driver',PRODUCER/'root-driver.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o)+'\n')
class Independent(unittest.TestCase):
 def test_expected_manifest_without_reviewed_receipt_rejects_unreviewed_source(self):
  with tempfile.TemporaryDirectory(dir=BASE) as td:
   r=pathlib.Path(td);native=r/'stage/backend/internal/service/unreviewed.go';native.parent.mkdir(parents=True);native.write_text('package service\nvar unreviewed = true\n')
   legacy=json.loads((PRODUCER/'source-manifest.json').read_text());sm=copy.deepcopy(legacy)
   sm['source_after_sha256']={'backend/internal/service/unreviewed.go':sha(native)};sm['operator_after_sha256']={};sm['historical']['source_sha']='unreviewed';sm['source_patch_files']=[]
   write(r/'stage/source-manifest.json',sm);expected=r/'unreviewed-manifest.json';write(expected,sm)
   binary=r/'build/profile-server';binary.parent.mkdir();binary.write_bytes(b'SYNTHETIC UNREVIEWED BINARY')
   identity={k:1 for k in ('engine_pid','pid_start_ticks','cgroup_device','cgroup_inode','exe_device','exe_inode')};identity['container_id']='c'*64
   write(r/'resource-cleanup.json',{'failures':0});write(r/'evidence/account-cleanup.json',{'failures':0,'ambiguous_intent':False,'remaining_resources':[]})
   state={'total':0,'effects':0,'active':0,'exceeded':False,'records':[]}
   write(r/'evidence/setup.json',{'protocol':'responses','healthy_control':True,'preparation_state':state});write(r/'evidence/mock-final.json',state)
   runtime=[]
   for i in range(24):
    s={k:0 for k in SAMPLE_INTS};s.update(schema=1,sequence=i+1,pid=1,start_ms=1000+i*100.,end_ms=1001+i*100.,duration_ms=1.,heap_alloc=100,heap_objects=5,heap_inuse=4096,heap_idle=4096,heap_released=2048,heap_sys=8192,total_alloc=100+i,mallocs=10+i,frees=5+i,num_gc=0,last_gc_unix_ns=0,mem_profile_rate=524288,goroutines=3);runtime.append(s)
   profiles=r/'profiles';profiles.mkdir();(profiles/'runtime.ndjson').write_text(''.join(json.dumps(s)+'\n' for s in runtime))
   checkpoints=[]
   for i in range(4):
    checkpoints.append({'checkpoint':i,'elapsed_ms':100+i*600.});acks=[]
    for k,name in enumerate(('heap','allocs','goroutine')):
     a,b=runtime[i*6+k*2:i*6+k*2+2];acks.append({'schema':1,'checkpoint':i,'kind':k+1,'pid':1,'before_sequence':a['sequence'],'after_sequence':b['sequence'],'before_num_gc':0,'after_num_gc':0,'start_ms':a['end_ms'],'end_ms':b['start_ms']});(profiles/f'checkpoint-{i:03d}-{name}.pb.gz').write_bytes(gzip.compress(proto(name)))
    write(profiles/f'checkpoint-{i:03d}.json',acks)
   targets=checkpoints[1:];rss=[dict(identity,mono_ms=10000+c['elapsed_ms'],rss_bytes=100,smaps_rollup_rss_bytes=100,sockets=0) for c in targets];(r/'control-rss.ndjson').write_text(''.join(json.dumps(s)+'\n' for s in rss))
   run={'schema':'rrsub2profile-run-v1','status':'COMPLETE','protocol':'responses','lane':'control','no_forced_gc':True,'new_image_and_binary':True,'source_manifest_sha256':sha(r/'stage/source-manifest.json'),'build':{'binary_sha256':sha(binary),'image_id':'sha256:'+'d'*64},'cleanup_failures':0,'scheduled_streams':[],'rows':[],'requests_completed':0,'measurement_elapsed_ms':3000,'namespace_pid':1,'identity':identity,'checkpoints':checkpoints,'control_reference':{'lane':'fixed','targets':targets},'baseline_ms':10000,'missing_counters':[]};write(r/'run.json',run)
   with self.assertRaisesRegex(ContractError,'SOURCE_MANIFEST_CHANGED'):analyze.analyze(r)
   output=r/'result.json';cp=subprocess.run([sys.executable,str(PRODUCER/'analyze.py'),str(r),'--expected-manifest',str(expected),'--out',str(output)],capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
   self.assertNotEqual(cp.returncode,0);self.assertFalse(output.exists())
   for receipt in (False,None,'',{},[],{'schema':'invalid'}):
    sm['reviewed_source']=receipt;write(expected,sm);write(r/'stage/source-manifest.json',sm);run['source_manifest_sha256']=sha(expected);write(r/'run.json',run)
    cp=subprocess.run([sys.executable,str(PRODUCER/'analyze.py'),str(r),'--expected-manifest',str(expected),'--out',str(output)],capture_output=True,text=True)
    self.assertNotEqual(cp.returncode,0);self.assertFalse(output.exists())
   del sm['reviewed_source']
   self.assertNotIn('reviewed_source',sm)
 def test_private_outputs_exclusive_0600_at_creation(self):
  with tempfile.TemporaryDirectory(dir=BASE) as td:
   r=pathlib.Path(td).resolve();go=r/'go/bin/go';go.parent.mkdir(parents=True);go.write_bytes(b'SYNTHETIC GO EXECUTABLE');cache=r/'cache';cache.mkdir();collector=r/'collector.py';collector.write_text('# synthetic\n');freeze=r/'freeze'
   for n in ('runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go'):
    p=freeze/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// synthetic\n')
   c=config(r);c['go_binary']=str(go);c['go_binary_sha256']=sha(go);old=r/'old.json';write(old,c);out=r/'new.json';receipt=r/'receipt.json';observed=[];original=pathlib.Path.chmod;original_open=os.open;first_modes=[]
   def chmod(p,mode,*a,**kw):
    if p==out:observed.append(p.stat().st_mode&0o777)
    return original(p,mode,*a,**kw)
   def observe_open(path,flags,mode=0o777,**kw):
    fd=original_open(path,flags,mode,**kw)
    if flags & os.O_CREAT:
     first_modes.append((os.fstat(fd).st_mode&0o777,flags))
    return fd
   previous=os.umask(0o022)
   try:
    with patch.object(pathlib.Path,'chmod',chmod),patch.object(os,'open',observe_open):operator_config.migrate(old,out,receipt,freeze,cache,collector)
   finally:os.umask(previous)
   self.assertEqual(observed,[]);self.assertEqual([m for m,f in first_modes],[0o600,0o600]);self.assertTrue(all(f & os.O_EXCL for m,f in first_modes));self.assertEqual(out.stat().st_mode&0o777,0o600);self.assertEqual(receipt.stat().st_mode&0o777,0o600)
 def test_preflight_toolchain_query_and_compile_share_sanitized_environment(self):
  with tempfile.TemporaryDirectory(dir=BASE) as td:
   r=pathlib.Path(td).resolve();output=r/'run00000001';c=config(r);fixture=pathlib.Path(c['fixture_dir']);fixture.mkdir();go=pathlib.Path(c['go_binary']);go.parent.mkdir(parents=True);go.write_bytes(b'SYNTHETIC EXECUTABLE');c['go_binary_sha256']=sha(go)
   for key in ('modules_cache','compilation_cache'):pathlib.Path(c[key]).mkdir()
   (fixture/'engine.env').write_text('DATABASE_HOST=postgres\nREDIS_HOST=redis\nDATABASE_USER=synthetic\nDATABASE_PASSWORD=synthetic\nDATABASE_DBNAME=synthetic\n');(fixture/'snapshot.sql').write_text('-- synthetic\n');write(fixture/'lab.json',{})
   attestation={'source':'transport-isolated-r4','status':'PASS','real_provider_keys_copied':False,'images':{'postgres':c['postgres_image'],'redis':c['redis_image']},'hashes':{n:sha(fixture/n) for n in ('engine.env','snapshot.sql','lab.json')}};write(fixture/'profile-fixture.json',attestation);c['fixture_attestation_sha256']=sha(fixture/'profile-fixture.json')
   ambient=r/'ambient-goroot';stdlib={}
   for n in ('runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go'):
    p=ambient/'src'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// synthetic reviewed ambient tree\n');stdlib[n]=sha(p)
   effective=r/'pinned-executable-goroot'
   for n in stdlib:
    p=effective/'src'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// synthetic reviewed ambient tree\n')
   receipt=pathlib.Path(c['toolchain_receipt']);write(receipt,{'go_version':'go1.27.1','go_binary_sha256':c['go_binary_sha256'],'stdlib_sha256':stdlib,'compilation_cache':c['compilation_cache']});c['toolchain_receipt_sha256']=sha(receipt)
   d=driver.Driver(c,output,'responses','fixed',None);calls=[];original=pathlib.Path.read_text
   def read_text(p,*a,**kw):
    if str(p)=='/etc/machine-id':return driver.MACHINE+'\n'
    if str(p)=='/proc/meminfo':return 'MemAvailable: 10000000 kB\n'
    return original(p,*a,**kw)
   def intercept(args,**kw):
    calls.append((args,kw))
    if args==[c['go_binary'],'version']:return subprocess.CompletedProcess(args,0,b'go version go1.27.1 linux/amd64\n',b'')
    if args==[c['go_binary'],'env','GOROOT']:
     used=effective if (kw.get('env') or {}).get('GOENV')=='off' else ambient
     return subprocess.CompletedProcess(args,0,(str(used)+'\n').encode(),b'')
    if args==['uname','-m']:return subprocess.CompletedProcess(args,0,b'x86_64\n',b'')
    if args[:3]==['docker','image','inspect']:
     image='sha256:'+'f'*64 if args[3]==d.name+'-image' else driver.BASE
     return subprocess.CompletedProcess(args,0,json.dumps([{'Id':image}]).encode(),b'')
    if args[:2] in (['docker','image'],['docker','build']):return subprocess.CompletedProcess(args,0,b'',b'')
    if args==[c['go_binary'],'version','-m',str(output/'build/profile-server')]:return subprocess.CompletedProcess(args,0,b'profile-server: go1.27.1\n build -tags=rrsub2profile\n',b'')
    if args[0]==c['go_binary'] and 'build' in args:
     pathlib.Path(args[args.index('-o')+1]).write_bytes(b'SYNTHETIC BINARY');return subprocess.CompletedProcess(args,0,b'',b'')
    raise AssertionError(args)
   with patch.object(driver.subprocess,'run',intercept),patch.object(driver.os,'geteuid',return_value=0),patch.object(driver.os,'chown'),patch.object(pathlib.Path,'read_text',read_text),patch.object(driver,'generate',return_value=({},'')),patch.dict(os.environ,{'GOROOT':str(ambient),'GOTOOLCHAIN':'auto','GOENV':str(r/'poisoned-goenv'),'GOCACHE':'/ambient-cache','GOMODCACHE':'/ambient-modules','GOGC':'1','GOMEMLIMIT':'1MiB'}):
    d.preflight()
    d.build()
   build=next(kw for args,kw in calls if args[0]==c['go_binary'] and 'build' in args)
   go_calls=[kw for args,kw in calls if args[0]==c['go_binary']]
   self.assertEqual(len(go_calls),4);self.assertTrue(all(kw['env']==build['env'] for kw in go_calls))
   self.assertEqual(build['env']['GOCACHE'],c['compilation_cache']);self.assertEqual(build['env']['GOMODCACHE'],c['modules_cache']);self.assertEqual(build['env']['GOMAXPROCS'],'2')
   self.assertTrue(all(k not in build['env'] for k in ('GOROOT','GOGC','GOMEMLIMIT','GODEBUG')))
   query=next(kw for args,kw in calls if args==[c['go_binary'],'env','GOROOT']);self.assertEqual(query['env'],build['env']);self.assertEqual(query['env']['GOENV'],'off')
   self.assertNotIn('GOROOT',build['env']);self.assertEqual(build['env']['GOTOOLCHAIN'],'local')
   self.assertEqual(d.effective_goroot,effective)
   # An ambient reviewed tree cannot authorize different bytes in the tree
   # selected by the actual sanitized compiler environment.
   (effective/'src/runtime/mprof.go').write_text('// unreviewed effective toolchain\n')
   d2=driver.Driver(c,r/'run00000002','responses','fixed',None)
   with patch.object(driver.subprocess,'run',intercept),patch.object(driver.os,'geteuid',return_value=0),patch.object(driver.os,'chown'),patch.object(pathlib.Path,'read_text',read_text),patch.object(driver,'generate',return_value=({},'')),patch.dict(os.environ,{'GOROOT':str(ambient),'GOENV':str(r/'poisoned-goenv'),'GOTOOLCHAIN':'auto'}):
    with self.assertRaisesRegex(ContractError,'MATCHING_STDLIB_REQUIRED'):d2.preflight()
if __name__=='__main__':unittest.main(verbosity=2)
