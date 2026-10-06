"""Executable behavioral tests using numeric data and binary protobuf fixtures.
No source pattern assertion substitutes for runtime/handler tests.
"""
import copy, gzip, importlib.util, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from contracts import *
from pprof_decode import decode
from analyze import compare
OWN=Path(__file__).resolve().parent

def vint(n):
    b=bytearray()
    while n>=128:b.append((n&127)|128);n>>=7
    b.append(n);return bytes(b)
def fld(k,v):
    return vint(k*8)+(vint(v)) if type(v) is int else vint(k*8+2)+vint(len(v))+v

def proto(kind='heap',values=None,label=True):
    names=['alloc_objects','alloc_space','inuse_objects','inuse_space'] if kind!='goroutine' else ['goroutine']
    strings=['','count','bytes',*names]
    result=b''
    for n in names:result+=fld(1,fld(1,strings.index(n))+fld(2,strings.index('bytes' if n.endswith('space') else 'count')))
    values=values or ([100,1000,10,100] if kind!='goroutine' else [3])
    sample=fld(2,b''.join(vint(n if n>=0 else n+2**64) for n in values))
    if label and kind!='goroutine':sample+=fld(3,fld(1,2)+fld(3,64)) # real runtime's numeric bytes label
    result+=fld(2,sample)
    for s in strings:result+=fld(6,s.encode())
    result+=fld(12,512*1024 if kind!='goroutine' else 1)
    return result

def row(n=5):
    r={'id':'memory-responses-8-5-b01','protocol':'responses','functional_status':'PASS','stop_required':False,'unknown_identity':False,
      'exceeded':False,'active_at_boundary':0,'upstream_attempts_total':n,'upstream_effects_total':n,
      'attempt_sequences':list(range(1,n+1)),'downstream':{'requests':n,'successful':n,'bytes':8*MIB*n,'max_frame_bytes':2*MIB-8},
      'upstream':[], 'memory_envelope':{'empirical_qualified_status':'FAIL','physical_interval_rss_status':'NOTPROVEN'}}
    r['admitted_request_ids']=[r['id']+f'.r{j:02d}' for j in range(1,n+1)]
    r['request_results']=[{'id':id,'bytes':8*MIB,'max_frame_bytes':2*MIB-8,'text_delta_bytes':5000,'comments':1,'http_status':200,'transport':None,'failed':False,'malformed':False,'tool_id':'tool','duration_ms':1000,'terminal_ms':900,'client_close_ms':1000} for id in r['admitted_request_ids']]
    r['upstream']=[{'id':r['admitted_request_ids'][i-1],'identity':'responses','protocol':'responses','bytes':8*MIB,'effects':1,'finished':True,'close_ms':1000.,'terminal_ms':900.,'sequence':i} for i in range(1,n+1)]
    return r

