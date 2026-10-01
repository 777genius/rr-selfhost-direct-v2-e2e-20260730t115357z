"""Bounded offline custody/raw aggregate audit; no product code or external calls."""
from pathlib import Path
import json,hashlib,sys,math
ROOT=Path(__file__).resolve().parent.parent; OUT=ROOT/'sub2api-memory-final-audit'; I=ROOT/'.spike-inputs'
sys.dont_write_bytecode=True
sys.path.insert(0,str(I/'profile-analyzer'))
from contracts import samples_gate,checkpoint_gate,slope
from pprof_decode import decode
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def emit(n,d):(OUT/n).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
ledger={}
for rel,h in read(I/'INPUT-HASHES.json').items():
 p=I/rel; assert sha(p)==h,rel;ledger[rel]={'sha256':h,'bytes':p.stat().st_size}
old=read(I/'old-inputs/INPUT-HASHES.json')
for rel,h in old.items(): assert sha(I/'old-inputs'/rel)==h,rel
merged=read(ROOT/'sub2api-native-merged/merged-hashes.json'); source=[]
for p in (I/'old-inputs/source').rglob('*.go'):
 rel=p.relative_to(I/'old-inputs/source').as_posix();key='backend/internal/'+rel if '/' in rel else 'backend/internal/repository/usage_log_repo.go'
 assert sha(p)==merged[key];source.append({'input':str(p.relative_to(ROOT)),'merged_path':key,'sha256':sha(p)})
assert len(source)==1377
insert=I/'usage_log_repo_insert.go'; key='backend/internal/repository/usage_log_repo_insert.go';assert sha(insert)==merged[key]=='5e10557e70be455a904bd40f3a695fd39d2aad5fe3b01eb1cb639d829ac11954'
source.append({'input':str(insert.relative_to(ROOT)),'merged_path':key,'sha256':sha(insert)})
bind=read(I/'actual-public-raw/source-binding.json'); manifest=read(I/'expected-manifest.json'); runs={};count=0
for lane in ['responses','messages','responses-control','messages-control']:
 rdir=I/'actual-public-raw'/lane;r=read(rdir/'run.json');build=read(rdir/'build-receipt.json')
 assert r['status']=='COMPLETE' and r['no_forced_gc'] and r['new_image_and_binary']
 assert r['source_manifest_sha256']==sha(rdir/'source-manifest.json')==sha(I/'expected-manifest.json')
 assert build==r['build'];assert build['binary_sha256']==manifest['reviewed_source']['binary_sha256']==bind['actual_profile_binary_sha256']
 assert build['base_image_id']==manifest['reviewed_source']['base_image']
 rows=[json.loads(x) for x in (rdir/'profiles/runtime.ndjson').read_text().splitlines()];index=samples_gate(rows,r['namespace_pid']);points=[]
 summary=read(I/'old-inputs'/((lane.split('-')[0])+'-analysis.json')) if '-control' not in lane else None
 for cp in r['checkpoints']:
  n=cp['checkpoint'];ack=read(rdir/'profiles'/f'checkpoint-{n:03d}.json');checkpoint_gate(ack,n,index,r['namespace_pid']);cur=index[ack[0]['before_sequence']]
  profiles={k:decode(rdir/'profiles'/f'checkpoint-{n:03d}-{k}.pb.gz',k) for k in ['heap','allocs','goroutine']};count+=3
  if summary:
   s=summary['checkpoints'][n];assert profiles==s['profiles_sampled_weighted']
   for dest,src in [('heap_alloc_allocator','heap_alloc'),('heap_objects_allocator','heap_objects'),('heap_inuse','heap_inuse'),('heap_idle','heap_idle'),('heap_released','heap_released'),('total_alloc','total_alloc'),('mallocs','mallocs'),('frees','frees'),('goroutines','goroutines'),('num_gc','num_gc')]:assert s[dest]==cur[src],(lane,n,dest)
   assert cp['elapsed_ms']==s['elapsed_ms'];assert all(a['before_num_gc']==a['after_num_gc']==cur['num_gc'] for a in ack)
  points.append({'checkpoint':n,'elapsed_ms':cp['elapsed_ms'],'runtime':cur,'profiles':profiles})
 if summary:
  for label,ps in [('all_checkpoints',summary['checkpoints']),('postwarmup_after_two_bursts',summary['checkpoints'][3:])]:
   xs=[p['elapsed_ms']/1000 for p in ps]
   for k,v in summary['slopes'][label].items():
    if k in ps[0]:actual=slope(xs,[p[k] for p in ps])
    elif k.startswith('sampled_heap_') and k.endswith('_per_second'):actual=slope(xs,[p['profiles_sampled_weighted']['heap'][k[len('sampled_heap_'):-len('_per_second')]] for p in ps])
    elif k=='rss_bytes_per_second':actual=slope(xs,[p['rss_bytes'] for p in ps])
    else:continue
    assert math.isclose(actual,v,rel_tol=1e-10,abs_tol=1e-8),(lane,k)
 runs[lane]={'identity':r['identity'],'build':build,'runtime_samples':len(rows),'checkpoints':points,'raw_run_sha256':sha(rdir/'run.json')}
native={}
for protocol in ['responses','messages']:
 d=read(I/f'actual-native-load-{protocol}.json');assert d['source']['binary_sha256']==bind['native']['binary_sha256'];assert d['source']['image_id']==bind['native']['image_id']
 assert len(d['results'])==10;assert all(x['functional_status']=='PASS' and x['empirical_status']=='FAIL' and x['physical_interval_status']=='NOTPROVEN' for x in d['results'])
 native[protocol]={'functional_PASS':10,'strict_RSS_FAIL':10,'physical_interval':'NOTPROVEN','evidence_sha256':sha(I/f'actual-native-load-{protocol}.json')}
emit('input-hash-ledger.json',{'verified_current_entries':len(ledger),'verified_old_entries':len(old),'public_raw_files':sum(k.startswith('actual-public-raw/') for k in ledger),'ledger_sha256':sha(I/'INPUT-HASHES.json'),'entries':ledger})
emit('source-verification.json',{'original_go_files':1377,'new_exact_insert_pin':source[-1],'files':source})
emit('raw-verification.json',{'decoded_profiles':count,'runs':runs,'native':native,'binding_receipts':bind})
print(json.dumps({'verified_inputs':len(ledger),'old_inputs':len(old),'source_files':len(source),'profiles':count,'native':'20 functional PASS / 20 strict RSS FAIL'}))
