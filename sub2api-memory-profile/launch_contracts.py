"""Validate producer inputs and generated subprocess payloads before effects.
No Docker/Go calls; secret values are only compared in operator memory.
"""
from pathlib import Path
import re
from contracts import require
BASE='sha256:6df1cc33771f1bc94028cc18440a13e7d31a3513331bbb8d7d686584d19b79e2'
NODE='node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1'
BASE_TAG='rr-sub2-profile-base:6df1cc3-20261001'
MACHINE='d856d40da5ad4e23b4f67773e5942842'
def digest(v): return type(v) is str and re.fullmatch('[a-f0-9]{64}',v) is not None
def image(v): return type(v) is str and re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}',v) is not None
def config_gate(c):
    require(type(c) is dict,'CONFIG_OBJECT')
    paths=('fixture_dir','go_binary','modules_cache','compilation_cache','toolchain_receipt','collector_source')
    hashes=('fixture_attestation_sha256','go_binary_sha256','toolchain_receipt_sha256')
    require(all(type(c.get(k)) is str and Path(c[k]).is_absolute() for k in paths),'CONFIG_PATH_FIELDS')
    require(all(digest(c.get(k)) for k in hashes),'CONFIG_HASH_FIELDS')
    require(c.get('synthetic_only') is True,'SYNTHETIC_ONLY')
    require(c.get('machine_id')==MACHINE and c.get('node_image')==NODE and c.get('base_image')==BASE,'FROZEN_PINS')
    require(all(image(c.get(k)) for k in ('postgres_image','redis_image')),'DEPENDENCY_DIGESTS_REQUIRED')
    require(('reviewed_source' in c)==('reviewed_source_sha256' in c),'REVIEWED_SOURCE_FIELDS')
    if 'reviewed_source' in c:
        require(type(c['reviewed_source']) is str and Path(c['reviewed_source']).is_absolute() and digest(c['reviewed_source_sha256']),'REVIEWED_SOURCE_FIELDS')

def toolchain_gate(r,c):
    require(type(r) is dict and set(r)=={'go_version','go_binary_sha256','stdlib_sha256','compilation_cache'},'TOOLCHAIN_RECEIPT_FIELDS')
    require(r['go_version']=='go1.27.1' and r['go_binary_sha256']==c['go_binary_sha256'] and r['compilation_cache']==c['compilation_cache'],'TOOLCHAIN_CACHE_PIN')
    names={'runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go'}
    require(type(r['stdlib_sha256']) is dict and set(r['stdlib_sha256'])==names and all(digest(v) for v in r['stdlib_sha256'].values()),'STDLIB_RECEIPT_FIELDS')

def build_gate(args,env,c):
    require(type(args) is list and all(type(x) is str for x in args) and type(env) is dict,'BUILD_FIELDS')
    require(len(args)==10 and args[0]==c['go_binary'] and args[1]=='-C' and args[3:7]==['build','-trimpath','-buildvcs=false','-tags=rrsub2profile'] and args[7]=='-o' and args[9]=='./cmd/server','BUILD_COMMAND')
    fixed={'GOENV':'off','GOTOOLCHAIN':'local','GOWORK':'off','GOPROXY':'off','GOSUMDB':'off','CGO_ENABLED':'0','GOOS':'linux','GOARCH':'amd64','GOMAXPROCS':'2','GOCACHE':c['compilation_cache'],'GOMODCACHE':c['modules_cache']}
    require(all(env.get(k)==v and type(env.get(k)) is str for k,v in fixed.items()) and set(env)<=set(fixed)|{'PATH','LANG'},'BUILD_ENVIRONMENT')

def dockerfile_gate(text,tag):
    require(type(text) is str and type(tag) is str and tag==BASE_TAG,'BASE_TAG_FIELDS')
    lines=text.splitlines()
    require(len(lines)==5 and lines[0]=='FROM '+tag and lines[1].split()==['COPY','--chmod=755','profile-server','/rr-profile-server'] and lines[2]=='USER 1000:1000' and lines[3]=='ENTRYPOINT ["/rr-profile-server"]' and lines[4]=='CMD []','GENERATED_IMAGE_CONFIGURATION')

def service_gate(suffix,image_id,args,command,c,private,redis_password):
    require(type(args) is list and all(type(x) is str for x in args) and type(command) in (list,tuple) and all(type(x) is str for x in command),'LAUNCH_FIELDS')
    if suffix not in ('postgres','redis'): return
    require(image_id==c[suffix+'_image'],'SERVICE_IMAGE_CHANGED')
    def option(k):
        require(args.count(k)==1 and args.index(k)+1<len(args),'LAUNCH_OPTION')
        return args[args.index(k)+1]
    require(option('--network-alias')==suffix,'SERVICE_NETWORK_ALIAS')
    if suffix=='postgres':
        require(len(args)==8 and set(args[::2])=={'--network-alias','--env-file','--tmpfs','--memory'},'POSTGRES_OPTIONS')
        require(option('--tmpfs')=='/var/lib/postgresql' and option('--env-file')==str(private/'postgres.env') and option('--memory')=='512m' and not command,'POSTGRES_CONFIGURATION')
    else:
        require(len(args)==(6 if redis_password else 4) and set(args[::2])==({'--network-alias','--memory','--mount'} if redis_password else {'--network-alias','--memory'}),'REDIS_OPTIONS')
        require(option('--memory')=='256m','REDIS_MEMORY')
        if redis_password:
            require(tuple(command)==('redis-server','/rr-profile-redis.conf') and option('--mount')==f'type=bind,src={private}/redis-profile.conf,dst=/rr-profile-redis.conf,readonly','REDIS_PRIVATE_CONFIG')
            p=private/'redis-profile.conf'
            import json
            require(p.is_file() and p.stat().st_mode & 0o777==0o444 and p.read_text()=='save ""\nappendonly no\nrequirepass '+json.dumps(redis_password)+'\n','REDIS_CONFIG_CONTENT')
        else:
            require(tuple(command)==('redis-server','--save','','--appendonly','no') and '--mount' not in args,'REDIS_CONFIGURATION')