def samples(count=8):
    rows=[]
    for i in range(count):
        r={k:0 for k in SAMPLE_INTS};r.update(schema=1,sequence=i+1,pid=1,heap_alloc=100,heap_objects=5,heap_inuse=4096,
          heap_idle=4096,heap_released=2048,heap_sys=8192,total_alloc=100+i,mallocs=10+i,frees=5+i,num_gc=i//4,
          last_gc_unix_ns=(i//4)*10000,goroutines=5,mem_profile_rate=512*1024,start_ms=1000.+i*100,end_ms=1001.+i*100,duration_ms=1.)
        rows.append(r)
    return rows

def cp(rows):
    return [{'schema':1,'checkpoint':0,'kind':k+1,'before_sequence':k*2+1,'after_sequence':k*2+2,
      'before_num_gc':rows[k*2]['num_gc'],'after_num_gc':rows[k*2+1]['num_gc'],'pid':1,
      'start_ms':rows[k*2]['end_ms'],'end_ms':rows[k*2+1]['start_ms']} for k in range(3)]

class StrictContracts(unittest.TestCase):
    def test_schedule_exact_requests_repetitions(self):
        self.assertEqual(schedule('fixed'),[5]*10);self.assertEqual(schedule('staircase'),[1]*10+[5]*10+[20]*5)
        self.assertEqual(sum(schedule('staircase')),160);self.assertEqual(sum(schedule('fixed')),50)
        self.assertEqual(len(schedule('staircase')),25);self.assertEqual(schedule('control'),[])
        with self.assertRaises(ContractError):schedule('infinite')
    def test_jsonl_complete_duplicate_and_nonfinite(self):
        self.assertEqual(jsonl('{"x":1}\n{"x":2}\n'),[{'x':1},{'x':2}])
        for bad in ['{"x":1}', '{"x":1}\n\n','{"x":NaN}\n','{"x":1,"x":2}\n','[]\nprose\n','']:
            with self.subTest(bad=bad),self.assertRaises(ContractError):jsonl(bad)
        self.assertFalse(number(float('inf')));self.assertFalse(number(True));self.assertFalse(number('1'));self.assertFalse(number(10**1000))
    def test_burst_finite_fullframe_and_attempt_effect_contract(self):
        self.assertEqual(burst_gate(row(),5,'responses'),[1,2,3,4,5])
        def check(mut):
            r=row();mut(r)
            with self.assertRaises(ContractError):burst_gate(r,5,'responses')
        for k in ['upstream_attempts_total','upstream_effects_total','active_at_boundary']:
            for bad in [None,'0',True,{},[],float('inf')]:check(lambda r,k=k,bad=bad:r.__setitem__(k,bad))
        for k in ['bytes','max_frame_bytes','requests','successful']:
            for bad in [None,'5',True,{},[],float('inf'),-1]:check(lambda r,k=k,bad=bad:r['downstream'].__setitem__(k,bad))
        for key,bad in [('effects',0),('bytes',8*MIB-1),('finished',False),('identity','UNKNOWN'),('close_ms',None),('terminal_ms',None),('sequence',2)]:
            check(lambda r,key=key,bad=bad:r['upstream'][0].__setitem__(key,bad))
        check(lambda r:r['admitted_request_ids'].pop());check(lambda r:r['request_results'].pop());check(lambda r:r['upstream'][0].__setitem__('id',r['upstream'][1]['id']));check(lambda r:r['request_results'][0].__setitem__('client_close_ms',None))
        check(lambda r:r.__setitem__('active_at_boundary',1));check(lambda r:r.__setitem__('stop_required',True))
        check(lambda r:r['memory_envelope'].__setitem__('empirical_qualified_status','NOT RUN'))
        check(lambda r:r['memory_envelope'].__setitem__('physical_interval_rss_status','PASS'))
    def test_runtime_fields_no_coercion_identity_cycles_gaps(self):
        s=samples();self.assertEqual(len(samples_gate(s,1)),8)
        for key in SAMPLE_INTS+SAMPLE_NUMS:
            for bad in [None,'0',True,{},[],float('nan'),float('inf'),-1]:
                a=copy.deepcopy(s);a[3][key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ContractError):samples_gate(a,1)
        for mutate in [lambda a:a[3].pop('num_gc'),lambda a:a[3].__setitem__('pid',2),
                       lambda a:a[5].__setitem__('num_gc',0),lambda a:a[3].__setitem__('num_forced_gc',1),
                       lambda a:a[3].__setitem__('end_ms',1500),lambda a:a[3].__setitem__('sequence',3),
                       lambda a:a[3].__setitem__('heap_released',8192),lambda a:a[3].__setitem__('mem_profile_rate',1)]:
            a=copy.deepcopy(s);mutate(a)
            with self.assertRaises(ContractError):samples_gate(a,1)
    def test_checkpoint_missing_identity_cycle_forgery_and_replay(self):
        s=samples();idx=samples_gate(s,1);good=cp(s);checkpoint_gate(good,0,idx,1)
        for mut in [lambda r:r.pop(),lambda r:r[0].__setitem__('checkpoint',1),lambda r:r[1].__setitem__('pid',2),
                    lambda r:r[0].__setitem__('before_num_gc',4),lambda r:r[2].__setitem__('after_sequence',999),
                    lambda r:r[1].__setitem__('before_sequence',2),lambda r:r[0].__setitem__('kind',3),lambda r:r[0].pop('start_ms')]:
            a=copy.deepcopy(good);mut(a)
            with self.assertRaises(ContractError):checkpoint_gate(a,0,idx,1)
    def test_binary_profile_actual_field_layout_and_corruption(self):
        with tempfile.TemporaryDirectory(dir=OWN/'evidence') as td:
            p=Path(td)/'heap.pb.gz';p.write_bytes(gzip.compress(proto()))
            self.assertEqual(decode(p,'heap'),{'alloc_objects':100,'alloc_space':1000,'inuse_objects':10,'inuse_space':100})
            p.write_bytes(gzip.compress(proto('goroutine')));self.assertEqual(decode(p,'goroutine'),{'goroutine':3})
            for b in [proto(values=[1,10,5,100]),proto(values=[1,-1,0,0]),proto()+b'\x12\xff',b'\x00']:
                p.write_bytes(gzip.compress(b))
                with self.assertRaises((ContractError,ValueError)):decode(p,'heap')
            p.unlink()
            with self.assertRaises(ContractError):decode(p,'heap')
    def test_slopes_known_observations_and_control_difference(self):
        self.assertEqual(slope([0,1,2],[4,7,10]),3)
        for bad in [[None,1,2],[True,1,2],['0',1,2]]:
            with self.assertRaises(ContractError):slope(bad,[4,7,10])
        p={'checkpoint':0,'heap_inuse':100,'heap_released':50,'goroutines':2,'profiles_sampled_weighted':{'heap':{'inuse_space':10}}}
        w={'protocol':'responses','lane':'fixed','checkpoints':[p]};c=copy.deepcopy(w);c['lane']='control'
        c['checkpoints'][0]['heap_inuse']=60
        self.assertEqual(compare(w,c)['checkpoints'][0]['allocator_heap_inuse_difference'],40)
        c['protocol']='messages'
        with self.assertRaises(ContractError):compare(w,c)
    def test_root_adapter_removes_only_verified_owned_container(self):
        spec=importlib.util.spec_from_file_location('driver',OWN/'root-driver.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        d=m.Driver({},Path('/unused/test12345678'),'responses','fixed',None);d.code=Path('/unused/code');d.private=Path('/unused/private');d.evidence=Path('/unused/evidence');d.telemetry=Path('/unused/telemetry')
        calls=[]
        def docker(*args,**kw):calls.append(args);return b'0\n'
        d.docker=docker;d.create=lambda *a,**k:'owned-operator';d.containers=['owned-operator'];d.own=lambda n:{'Id':'verified-id'}
        d.node('burst');self.assertIn(('rm','-v','verified-id'),calls);self.assertEqual(d.containers,[])
        d.containers=['owned-operator'];d.own=lambda n:require(False,'OWNERSHIP_CHANGED');calls.clear()
        with self.assertRaises(ContractError):d.node('burst')
        self.assertFalse(any(c[0]=='rm' for c in calls))

if __name__=='__main__': unittest.main(verbosity=2)
