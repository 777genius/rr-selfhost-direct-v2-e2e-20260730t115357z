#!/usr/bin/env python3
"""Offline source/summary audit only; never executes Go or changes input bytes."""
from pathlib import Path
import hashlib, json, math, re
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'sub2api-memory-final-audit'
INPUT=ROOT/'.spike-inputs'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(name, value): (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def slope(xs,ys):
    xm=sum(xs)/len(xs);ym=sum(ys)/len(ys)
    return sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/sum((x-xm)**2 for x in xs)
expected=json.loads((INPUT/'INPUT-HASHES.json').read_text())
ledger={}
for rel,h in expected.items():
    p=INPUT/rel
    actual=sha(p)
    assert actual==h,rel
    ledger['.spike-inputs/'+rel]={'expected_sha256':h,'actual_sha256':actual,'bytes':p.stat().st_size}
merged=json.loads((ROOT/'sub2api-native-merged/merged-hashes.json').read_text())
source_verified=[]
for p in (INPUT/'source').rglob('*.go'):
    rel=p.relative_to(INPUT/'source').as_posix()
    key='backend/internal/'+rel if '/' in rel else 'backend/internal/repository/usage_log_repo.go'
    assert sha(p)==merged[key],key
    source_verified.append({'input':'.spike-inputs/source/'+rel,'merged_path':key,'sha256':sha(p)})
patch=sha(INPUT/'reviewed-production.patch')
assert patch=='16bc1644e564847f0565dffd765af6c7e0c7a70ac5677147d3166e20c90923a5'
metrics=('heap_alloc_allocator','heap_objects_allocator','heap_inuse','heap_released','total_alloc','mallocs','goroutines')
protocols={}
for protocol in ('responses','messages'):
    d=json.loads((INPUT/(protocol+'-analysis.json')).read_text());c=d['checkpoints']
    assert d['status']=='DIAGNOSTIC_ONLY' and d['live_heap_attribution']=='INCONCLUSIVE'
    assert len(c)==11 and all(p['streams']==5 for p in c[1:])
    assert all(p['natural_cycles_after_end']==0 and not p['postburst_profile_cycle_eligible'] for p in c[1:])
    assert all(p['profile_gc_stable'] and all(b['before_num_gc']==b['after_num_gc']==p['num_gc'] for b in p['profile_gc_brackets']) for p in c)
    recomputed={}
    for label,points in [('all_checkpoints',c),('postwarmup_after_two_bursts',c[3:])]:
        xs=[p['elapsed_ms']/1000 for p in points]
        z={k:slope(xs,[p[k] for p in points]) for k in metrics}
        for k in ('inuse_space','inuse_objects','alloc_space','alloc_objects'):
            z['sampled_heap_'+k+'_per_second']=slope(xs,[p['profiles_sampled_weighted']['heap'][k] for p in points])
        if all('rss_bytes' in p for p in points):z['rss_bytes_per_second']=slope(xs,[p['rss_bytes'] for p in points])
        for k,v in z.items():assert math.isclose(v,d['slopes'][label][k],rel_tol=1e-10,abs_tol=1e-8),(protocol,k)
        recomputed[label]=z
    top=(INPUT/'pprof-top'/f'{protocol}-010.txt').read_text()
    assert '27.47MB' in top and 'NewContentModerationService' in top
    final=c[-1];initial=c[0];control=d['matched_control']['checkpoints'][-1]
    protocols[protocol]={'analysis_sha256':sha(INPUT/(protocol+'-analysis.json')),'run_sha256_reference':d['input_run_sha256'],
        'natural_gc_baseline_end':[initial['num_gc'],final['num_gc']], 'goroutines_baseline_end':[initial['goroutines'],final['goroutines']],
        'cycles_after_each_burst_end':[p['natural_cycles_after_end'] for p in c[1:]],
        'profile_inuse_baseline_end_bytes':[initial['profiles_sampled_weighted']['heap']['inuse_space'],final['profiles_sampled_weighted']['heap']['inuse_space']],
        'allocator_heap_alloc_baseline_end_bytes':[initial['heap_alloc_allocator'],final['heap_alloc_allocator']],
        'allocator_heap_inuse_baseline_end_bytes':[initial['heap_inuse'],final['heap_inuse']],
        'end_heap_idle_bytes':final['heap_idle'],'end_heap_released_bytes':final['heap_released'],
        'end_unreleased_idle_span_bytes':final['heap_idle']-final['heap_released'],
        'end_rss_bytes':final['rss_bytes'],'end_workload_minus_idle_control_rss_bytes':control['rss_difference'],
        'allocation_churn_bytes':final['total_alloc']-initial['total_alloc'],
        'diagnostic_empirical_pass_count':sum(p['empirical_return']=='PASS' for p in c[1:]),
        'diagnostic_empirical_fail_count':sum(p['empirical_return']=='FAIL' for p in c[1:]),
        'recomputed_slopes':recomputed,'live_attribution':'INCONCLUSIVE','physical_interval_rss':'NOTPROVEN'}
mod=(INPUT/'source/service/content_moderation.go').read_text()
eng=(INPUT/'source/service/content_moderation_engines.go').read_text()
assert 'make(chan contentModerationTask, maxContentModerationQueueSize)' in mod
assert re.search(r'maxContentModerationQueueSize\s*=\s*100000',mod)
assert 'Body               []byte' in mod
assert mod.count('input:')>=2
assert not re.search(r'(?:input|task\.input)\.Body\s*=',mod)
assert all(mod[:m.start()].count('\n')+1<1063 for m in re.finditer(r'input\.Body',mod))
assert 's.keyHealth[hash] = state' in mod
assert not re.search(r'delete\(s\.keyHealth',mod+eng)
# Go amd64 layout from declared fields; no compiler execution. Natural alignment.
layout={'ContentModerationCheckInput':[('flag',1,1),('RequestID',16,8),('UserID',8,8),('UserEmail',16,8),('APIKeyID',8,8),('APIKeyName',16,8),('GroupID',8,8),('GroupName',16,8),('Endpoint',16,8),('Provider',16,8),('Model',16,8),('Protocol',16,8),('Body',24,8)]}
def size(fields):
    offset=0;align=max(a for _,_,a in fields)
    for _,s,a in fields:offset=(offset+a-1)//a*a+s
    return (offset+align-1)//align*align
input_size=size(layout['ContentModerationCheckInput'])
task_size=size([('input',input_size,8),('content',40,8),('inputHash',16,8),('log',8,8),('config',8,8),('recordHash',1,1),('applySideEffects',1,1),('enqueuedAt',24,8)])
assert input_size==184 and task_size==288
batch_input=(INPUT/'source/usage_log_repository.go').read_text()
assert 'ensureBestEffortBatcher' not in batch_input
supplements=['sub2api-native-merged/merged-hashes.json','sub2api-native-merged/manifest.json','sub2api-native-merged-review/evidence.json','sub2api-native-merged-review/REPORT.md','sub2api-memory-profile/SEMANTICS.md','sub2api-transport-r4/adapter.mjs']
for rel in supplements:
    p=ROOT/rel;ledger[rel]={'actual_sha256':sha(p),'bytes':p.stat().st_size,'role':'supporting reference'}
ledger['.spike-inputs/INPUT-HASHES.json']={'actual_sha256':sha(INPUT/'INPUT-HASHES.json'),'bytes':(INPUT/'INPUT-HASHES.json').stat().st_size,'role':'supplied full ledger'}
emit('input-hash-ledger.json',{'schema':'memory-final-input-custody-v1','verified_supplied_entries':len(expected),'entries':ledger})
emit('source-verification.json',{'verified_count':len(source_verified),'files':source_verified,'repository_alias':'source/usage_log_repository.go == backend/internal/repository/usage_log_repo.go; insertion/batcher shard not supplied'})
findings={
'schema':'sub2api-memory-final-audit-v1','goal_status':json.loads((OUT/'blocked-audit.json').read_text())['goal_status'] if (OUT/'blocked-audit.json').exists() else 'active','status':'DIAGNOSTIC_ONLY','production_recommendation':'NO_PRODUCTION_GO','production_patch_sha256':patch,
'identity_user_reported_only':{'native_image_id':'sha256:c656447c1b79706e67f71fe49ada0f0f840e26eba798597e6751917ddc691bd1','native_binary_sha256':'5e28306e531eac0abea49811f116dbbddb233c4e52ce3f7d63f9c71d949632fd','profile_binary_sha256_prefix':'798','profile_full_binary_hash_available':False,'final_native_functional_pass':20,'final_native_strict_rss_fail':20},
'protocols':protocols,'scope_user_reported':{'streams':5,'response_payload_bytes_per_request':8388608,'bursts_per_protocol':10,'known_requests_total':100,'matched_idle_controls':True},
'fixed_allocation':{'id':'M1','classification':'static_service_queue_capacity','source':'content_moderation.go:586-614','queue_capacity':100000,'derived_amd64_task_bytes':task_size,'derived_ring_bytes':task_size*100000,'derived_ring_mib':task_size*100000/1048576,'sampled_constructor_top_mib':27.47,'cause_share_of_rss':'UNPROVEN','allocation_time_relative_to_baseline':'UNPROVEN; sampled startup omission can reflect profile lag'},
'findings':[{'id':'M2','classification':'SOURCE_CONFIRMED_UNNECESSARY_BODY_REFERENCE','source':'content_moderation.go:318-332,1178-1293','evidence':'Both enqueue functions copy input including Body; worker consumes extracted content/log plus metadata; all input.Body reads are before enqueue helpers. No clearing assignment. Pending tasks therefore keep original body backing storage alive.','bound':'Count bounded by physical 100000-slot channel; byte budget not enforced in enqueue. Not an unbounded queue or proof of indefinite leak.','measured_run_cause':'UNPROVEN; moderation state/queue occupancy not supplied','proposed_minimal_fix':'Clear Body in the local metadata copy before both enqueue task constructions.','independent_red_green':'With worker held and no GC, enqueue large-body tasks through both modes. Red: stored Body nonnil. Green: stored Body nil, same extracted moderation content/metadata/log/action and queue/drop behavior; release/drain reaches zero. Do not use RSS or forced GC as this oracle.'},
{'id':'M3','classification':'SOURCE_CONFIRMED_CHURN_DEPENDENT_MAP_RETENTION','source':'content_moderation.go:545,2338-2449;content_moderation_engines.go:99-159','evidence':'Per hash health entries are inserted; configuration removal/replacement does not prune map; no map deletion in supplied service source. Distinct used configurations accumulate state.','measured_run_cause':'UNPROVEN; fixed workload has no demonstrated configuration churn','proposed_minimal_fix':'Bound inactive historical health state or prune removed inactive entries with concurrency-safe handling of in-flight calls.','independent_red_green':'Offline fixture uses synthetic hash identifiers to exercise repeated insert/retire cycles. Red: inactive historical map grows with cycles. Green: bounded historical state while active accounting/freeze behavior remains correct and concurrent completion cannot resurrect unlimited retired state.'},
{'id':'M4','classification':'NO_PROVABLE_STREAM_REPLAY_OR_SPOOL_DEFECT_IN_INSPECTED_PATHS','source':'gateway_anthropic_passthrough.go:442-495;openai_gateway_passthrough.go:1938-1951,2000-2018;openai_first_output_timeout.go:24-29,145-260;sse_scanner_buffer_pool.go;native_api_key_cancellation.go:34-59','evidence':'Messages uses one queued event, scanner-owned 64KiB pooled seed returned on reader exit, trusted cancellation body close and bounded reader join. Responses strict native stage 64KiB RAM/8MiB aggregate, anonymous spool, strict fail closed, deferred Close and commit release; scalar scan runs on forwarding goroutine. Expanded scanner buffer is not returned to seed pool.','limits':'Configured frame limits still permit large transient Scanner/Text copies; noncooperative bodies/default drain and exact owners require runtime evidence. No universal leak-free verdict.'},
{'id':'M5','classification':'USAGE_BATCH_SOURCE_INCOMPLETE','source':'usage_log_repository.go:142-164;usage_record_worker_pool.go:143-193;pprof-top/messages-010.txt:10','evidence':'Outer pond queue is bounded with TrySubmit and drop/sync/sample overflow. Supplied repository file defines batch handles only; ensureBestEffortBatcher implementation lives in missing usage_log_repo_insert.go. Top attributes sampled 3.01MiB to batcher allocation stack.','verdict':'Cannot prove retained batch backing pointers, queue capacity, flush clearing, or per-request live ownership from this top.'}],
'empirical_criterion':{'meaning':'Last qualifying completed quiescent RSS and smaps sample near 5sec must both be <= burst pre-load baseline +32MiB; separate sampled peak and lifetime cgroup guards also apply.','implication':'Failure proves observed reclaim envelope not met, regardless of reachability or allocator explanation. It does not prove an indefinite leak or absolute RSS between samples.','production_risk':'Elevated resident high-water memory can reduce container headroom during repeated bursts, increase OOM risk and concurrency cost; unreachable heap/static costs still consume resident capacity until reclaimed.','stability':'FINITE_SCOPE_ONLY; counts and postwarmup sampled slopes do not establish a plateau. No production GO.'},
'limitations':['Raw runtime NDJSON, binary pprof/acks, original burst/READY/DONE receipts, complete profile binary/build/stdlib pins and idle-control raw records are not supplied in .spike-inputs; independent audit checks public analysis arithmetic and source/hash custody, not replay of canonical analyzer.','All 20 diagnostic endpoints have zero natural cycles after each end; inuse samples cannot identify current live per-request roots.','Final native all20 RSSFAIL is user-reported and retained; diagnostic run has 4 FAIL/16 PASS and must not replace final native verdict.','Exact RSS causal decomposition between garbage, reachable roots, static data, runtime caches, fragmentation and resident idle pages remains unproven.','Root final slot84 and three genuine canaries remain pending per user; no live polling or provider activity authorized.'],
'verification':{'supplied_hashes_verified':len(expected),'current_go_source_bytes_matching_merged_ledger':len(source_verified),'ols_slopes':'independently recomputed','source_layout':'derived offline for amd64, not compiler-measured','new_runtime_tests':'NOT RUN; no Go/Docker/root/network/auth/Git writes/subagents','input_ledger':'input-hash-ledger.json','input_ledger_sha256':sha(OUT/'input-hash-ledger.json'),'source_ledger':'source-verification.json'},
'goal_completion':'NOT_MARKED_COMPLETE: exact raw profile custody and usage batch insertion implementation missing; bounded audit handoff complete'}
emit('findings.json',findings)
print(json.dumps({'status':findings['status'],'hashes_verified':len(expected),'source_matches':len(source_verified),'natural_post_end_cycles':'all zero','ols':'verified','output':'sub2api-memory-final-audit/findings.json'}))
