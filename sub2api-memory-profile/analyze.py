#!/usr/bin/env python3
"""Independent body-free offline diagnosis. Reject incomplete or forged inputs.
Does not produce PASS for reliability or prove absence/presence of a leak.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess
OWN=Path(__file__).resolve().parent
from contracts import require, strict_json, jsonl, schedule, burst_gate, samples_gate, checkpoint_gate, slope, number, integer
from pprof_decode import decode

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    require(p.is_file() and p.stat().st_size<=16*1024**2,'MISSING_OR_OVERSIZED_EVIDENCE')
    return strict_json(p.read_text())

LEGACY_MANIFEST_SHA256='8a8103f73486912aa86f972fd2914bbff295d91126483447930da15ca227f704'

def expected_source_manifest(path=None):
    legacy=OWN/'source-manifest.json'
    require(sha(legacy)==LEGACY_MANIFEST_SHA256,'LEGACY_MANIFEST_CHANGED')
    path=legacy if path is None else path
    require(path.is_file() and path.stat().st_size<=16*1024**2,'MISSING_OR_OVERSIZED_EVIDENCE')
    data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    sm=strict_json(data.decode())
    if digest!=LEGACY_MANIFEST_SHA256:
        validate_reviewed_manifest(sm)
    return digest,sm

def analyze(root, expected_manifest=None):
    # Authorize the source input before reading any run evidence.
    expected_hash,sm=expected_source_manifest(expected_manifest)
    run=read(root/'run.json')
    require(run['schema']=='rrsub2profile-run-v1' and run['status']=='COMPLETE','INCOMPLETE_RUN')
    require(run['protocol'] in ('responses','messages'),'PROTOCOL_REQUIRED')
    require(run['no_forced_gc'] is True and run['new_image_and_binary'] is True,'INSTRUMENTATION_ATTESTATION')
    source=root/'stage/source-manifest.json'
    require(sha(source)==run['source_manifest_sha256']==expected_hash,'SOURCE_MANIFEST_CHANGED')
    require(sm['tag']=='rrsub2profile' and sm['go_version']=='go1.27.1','BUILD_TAG_TOOLCHAIN')
    if 'reviewed_source' in sm:
        validate_reviewed_manifest(sm)
        require(run['build']['binary_sha256']==sm['reviewed_source']['binary_sha256'],'REVIEWED_BINARY_PIN')
    for name,h in sm['source_after_sha256'].items():
        require(sha(root/'stage'/name)==h,'SOURCE_AFTER_HASH')
    for name,h in sm['operator_after_sha256'].items():
        require(sha(root/'stage/code'/name)==h,'OPERATOR_AFTER_HASH')
    require(run['build']['binary_sha256']==sha(root/'build/profile-server'),'BINARY_CHANGED')
    require(run['build']['binary_sha256']!=sm['historical']['binary_sha256'] and run['build']['image_id']!=sm['historical']['image_id'],'SAME_IMAGE_OVERCLAIM')
    require(run['cleanup_failures']==0 and read(root/'resource-cleanup.json')['failures']==0,'RESOURCE_CLEANUP')
    cleanup=read(root/'evidence/account-cleanup.json')
    require(cleanup['failures']==0 and cleanup['ambiguous_intent'] is False and cleanup['remaining_resources']==[],'ACCOUNT_CLEANUP')
    lane=run['lane'];expected=schedule(lane)
    require(run['scheduled_streams']==expected,'SCHEDULE_CHANGED')
    setup=read(root/'evidence/setup.json');final=read(root/'evidence/mock-final.json')
    require(setup['protocol']==run['protocol'] and setup['healthy_control'] is True,'WARMUP_CONTROL')
    prep=setup['preparation_state']
    require(all(integer(x[k]) for x in (prep,final) for k in ('total','effects','active')),'MOCK_NUMERIC')
    require(prep['active']==final['active']==0 and prep['exceeded'] is final['exceeded'] is False,'MOCK_ACTIVE_EFFECTS')
    require(len(prep['records'])==prep['total'] and len(final['records'])==final['total'],'MISSING_ATTEMPTS')
    require(all(r['identity'] in ('responses','messages') and number(r['close_ms']) and integer(r['effects']) for r in final['records']),'AMBIGUOUS_EFFECTS')
    require(sum(r['effects'] for r in final['records'])==final['effects'],'EFFECT_AGGREGATE')
    require(final['records'][:len(prep['records'])]==prep['records'],'PREPARATION_MUTATED')
    require(len(run['rows'])==len(expected) and run['requests_completed']==sum(expected),'MISSING_BURSTS')
    require(number(run['measurement_elapsed_ms']) and run['measurement_elapsed_ms']<=600000,'SUPERVISOR_BOUND')
    require(integer(run['namespace_pid']) and run['namespace_pid']>0,'NAMESPACE_PID')
    identity=run['identity']
    require(all(integer(identity[k]) and identity[k]>0 for k in ('engine_pid','pid_start_ticks','cgroup_device','cgroup_inode','exe_device','exe_inode')),'PROCESS_IDENTITY')
    rt=root/'profiles/runtime.ndjson'
    require(rt.stat().st_size<=16*1024**2,'RUNTIME_SIZE')
    rows=jsonl(rt.read_text());index=samples_gate(rows,run['namespace_pid'])
    require(len(run['checkpoints'])==len(expected)+1 if lane!='control' else len(run['checkpoints'])>2,'MISSING_CHECKPOINTS')
    points=[];sequences=[];elapsed=[];previous_cgroup_peak=0
    for i,cp in enumerate(run['checkpoints']):
        require(type(cp['checkpoint']) is int and cp['checkpoint']==i and number(cp['elapsed_ms']),'CHECKPOINT_ORDER')
        require(not elapsed or cp['elapsed_ms']>elapsed[-1],'CHECKPOINT_ELAPSED_ORDER');elapsed.append(cp['elapsed_ms'])
        ack=read(root/'profiles'/f'checkpoint-{i:03d}.json');checkpoint_gate(ack,i,index,run['namespace_pid'])
        if i: require(ack[0]['before_sequence']>last_sequence,'CHECKPOINT_REPLAY')
        last_sequence=ack[-1]['after_sequence']
        profiles={name:decode(root/'profiles'/f'checkpoint-{i:03d}-{name}.pb.gz',name) for name in ('heap','allocs','goroutine')}
        current=index[ack[0]['before_sequence']]
        point={'checkpoint':i,'elapsed_ms':cp['elapsed_ms'],'num_gc':current['num_gc'],
          'profile_gc_stable':ack[0]['before_num_gc']==ack[0]['after_num_gc'],
          'profile_gc_brackets':[{'kind':a['kind'],'before_num_gc':a['before_num_gc'],'after_num_gc':a['after_num_gc']} for a in ack],
          'heap_alloc_allocator':current['heap_alloc'],'heap_objects_allocator':current['heap_objects'],
          'heap_inuse':current['heap_inuse'],'heap_idle':current['heap_idle'],'heap_released':current['heap_released'],
          'total_alloc':current['total_alloc'],'mallocs':current['mallocs'],'frees':current['frees'],
          'goroutines':current['goroutines'],'profiles_sampled_weighted':profiles}
        if lane!='control' and i:
            spec=run['rows'][i-1];n=expected[i-1]
            require(spec['streams']==n,'CONCURRENCY_SCHEDULE')
            r=read(root/'evidence'/(spec['id']+'.json'));seq=burst_gate(r,n,run['protocol']);sequences.extend(seq)
            require(r['dedicated_resources']==setup['resources'],'ACCOUNT_RECREATED')
            require(spec['sequences']==seq,'CHECKPOINT_ATTEMPTS')
            ready=read(root/'telemetry'/(spec['id']+'.ready.json'));done=read(root/'telemetry'/(spec['id']+'.done.json'))
            rss=jsonl((root/'telemetry'/(spec['id']+'.ndjson')).read_text())
            for k in ('instance','engine_pid','pid_start_ticks','cgroup_path','cgroup_device','cgroup_inode','exe_device','exe_inode','container_id'):
                require(ready[k]==done[k]==identity[k] and all(x[k]==identity[k] for x in rss),'RSS_PROCESS_CHANGED')
            require(ready['first_sample']['cgroup_peak_bytes']>=previous_cgroup_peak,'ENGINE_OR_CGROUP_PEAK_RESTARTED')
            previous_cgroup_peak=rss[-1]['cgroup_peak_bytes']
            require(done['status']=='DONE' and number(done['full_tail_ms']) and done['full_tail_ms']>=5000,'MISSING_FULL_IDLE_TAIL')
            require(done['last_sample_ms']==rss[-1]['mono_ms'] and rss[-1]['sample_started_ms']-done['ended_ms']==done['full_tail_ms'],'DONE_IDENTITY_TIMES')
            for x in rss:
                require(all(number(x[k]) for k in ('mono_ms','sample_started_ms','sample_duration_ms','rss_bytes','smaps_rollup_rss_bytes','sockets')),'RSS_SCALARS')
            replay=subprocess.run(['node',str(OWN/'verify-rss.mjs'),str(root),spec['id']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
            require(replay.returncode==0,'INDEPENDENT_RSS_REPLAY_FAILED')
            endpoint=[x for x in rss if x['phase']=='quiescent' and x['mono_ms']<=done['ended_ms']+5000]
            require(endpoint and endpoint[-1]['mono_ms']>=done['ended_ms']+4750,'RSS_RETURN_ENDPOINT')
            require(index[ack[0]['before_sequence']]['start_ms']>=rss[-1]['mono_ms'],'PROFILE_BEFORE_TAIL_DONE')
            end_cycles=[x['num_gc'] for x in rows if x['end_ms']<=done['ended_ms']]
            require(end_cycles,'BURST_CYCLE_BOUNDARY_MISSING')
            point.update(streams=n,rss_bytes=endpoint[-1]['rss_bytes'],smaps_rss_bytes=endpoint[-1]['smaps_rollup_rss_bytes'],
              sockets=endpoint[-1]['sockets'],empirical_return=r['memory_envelope']['empirical_qualified_status'],
              natural_cycles_after_end=current['num_gc']-end_cycles[-1])
            # Two-cycle lag cannot be silently equated with current completed GC.
            point['postburst_profile_cycle_eligible']=point['profile_gc_stable'] and point['natural_cycles_after_end']>=2
        points.append(point)
    require(len(sequences)==len(set(sequences)),'DUPLICATE_REQUEST_ATTEMPTS')
    require(final['total']==prep['total']+sum(expected) and final['effects']==prep['effects']+sum(expected),'UNEXPECTED_ATTEMPT_OR_EFFECT')
    require(sorted(sequences)==sorted(r['sequence'] for r in final['records'][len(prep['records']):]),'MISSING_EXACT_REQUESTS')
    control=None
    if lane=='control':
        control=run['control_reference'];require(control and control['lane'] in ('fixed','staircase'),'TIME_CONTROL_UNMATCHED')
        require(len(points)==len(control['targets'])+1,'TIME_CONTROL_CHECKPOINTS')
        require(all(abs(p['elapsed_ms']-t['elapsed_ms'])<=1000 for p,t in zip(points[1:],control['targets'])),'TIME_CONTROL_DRIFT')
        control_rss=jsonl((root/'control-rss.ndjson').read_text())
        require(control_rss,'CONTROL_RSS_MISSING')
        for r in control_rss:
            require(all(r[k]==identity[k] for k in ('engine_pid','pid_start_ticks','container_id','exe_device','exe_inode')),'CONTROL_PID_CHANGED')
            require(all(number(r[k]) for k in ('mono_ms','rss_bytes','smaps_rollup_rss_bytes','sockets')),'CONTROL_RSS_NUMERIC')
        for p in points[1:]:
            target=run['baseline_ms']+p['elapsed_ms'];near=[r for r in control_rss if 0<=target-r['mono_ms']<=15000]
            require(near,'CONTROL_RSS_ENDPOINT_MISSING');p['rss_bytes']=near[-1]['rss_bytes'];p['smaps_rss_bytes']=near[-1]['smaps_rollup_rss_bytes'];p['sockets']=near[-1]['sockets']
    metrics=('heap_alloc_allocator','heap_objects_allocator','heap_inuse','heap_released','total_alloc','mallocs','goroutines')
    comparisons={}
    for label,series in (('all_checkpoints',points),('postwarmup_after_two_bursts',points[3:])):
        if len(series)<2:continue
        xs=[p['elapsed_ms']/1000 for p in series]
        comparisons[label]={k:slope(xs,[p[k] for p in series]) for k in metrics}
        for k in ('inuse_space','inuse_objects','alloc_space','alloc_objects'):
            comparisons[label]['sampled_heap_'+k+'_per_second']=slope(xs,[p['profiles_sampled_weighted']['heap'][k] for p in series])
        if lane=='fixed':
            comparisons[label]['per_burst']={k:slope([p['checkpoint'] for p in series],[p[k] for p in series]) for k in metrics}
        if all('rss_bytes' in p for p in series):
            comparisons[label]['rss_bytes_per_second']=slope(xs,[p['rss_bytes'] for p in series])
    natural=[r for a,r in zip(rows,rows[1:]) if r['num_gc']>a['num_gc']]
    return {'status':'DIAGNOSTIC_ONLY','lane':lane,'protocol':run['protocol'],'checkpoints':points,'slopes':comparisons,
      'observed_natural_cycle_allocator_samples':[{k:r[k] for k in ('sequence','end_ms','num_gc','heap_alloc','heap_objects','heap_inuse','heap_released')} for r in natural],
      'live_heap_attribution':'INCONCLUSIVE' if lane=='control' or not all(p.get('postburst_profile_cycle_eligible') for p in points[1:]) else 'SAMPLED_CYCLE_CORROBORATION_ONLY_ROOT_OWNERSHIP_UNVERIFIED',
      'missing_counters':run['missing_counters'],'historical_20_rss_return':'FAIL (unchanged)',
      'physical_interval_rss':'NOTPROVEN','leak_or_plateau_verdict':'UNPROVEN; compare fixed N5 against matched no-work control and inspect stack owners',
      'input_run_sha256':sha(root/'run.json')}

def validate_reviewed_manifest(sm):
    from launch_contracts import BASE,digest
    require(sha(OWN/'source-manifest.json')==LEGACY_MANIFEST_SHA256,'LEGACY_MANIFEST_CHANGED')
    legacy=read(OWN/'source-manifest.json')
    require(type(sm) is dict and set(sm)==set(legacy)|{'reviewed_source'},'REVIEWED_MANIFEST_FIELDS')
    r=sm['reviewed_source']
    require(type(r) is dict and set(r)=={'schema','base_manifest_sha256','base_image','binary_sha256','patches','reviewed_manifest_sha256'} and r['schema']=='rrsub2profile-reviewed-v1' and digest(r['reviewed_manifest_sha256']) and r.get('base_manifest_sha256')==sha(OWN/'source-manifest.json') and r.get('base_image')==BASE and digest(r.get('binary_sha256')),'REVIEWED_MANIFEST_BASE')
    require(type(r.get('patches')) is list and 1<=len(r['patches'])<=2,'REVIEWED_PATCH_LIST')
    expected=dict(legacy['source_after_sha256']);changed=set()
    for p in r['patches']:
        require(type(p) is dict and set(p)=={'sha256','files'} and digest(p['sha256']) and type(p['files']) is dict and p['files'],'REVIEWED_PATCH_FIELDS')
        for n,h in p['files'].items():
            require(type(n) is str and n.startswith('backend/') and Path(n).as_posix()==n and '..' not in Path(n).parts and n.endswith('.go') and n!='backend/cmd/server/rr_sub2_profile.go' and type(h) is dict and set(h)=={'before_sha256','after_sha256'} and (h['before_sha256'] is None or digest(h['before_sha256'])) and digest(h['after_sha256']) and (n not in expected if h['before_sha256'] is None else h['before_sha256']==expected.get(n)),'REVIEWED_SOURCE_SCOPE')
            expected[n]=h['after_sha256'];changed.add(n)
    require(sm['source_after_sha256']==expected and sm['source_patch_files']==sorted(changed|set(legacy['source_patch_files'])),'REVIEWED_SOURCE_MAP')
    require(all(sm[k]==v for k,v in legacy.items() if k not in ('source_after_sha256','source_patch_files')),'LEGACY_FIELDS_CHANGED')

def compare(work,control):
    require(work['protocol']==control['protocol'] and control['lane']=='control' and work['lane'] in ('fixed','staircase'),'CONTROL_LANE_MISMATCH')
    require(len(work['checkpoints'])==len(control['checkpoints']),'CONTROL_POINT_COUNT')
    return {'kind':'time_matched_workload_minus_no_work_observations','checkpoints':[
      {'checkpoint':w['checkpoint'], 'sampled_inuse_space_difference':w['profiles_sampled_weighted']['heap']['inuse_space']-c['profiles_sampled_weighted']['heap']['inuse_space'],
       'allocator_heap_inuse_difference':w['heap_inuse']-c['heap_inuse'],'released_difference':w['heap_released']-c['heap_released'],
       'goroutines_difference':w['goroutines']-c['goroutines'],
       'rss_difference':None if 'rss_bytes' not in w or 'rss_bytes' not in c else w['rss_bytes']-c['rss_bytes']}
       for w,c in zip(work['checkpoints'],control['checkpoints'])],
      'limitations':'startup/preparation identical definitions; balance/billing/idle pool owners require stack analysis; no leak or RSS acceptance verdict'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('run',type=Path);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--control',type=Path);ap.add_argument('--expected-manifest',type=Path);a=ap.parse_args()
    try:
        r=analyze(a.run,a.expected_manifest)
        if a.control:
            c=analyze(a.control,a.expected_manifest); cr=read(a.control/'run.json');wr=read(a.run/'run.json')
            require(cr['control_reference']['run_sha256']==sha(a.run/'run.json') and cr['build']['binary_sha256']==wr['build']['binary_sha256'],'CONTROL_REFERENCE_CHANGED')
            r['matched_control']=compare(r,c)
        a.out.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
    except Exception:raise SystemExit('ANALYSIS_REJECTED_INCOMPLETE_OR_INVALID_EVIDENCE')
