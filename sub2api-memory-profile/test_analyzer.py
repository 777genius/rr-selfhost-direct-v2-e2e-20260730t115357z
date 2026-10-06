"""End-to-end analyzer data test. Synthetic runtime/protobuf, frozen real RSS.
This proves executable data contracts, never a Go or Docker runtime result.
"""
import copy,gzip,json,tempfile,unittest
from pathlib import Path
from contracts import ContractError,SAMPLE_INTS
from prepare import generate,INPUT,OWN,sha
from analyze import analyze
from test_contracts import proto,row as sample_burst

def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v)+'\n')

def shift(v,delta,cid):
    times={'mono_ms','sample_started_ms','started_ms','ended_ms','last_sample_ms','first_ready_ms'}
    if type(v) is dict:
        return {k:(x+delta if k in times and type(x) in (int,float) else cid if k in ('id','batch_id') and type(x) is str and x.startswith('memory-') else shift(x,delta,cid)) for k,x in v.items()}
    if type(v) is list:return [shift(x,delta,cid) for x in v]
    return v

class EndToEndAnalyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (INPUT/'actual-execution/responses/memory-responses-8-5/case.json').is_file():
            raise unittest.SkipTest('W1 full raw run/collector/profile fixtures absent from supplied W2 package; no synthetic substitution')
        cls.tmp=tempfile.TemporaryDirectory(dir=OWN/'evidence');cls.root=Path(cls.tmp.name);r=cls.root
        generate(r/'stage')
        binary=r/'build/profile-server';binary.parent.mkdir();binary.write_bytes(b'SYNTHETIC DATA TEST ONLY; NOT A GO BINARY')
        historical=INPUT/'actual-execution/responses/memory-responses-8-5'
        case=json.loads((historical/'case.json').read_text());ready=json.loads((historical/'telemetry.ready.json').read_text());done=json.loads((historical/'telemetry.done.json').read_text())
        rss=[json.loads(x)for x in (historical/'telemetry.ndjson').read_text().splitlines()]
        base=ready['container_created_ms'];identity={k:ready[k]for k in ('instance','engine_pid','pid_start_ticks','cgroup_path','cgroup_device','cgroup_inode','exe_device','exe_inode','container_id')}
        resources=[{'kind':'accounts','id':case['dedicated_account_id']}]
        preparation=[{'sequence':1,'id':'warmup','identity':'responses','close_ms':base,'effects':1}]
        prep={'total':1,'effects':1,'active':0,'exceeded':False,'records':preparation}
        write(r/'evidence/setup.json',{'protocol':'responses','healthy_control':True,'resources':resources,'preparation_state':prep})
        all_records=copy.deepcopy(preparation);runrows=[];checkpoints=[];samples=[]
        for i in range(1510):
            s={k:0 for k in SAMPLE_INTS};s.update(schema=1,sequence=i+1,pid=1,start_ms=base+i*100,end_ms=base+i*100+1,duration_ms=1,
                heap_alloc=100,heap_objects=5,heap_inuse=4096,heap_idle=4096,heap_released=2048,heap_sys=8192,total_alloc=100+i,
                mallocs=10+i,frees=5+i,num_gc=i//10,last_gc_unix_ns=(i//10)*1000000000,mem_profile_rate=512*1024,goroutines=3)
            samples.append(s)
        p=r/'profiles';p.mkdir();(p/'runtime.ndjson').write_text(''.join(json.dumps(s)+'\n'for s in samples))
        peak=max(s['cgroup_peak_bytes'] for s in rss)
        for i in range(11):
            start=i*150;ack=[]
            for kind,name in enumerate(('heap','allocs','goroutine'),1):
                a=samples[start+2*(kind-1)];b=samples[start+2*(kind-1)+1]
                ack.append({'schema':1,'checkpoint':i,'kind':kind,'pid':1,'before_sequence':a['sequence'],'after_sequence':b['sequence'],
                     'before_num_gc':a['num_gc'],'after_num_gc':b['num_gc'],'start_ms':a['end_ms'],'end_ms':b['start_ms']})
                (p/f'checkpoint-{i:03d}-{name}.pb.gz').write_bytes(gzip.compress(proto(name)))
            write(p/f'checkpoint-{i:03d}.json',ack);checkpoints.append({'checkpoint':i,'elapsed_ms':start*100+501})
            if not i:continue
            cid=f'memory-responses-8-5-b{i:02d}';delta=(i-1)*15000
            row=shift(copy.deepcopy(case),delta,cid);rd=shift(copy.deepcopy(ready),delta,cid);dn=shift(copy.deepcopy(done),delta,cid);ss=shift(copy.deepcopy(rss),delta,cid)
            rd['first_sample']['cgroup_peak_bytes']=peak
            for s in ss:s['cgroup_peak_bytes']=peak
            row.update(stop_required=False,exceeded=False,upstream_attempts_total=5,upstream_effects_total=5,dedicated_resources=resources)
            sequences=list(range(2+(i-1)*5,2+i*5));row['attempt_sequences']=sequences
            row['admitted_request_ids']=[cid+f'.r{j:02d}' for j in range(1,6)]
            row['request_results']=sample_burst()['request_results']
            for d,id in zip(row['request_results'],row['admitted_request_ids']):d['id']=id
            for u,seq in zip(row['upstream'],sequences):u['sequence']=seq;u['id']=row['admitted_request_ids'][row['upstream'].index(u)]
            all_records.extend(row['upstream']);row['telemetry_boundary']['telemetry_ready']=rd
            write(r/'evidence'/(cid+'.json'),row);write(r/'telemetry'/(cid+'.ready.json'),rd);write(r/'telemetry'/(cid+'.done.json'),dn)
            (r/'telemetry'/(cid+'.ndjson')).write_text(''.join(json.dumps(s)+'\n'for s in ss))
            runrows.append({'id':cid,'streams':5,'sequences':sequences,'elapsed_ms':start*100})
        write(r/'evidence/mock-final.json',{'total':51,'effects':51,'active':0,'exceeded':False,'records':all_records})
        write(r/'evidence/account-cleanup.json',{'failures':0,'ambiguous_intent':False,'remaining_resources':[]});write(r/'resource-cleanup.json',{'failures':0})
        write(r/'run.json',{'schema':'rrsub2profile-run-v1','status':'COMPLETE','protocol':'responses','lane':'fixed','no_forced_gc':True,'new_image_and_binary':True,
          'source_manifest_sha256':sha(r/'stage/source-manifest.json'),'build':{'binary_sha256':sha(binary),'image_id':'sha256:'+'f'*64},
          'cleanup_failures':0,'scheduled_streams':[5]*10,'rows':runrows,'requests_completed':50,'measurement_elapsed_ms':160000,
          'namespace_pid':1,'identity':identity,'checkpoints':checkpoints,'baseline_ms':base,'missing_counters':['slots','orphan readers','billing queue']})
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_complete_data_path_decodes_profiles_and_replays_all_rss(self):
        result=analyze(self.root)
        self.assertEqual(result['status'],'DIAGNOSTIC_ONLY');self.assertEqual(len(result['checkpoints']),11)
        self.assertEqual(result['historical_20_rss_return'],'FAIL (unchanged)')
        self.assertEqual(result['physical_interval_rss'],'NOTPROVEN')
        self.assertNotIn('PASS',result['leak_or_plateau_verdict'])
        self.assertEqual(result['slopes']['all_checkpoints']['heap_inuse'],0)
        self.assertEqual(result['slopes']['all_checkpoints']['per_burst']['total_alloc'],150)
    def test_missing_profile_checkpoint_identity_cycles_and_cleanup_rejected(self):
        cases=[('profiles/checkpoint-003-heap.pb.gz',None),('profiles/checkpoint-004.json',lambda x:x[0].__setitem__('before_num_gc',999)),
            ('profiles/checkpoint-004.json',lambda x:x[0].__setitem__('checkpoint',5)),
            ('run.json',lambda x:x.__setitem__('requests_completed',49)),('run.json',lambda x:x.__setitem__('status','PARTIAL')),
            ('evidence/account-cleanup.json',lambda x:x.__setitem__('ambiguous_intent',True)),
            ('evidence/memory-responses-8-5-b02.json',lambda x:x.__setitem__('active_at_boundary',1))]
        for name,mut in cases:
            p=self.root/name;before=p.read_bytes()
            try:
                if mut is None:p.unlink()
                else:
                    x=json.loads(before);mut(x);write(p,x)
                with self.subTest(name=name),self.assertRaises((ContractError,KeyError,ValueError)):analyze(self.root)
            finally:p.write_bytes(before)
