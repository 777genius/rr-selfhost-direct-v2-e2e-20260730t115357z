"""Independent strict data contracts; no scalar coercion or runtime access."""
import json, math, re
MIB = 1048576
class ContractError(ValueError): pass

def require(ok, code):
    if not ok: raise ContractError(code)
def number(x): return (type(x) is int and 0<=x<=2**53-1) or (type(x) is float and math.isfinite(x) and x>=0)
def integer(x): return type(x) is int and 0<=x<=2**64-1

def pairs(rows):
    result={}
    for k,v in rows:
        require(k not in result,'DUPLICATE_JSON_KEY'); result[k]=v
    return result

def strict_json(text):
    def invalid(_): raise ContractError('NONFINITE_JSON')
    try: return json.loads(text,object_pairs_hook=pairs,parse_constant=invalid)
    except (json.JSONDecodeError,UnicodeError) as e: raise ContractError('MALFORMED_JSON') from e

def jsonl(text):
    require(bool(text) and text.endswith('\n'),'INCOMPLETE_JSONL')
    lines=text.splitlines(); require(all(x.strip() for x in lines),'EMPTY_JSONL_ROW')
    return [strict_json(x) for x in lines]

def schedule(lane):
    require(lane in ('fixed','staircase','control'),'LANE_REQUIRED')
    return [5]*10 if lane=='fixed' else [1]*10+[5]*10+[20]*5 if lane=='staircase' else []

def burst_gate(row,n,protocol):
    require(type(row) is dict and row.get('functional_status')=='PASS','FUNCTIONAL_FAILURE')
    require(row.get('protocol')==protocol,'PROTOCOL_IDENTITY')
    require(row.get('stop_required') is False,'STOP_REQUIRED')
    require(row.get('unknown_identity') is False and row.get('exceeded') is False,'UNKNOWN_EFFECT')
    require(row.get('active_at_boundary')==0 and type(row.get('active_at_boundary')) is int,'ACTIVE_STREAMS')
    for key in ('upstream_attempts_total','upstream_effects_total'):
        require(integer(row.get(key)) and row[key]==n,'ATTEMPT_EFFECT_COUNT')
    ds=row.get('downstream',{})
    require(all(integer(ds.get(k)) for k in ('requests','successful','bytes','max_frame_bytes')),'DOWNSTREAM_NUMERIC')
    require(ds['requests']==ds['successful']==n and ds['bytes']==8*MIB*n,'VOLUME_COUNT')
    require(1.9*MIB<=ds['max_frame_bytes']<2*MIB,'FRAME_BOUND')
    rs=row.get('upstream');require(type(rs) is list and len(rs)==n,'UPSTREAM_COUNT')
    admitted=[row['id']+f'.r{j:02d}' for j in range(1,n+1)]
    require(row.get('admitted_request_ids')==admitted,'ADMITTED_IDS')
    completed=row.get('request_results')
    require(type(completed) is list and len(completed)==n and [r.get('id') for r in completed]==admitted,'MISSING_COMPLETED_REQUEST_IDS')
    for d in completed:
        require(all(integer(d.get(k)) for k in ('bytes','max_frame_bytes','text_delta_bytes','comments')),'PER_REQUEST_NUMERIC')
        require(d['bytes']==8*MIB and 1.9*MIB<=d['max_frame_bytes']<2*MIB and d['text_delta_bytes']>4096 and d['comments']>0,'PER_REQUEST_FRAME_VOLUME')
        require(d.get('http_status')==200 and d.get('transport') is None and d.get('failed') is False and d.get('malformed') is False and d.get('tool_id') is not None,'PER_REQUEST_PROTOCOL')
        require(all(number(d.get(k)) for k in ('duration_ms','terminal_ms','client_close_ms')),'PER_REQUEST_FINITE_CLOSE')
    seq=[];ids=[]
    for r in rs:
        require(r.get('id') in admitted and r.get('identity')==r.get('protocol')==protocol,'UPSTREAM_IDENTITY')
        require(integer(r.get('bytes')) and r['bytes']==8*MIB and integer(r.get('effects')) and r['effects']==1,'UPSTREAM_VOLUME_EFFECT')
        require(r.get('finished') is True and number(r.get('close_ms')) and number(r.get('terminal_ms')),'FINITE_TERMINAL_CLOSURE')
        require(integer(r.get('sequence')) and r['sequence']>0,'ATTEMPT_SEQUENCE');seq.append(r['sequence']);ids.append(r['id'])
    require(sorted(ids)==sorted(admitted),'MISSING_OR_DUPLICATE_REQUEST_IDS')
    require(len(set(seq))==n and seq==row.get('attempt_sequences'),'DUPLICATE_ATTEMPT')
    env=row.get('memory_envelope',{})
    require(env.get('empirical_qualified_status') in ('PASS','FAIL'),'RSS_UNVERIFIED')
    require(env.get('physical_interval_rss_status')=='NOTPROVEN','PHYSICAL_RSS_OVERCLAIM')
    return seq

