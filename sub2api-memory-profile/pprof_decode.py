"""Small independent binary pprof aggregate reader. No symbol/body output.
Checks real protobuf values, including packed repeated signed int64 sample values.
Profiles are sampled/weighted and delayed; aggregates are not exact live bytes.
"""
import gzip, io
from contracts import require

def varint(b,i):
    n=0
    for shift in range(0,70,7):
        require(i<len(b),'TRUNCATED_PROTOBUF');x=b[i];i+=1;n|=(x&127)<<shift
        if not x&128:
            require(n<2**64,'PROTOBUF_INTEGER_OVERFLOW');return n,i
    raise ValueError('PROTOBUF_VARINT_TOO_LONG')

def fields(b):
    i=0
    while i<len(b):
        tag,i=varint(b,i);field=tag>>3;wire=tag&7;require(field>0,'PROTOBUF_TAG')
        if wire==0:value,i=varint(b,i)
        elif wire==2:
            n,i=varint(b,i);require(n<=len(b)-i,'TRUNCATED_PROTOBUF');value=b[i:i+n];i+=n
        elif wire in (1,5):
            n=8 if wire==1 else 4;require(n<=len(b)-i,'TRUNCATED_PROTOBUF');value=b[i:i+n];i+=n
        else:raise ValueError('PROTOBUF_WIRE_UNSUPPORTED')
        yield field,wire,value

def signed(n): return n if n<2**63 else n-2**64

def decode(path,kind):
    require(path.is_file() and 0<path.stat().st_size<=64*1024**2,'PROFILE_FILE_MISSING_OR_SIZE')
    with gzip.open(path,'rb') as f:b=f.read(128*1024**2+1)
    require(len(b)<=128*1024**2,'PROFILE_UNCOMPRESSED_LIMIT')
    strings=[];types=[];samples=[];labels=[];period=None
    for field,wire,value in fields(b):
        if field==6:
            require(wire==2,'PROFILE_STRING_WIRE');strings.append(value.decode('utf8','strict'))
        elif field==1:
            row={k:v for k,w,v in fields(value) if w==0};require(set(row)=={1,2},'PROFILE_VALUE_TYPE');types.append(row)
        elif field==2:
            vals=[]
            for k,w,v in fields(value):
                if k==2:
                    if w==0:vals.append(signed(v))
                    elif w==2:
                        i=0
                        while i<len(v):n,i=varint(v,i);vals.append(signed(n))
                    else:raise ValueError('PROFILE_SAMPLE_WIRE')
                if k==3:
                    require(w==2,'PROFILE_LABEL_WIRE');label={}
                    for lf,lw,lv in fields(v):
                        require(lw==0 and lf not in label,'PROFILE_LABEL_FIELDS');label[lf]=lv
                    labels.append(label)
            samples.append(vals)
        elif field==12:
            require(wire==0,'PROFILE_PERIOD_WIRE');period=value
    require(strings and strings[0]=='','PROFILE_STRING_TABLE')
    require(types and samples,'PROFILE_EMPTY')
    for label in labels:
        require(kind!='goroutine' and set(label)=={1,3} and label[1]<len(strings) and strings[label[1]]=='bytes' and label[3]<2**63,'PROFILE_LABELS_NOT_BODYFREE')
    require(all(r[1]<len(strings) and r[2]<len(strings) for r in types),'PROFILE_STRING_INDEX')
    names=[strings[r[1]] for r in types];units=[strings[r[2]] for r in types]
    require(len(names)==len(set(names)),'PROFILE_DUPLICATE_TYPE')
    expected={'heap':{'alloc_objects':'count','alloc_space':'bytes','inuse_objects':'count','inuse_space':'bytes'},
              'allocs':{'alloc_objects':'count','alloc_space':'bytes','inuse_objects':'count','inuse_space':'bytes'},
              'goroutine':{'goroutine':'count'}}[kind]
    require(dict(zip(names,units))==expected,'PROFILE_SAMPLE_TYPES')
    require(all(len(v)==len(names) and all(n>=0 for n in v) for v in samples),'PROFILE_SAMPLE_VALUES')
    if kind!='goroutine':require(period==512*1024,'PROFILE_SAMPLING_RATE')
    result=dict(zip(names,[sum(v[i] for v in samples) for i in range(len(names))]))
    if kind!='goroutine':require(result['inuse_space']<=result['alloc_space'] and result['inuse_objects']<=result['alloc_objects'],'PROFILE_AGGREGATES')
    return result
