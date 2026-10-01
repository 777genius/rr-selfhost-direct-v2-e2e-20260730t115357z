"""Independent offline regression probes; synthetic files, no Go/Docker/root/network."""
import copy,gzip,hashlib,importlib.util,json,os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
BASE=pathlib.Path(__file__).resolve().parent
PRODUCER=BASE/'harness/sub2api-memory-profile'
sys.path.insert(0,str(PRODUCER))
import analyze,operator_config
from contracts import SAMPLE_INTS,ContractError
from test_contracts import proto
from test_producer import config
spec=importlib.util.spec_from_file_location('review_driver',PRODUCER/'root-driver.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o)+'\n')
class Independent(unittest.TestCase):
 def test_expected_manifest_without_reviewed_receipt_accepts_unreviewed_source(self):
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
   self.assertEqual(cp.returncode,0,cp.stderr);self.assertEqual(json.loads(output.read_text())['status'],'DIAGNOSTIC_ONLY')
   self.assertNotIn('reviewed_source',sm)
 def test_private_config_is_created_world_readable_until_chmod(self):
  with tempfile.TemporaryDirectory(dir=BASE) as td:
   r=pathlib.Path(td).resolve();go=r/'go/bin/go';go.parent.mkdir(parents=True);go.write_bytes(b'SYNTHETIC GO EXECUTABLE');cache=r/'cache';cache.mkdir();collector=r/'collector.py';collector.write_text('# synthetic\n');freeze=r/'freeze'
   for n in ('runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go'):
    p=freeze/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// synthetic\n')
   c=config(r);c['go_binary']=str(go);c['go_binary_sha256']=sha(go);old=r/'old.json';write(old,c);out=r/'new.json';receipt=r/'receipt.json';observed=[];original=pathlib.Path.chmod
   def chmod(p,mode,*a,**kw):
    if p==out:observed.append(p.stat().st_mode&0o777)
    return original(p,mode,*a,**kw)
   previous=os.umask(0o022)
   try:
    with patch.object(pathlib.Path,'chmod',chmod):operator_config.migrate(old,out,receipt,freeze,cache,collector)
   finally:os.umask(previous)
   self.assertEqual(observed,[0o644]);self.assertEqual(out.stat().st_mode&0o777,0o600)
 def test_preflight_toolchain_query_and_compile_have_different_environments(self):
  with tempfile.TemporaryDirectory(dir=BASE) as td:
   r=pathlib.Path(td).resolve();output=r/'run00000001';c=config(r);fixture=pathlib.Path(c['fixture_dir']);fixture.mkdir();go=pathlib.Path(c['go_binary']);go.parent.mkdir(parents=True);go.write_bytes(b'SYNTHETIC EXECUTABLE');c['go_binary_sha256']=sha(go)
   for key in ('modules_cache','compilation_cache'):pathlib.Path(c[key]).mkdir()
   (fixture/'engine.env').write_text('DATABASE_HOST=postgres\nREDIS_HOST=redis\nDATABASE_USER=synthetic\nDATABASE_PASSWORD=synthetic\nDATABASE_DBNAME=synthetic\n');(fixture/'snapshot.sql').write_text('-- synthetic\n');write(fixture/'lab.json',{})
   attestation={'source':'transport-isolated-r4','status':'PASS','real_provider_keys_copied':False,'images':{'postgres':c['postgres_image'],'redis':c['redis_image']},'hashes':{n:sha(fixture/n) for n in ('engine.env','snapshot.sql','lab.json')}};write(fixture/'profile-fixture.json',attestation);c['fixture_attestation_sha256']=sha(fixture/'profile-fixture.json')
   ambient=r/'ambient-goroot';stdlib={}
   for n in ('runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go'):
    p=ambient/'src'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('// synthetic reviewed ambient tree\n');stdlib[n]=sha(p)
   receipt=pathlib.Path(c['toolchain_receipt']);write(receipt,{'go_version':'go1.27.1','go_binary_sha256':c['go_binary_sha256'],'stdlib_sha256':stdlib,'compilation_cache':c['compilation_cache']});c['toolchain_receipt_sha256']=sha(receipt)
   d=driver.Driver(c,output,'responses','fixed',None);calls=[];original=pathlib.Path.read_text
   def read_text(p,*a,**kw):
    if str(p)=='/etc/machine-id':return driver.MACHINE+'\n'
    if str(p)=='/proc/meminfo':return 'MemAvailable: 10000000 kB\n'
    return original(p,*a,**kw)
   def intercept(args,**kw):
    calls.append((args,kw))
    if args==[c['go_binary'],'version']:return subprocess.CompletedProcess(args,0,b'go version go1.27.1 linux/amd64\n',b'')
    if args==[c['go_binary'],'env','GOROOT']:return subprocess.CompletedProcess(args,0,(str(ambient)+'\n').encode(),b'')
    if args==['uname','-m']:return subprocess.CompletedProcess(args,0,b'x86_64\n',b'')
    if args[:3]==['docker','image','inspect']:return subprocess.CompletedProcess(args,0,b'[]',b'')
    if args[0]==c['go_binary'] and 'build' in args:raise RuntimeError('offline stop at compile boundary')
    raise AssertionError(args)
   with patch.object(driver.subprocess,'run',intercept),patch.object(driver.os,'geteuid',return_value=0),patch.object(driver.os,'chown'),patch.object(pathlib.Path,'read_text',read_text),patch.object(driver,'generate',return_value=({},'')),patch.dict(os.environ,{'GOROOT':str(ambient),'GOTOOLCHAIN':'auto'}):
    d.preflight()
    with self.assertRaisesRegex(RuntimeError,'offline stop'):d.build()
   query=next(kw for args,kw in calls if args==[c['go_binary'],'env','GOROOT']);self.assertIsNone(query['env'])
   self.assertNotIn('GOROOT',calls[-1][1]['env']);self.assertEqual(calls[-1][1]['env']['GOTOOLCHAIN'],'local')
if __name__=='__main__':unittest.main(verbosity=2)