SAMPLE_INTS=('schema','sequence','pid','heap_alloc','heap_objects','heap_inuse','heap_idle','heap_released','heap_sys',
 'total_alloc','mallocs','frees','sys','stack_inuse','stack_sys','next_gc','num_gc','num_forced_gc','last_gc_unix_ns',
 'pause_total_ns','goroutines','mem_profile_rate')
SAMPLE_NUMS=('start_ms','end_ms','duration_ms')

def samples_gate(rows,pid):
    require(type(rows) is list and len(rows)>=2,'MISSING_RUNTIME_SAMPLES')
    for i,r in enumerate(rows):
        require(type(r) is dict and set(r)==set(SAMPLE_INTS+SAMPLE_NUMS),'RUNTIME_FIELDS')
        require(all(integer(r[k]) for k in SAMPLE_INTS) and all(number(r[k]) for k in SAMPLE_NUMS),'FINITE_SCALARS_REQUIRED')
        require(r['schema']==1 and r['pid']==pid and r['sequence']==i+1,'RUNTIME_IDENTITY_SEQUENCE')
        require(r['end_ms']>=r['start_ms'] and abs(r['end_ms']-r['start_ms']-r['duration_ms'])<.001 and r['duration_ms']<=250,'RUNTIME_DURATION')
        require(r['num_forced_gc']==0 and r['mem_profile_rate']==512*1024,'MEMORY_SETTINGS_CHANGED')
        require(r['heap_released']<=r['heap_idle'] and r['heap_idle']+r['heap_inuse']==r['heap_sys'],'HEAP_CLASSES')
        require(r['heap_objects']==r['mallocs']-r['frees'] and r['heap_alloc']<=r['heap_inuse'] and r['heap_alloc']<=r['total_alloc'],'OBJECT_COUNTERS')
        if i:
            prev=rows[i-1]
            require(r['start_ms']>=prev['end_ms'] and r['start_ms']-prev['start_ms']<=250 and r['end_ms']-prev['end_ms']<=250,'RUNTIME_GAP')
            require(all(r[k]>=prev[k] for k in ('num_gc','total_alloc','mallocs','frees','pause_total_ns','last_gc_unix_ns')),'RUNTIME_COUNTER_REGRESSION')
    return {r['sequence']:r for r in rows}

CHECK_INTS=('schema','checkpoint','kind','before_sequence','after_sequence','before_num_gc','after_num_gc','pid')
def checkpoint_gate(rows,cp,index,pid):
    require(type(rows) is list and len(rows)==3,'MISSING_CHECKPOINT_KINDS')
    require([r.get('kind') for r in rows]==[1,2,3],'CHECKPOINT_KIND_ORDER')
    for r in rows:
        require(set(r)==set(CHECK_INTS+('start_ms','end_ms')),'CHECKPOINT_FIELDS')
        require(all(integer(r[k]) for k in CHECK_INTS) and all(number(r[k]) for k in ('start_ms','end_ms')),'CHECKPOINT_NUMERIC')
        require(r['schema']==1 and r['checkpoint']==cp and r['pid']==pid,'CHECKPOINT_IDENTITY')
        a=index.get(r['before_sequence']);b=index.get(r['after_sequence'])
        require(a is not None and b is not None and a['sequence']<b['sequence'],'CHECKPOINT_SAMPLE_MISSING')
        require(r['before_num_gc']==a['num_gc'] and r['after_num_gc']==b['num_gc'],'CHECKPOINT_CYCLES')
        require(r['start_ms']==a['end_ms'] and r['end_ms']==b['start_ms'] and r['start_ms']<=r['end_ms'],'CHECKPOINT_TIMES')
    require(all(a['after_sequence']<b['before_sequence'] for a,b in zip(rows,rows[1:])),'CHECKPOINT_OVERLAP')


def slope(xs,ys):
    require(len(xs)==len(ys) and len(xs)>1 and all(number(x) for x in xs+ys),'SLOPE_DATA')
    mx=sum(xs)/len(xs);my=sum(ys)/len(ys);den=sum((x-mx)**2 for x in xs)
    require(den>0,'SLOPE_X_VARIANCE');return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den
