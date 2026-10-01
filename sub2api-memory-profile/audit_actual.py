#!/usr/bin/env python3
"""Independent numeric audit of supplied root outputs, without Go/pprof/Docker.
Comparison JSON is checked against runtime/telemetry where available. Missing
run/build/DONE/profile bytes are explicit gaps, never treated as green gates.
"""
import argparse,hashlib,json,math,statistics
from pathlib import Path
from contracts import require,jsonl,samples_gate,strict_json,number,integer
from prepare import verify_inputs,INPUT,OWN,sha
METRICS=('heap_alloc_allocator','heap_objects_allocator','heap_inuse','heap_released','total_alloc','mallocs','goroutines')
RUNTIME={'heap_alloc_allocator':'heap_alloc','heap_objects_allocator':'heap_objects','heap_inuse':'heap_inuse','heap_released':'heap_released','total_alloc':'total_alloc','mallocs':'mallocs','goroutines':'goroutines'}

def audit(actual=INPUT/'actual'):
    pins=verify_inputs();out={}
    for protocol,index in [('responses',9),('messages',10)]:
        root=actual/f'profile-{protocol}-fixed-{index:08d}'
        control=actual/f'profile-{protocol}-control-{index+2:08d}'
        comparison=strict_json((actual/f'profile-{protocol}-comparison-w1.json').read_text())
        require(comparison['status']=='DIAGNOSTIC_ONLY' and comparison['protocol']==protocol and comparison['lane']=='fixed','ACTUAL_DIAGNOSTIC_IDENTITY')
        points=comparison['checkpoints'];require(len(points)==11 and [p['checkpoint'] for p in points]==list(range(11)),'ACTUAL_POINTS')
        rt=jsonl((root/'profiles/runtime.ndjson').read_text());samples_gate(rt,1)
        crt=jsonl((control/'profiles/runtime.ndjson').read_text());samples_gate(crt,1)
        for p in points:
            require(all(number(p[k]) for k in METRICS+('elapsed_ms','num_gc')),'ACTUAL_POINT_NUMERIC')
            matches=[r for r in rt if all(r[RUNTIME[k]]==p[k] for k in METRICS) and r['num_gc']==p['num_gc']]
            require(matches,'POINT_NOT_IN_ACTUAL_RUNTIME')
        recomputed={}
        for name,series in [('all_checkpoints',points),('postwarmup_after_two_bursts',points[3:])]:
            xs=[p['elapsed_ms']/1000 for p in series];sl={}
            for k in METRICS:
                sl[k]=statistics.linear_regression(xs,[p[k] for p in series]).slope
                require(math.isclose(sl[k],comparison['slopes'][name][k],rel_tol=1e-10,abs_tol=1e-8),'ACTUAL_SLOPE_MISMATCH')
            for k in ('inuse_space','inuse_objects','alloc_space','alloc_objects'):
                v=statistics.linear_regression(xs,[p['profiles_sampled_weighted']['heap'][k] for p in series]).slope
                require(math.isclose(v,comparison['slopes'][name]['sampled_heap_'+k+'_per_second'],rel_tol=1e-10,abs_tol=1e-8),'ACTUAL_SAMPLED_SLOPE_MISMATCH')
                sl['sampled_heap_'+k+'_per_second']=v
            if name.startswith('postwarmup'):
                sl['rss_bytes_per_second']=statistics.linear_regression(xs,[p['rss_bytes'] for p in series]).slope
                require(math.isclose(sl['rss_bytes_per_second'],comparison['slopes'][name]['rss_bytes_per_second'],rel_tol=1e-10),'ACTUAL_RSS_SLOPE_MISMATCH')
            recomputed[name]=sl
        rss_identity=None;previous_peak=0;max_sample_gap=0;max_sample_duration=0
        identity_keys=('instance','engine_pid','pid_start_ticks','cgroup_path','cgroup_device','cgroup_inode','container_id','exe_device','exe_inode')
        for p in points[1:]:
            rows=jsonl((root/'telemetry'/f'memory-{protocol}-8-5-b{p["checkpoint"]:02d}.ndjson').read_text())
            require(all(number(r[k]) for r in rows for k in ('mono_ms','sample_started_ms','sample_duration_ms','rss_bytes','smaps_rollup_rss_bytes','sockets')),'ACTUAL_RSS_FIELDS')
            require(rows,'ACTUAL_RSS_EMPTY')
            for i,r in enumerate(rows):
                identity={k:r[k] for k in identity_keys}
                require(all(integer(identity[k]) and identity[k]>0 for k in ('engine_pid','pid_start_ticks','cgroup_device','cgroup_inode','exe_device','exe_inode')),'ACTUAL_RSS_IDENTITY_FIELDS')
                if rss_identity is None:rss_identity=identity
                require(identity==rss_identity,'ACTUAL_RSS_PROCESS_CHANGED')
                require(number(r['cgroup_peak_bytes']) and r['cgroup_peak_bytes']>=previous_peak and r['cgroup_limit_bytes']==805306368 and r['physical_interval_rss_upper_bound_bytes'] is None,'ACTUAL_CGROUP_IDENTITY')
                previous_peak=r['cgroup_peak_bytes']
                require(0<=r['sample_duration_ms']<=250 and abs(r['mono_ms']-r['sample_started_ms']-r['sample_duration_ms'])<.001,'ACTUAL_RSS_DURATION')
                max_sample_duration=max(max_sample_duration,r['sample_duration_ms'])
                if i:
                    gap=r['mono_ms']-rows[i-1]['mono_ms'];require(0<=gap<=250,'ACTUAL_RSS_SAMPLE_GAP');max_sample_gap=max(max_sample_gap,gap)
            require(any(r['phase']=='quiescent' and r['rss_bytes']==p['rss_bytes'] and r['smaps_rollup_rss_bytes']==p['smaps_rss_bytes'] and r['sockets']==p['sockets'] for r in rows),'ACTUAL_RSS_ENDPOINT_VALUE')
            require(p['postburst_profile_cycle_eligible'] is False and type(p['natural_cycles_after_end']) is int and 0<=p['natural_cycles_after_end']<2,'ACTUAL_CYCLE_LIMITATION')
        deltas=comparison['matched_control']['checkpoints'];require(len(deltas)==11,'ACTUAL_CONTROL_POINTS')
        for w,d in zip(points,deltas):
            require(d['checkpoint']==w['checkpoint'],'ACTUAL_CONTROL_ORDER')
            require(any(r['heap_inuse']==w['heap_inuse']-d['allocator_heap_inuse_difference'] and r['heap_released']==w['heap_released']-d['released_difference'] and r['goroutines']==w['goroutines']-d['goroutines_difference'] for r in crt),'CONTROL_POINT_NOT_IN_RUNTIME')
        top=(actual/f'profile-{protocol}-heap-top-w1.txt').read_text()
        moderation=next(l.strip() for l in top.splitlines() if 'NewContentModerationService' in l)
        require(moderation.startswith('27.47MB'),'ACTUAL_STATIC_MODERATION_TOP')
        out[protocol]={'checkpoints':11,'runtime_samples':len(rt),'control_samples':len(crt),'postburst_natural_cycles':[p['natural_cycles_after_end'] for p in points[1:]],'postburst_profile_cycle_eligible':False,'stable_rss_process_identity':rss_identity,'max_within_burst_sample_gap_ms':max_sample_gap,'max_sample_duration_ms':max_sample_duration,
          'slopes_independently_recomputed':recomputed,'checkpoint_10':points[-1],
          'static_moderation_top':moderation,'comparison_sha256':sha(actual/f'profile-{protocol}-comparison-w1.json')}
    return {'schema':'rrsub2profile-actual-audit-v1','status':'DIAGNOSTIC_ONLY','current_input_entries_verified':len(pins),'protocols':out,
      'root_reported_scope':'fixed N5: 10 bursts, 50 requests, 400MiB per protocol; matched idle controls; cleanup 0; same bdb8ef4-prefix native/probe binary; no W2 memory or W3 cancellation patches',
      'independently_verified_scope':'supplied input custody; runtime scalar contracts; checkpoint allocator snapshots present; OLS slopes; stable RSS process/cgroup identity and within-burst timing; RSS endpoint values present; matched control allocator differences present; supplied pprof text attribution',
      'missing_actual_evidence':['full run/build receipts and complete binary hash','checkpoint acknowledgements and binary profiles','burst case/READY/DONE receipts and root cleanup receipts','actual collector source and frozen matching stdlib'],
      'limitations':'Numeric observations are consistent with root report, not independent proof of missing resource/effect/tail/cleanup gates. No two natural cycles after any burst; weighted pprof is historical and not equal to current ReadMemStats. No indefinite leak/plateau, orphan reader/slot, data-labeled leak or RSS fix verdict.',
      'historical_20_rss_return':'FAIL (unchanged)','future_source_runtime_gates':'reviewed stream/cancel source patches, exact build/binary pin, native/HTTP/WS regression and fresh runtime receipts required; no existing receipt promotion'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    result=audit();a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'output':str(a.out),'protocols':list(result['protocols'])}))
