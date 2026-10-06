#!/usr/bin/env python3
"""ROOT OPERATOR ONLY. Never launched by the source review worker.
One owned engine per finite lane, cloned synthetic DB/cache, no host ports.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, time
from contracts import require, strict_json, schedule, burst_gate, number, ContractError
from prepare import generate, sha, OWN, INPUT
from launch_contracts import config_gate, toolchain_gate, build_gate, dockerfile_gate, service_gate, BASE_TAG

MACHINE='d856d40da5ad4e23b4f67773e5942842'
NODE='node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1'
BASE='sha256:6df1cc33771f1bc94028cc18440a13e7d31a3513331bbb8d7d686584d19b79e2'
OLD_BINARY='e331d5cc5713ab665cf7f94363a6c6b72191e3915b8173c079e53b2773cec1ee'

def mono(): return time.clock_gettime_ns(time.CLOCK_MONOTONIC)/1e6

def write(p,obj,mode=0o600):
    p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n'); p.chmod(mode)

def env_file(p):
    result={}
    for line in p.read_text().splitlines():
        if not line or line.startswith('#'): continue
        k,sep,v=line.partition('=')
        require(sep and re.fullmatch('[A-Z0-9_]+',k) and k not in result,'FIXTURE_ENV_FORMAT')
        result[k]=v
    return result

def immutable(x): return type(x) is str and re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}',x)

class Driver:
    def __init__(self,c,root,protocol,lane,match):
        self.c=c;self.root=root;self.protocol=protocol;self.lane=lane;self.match=match
        self.name='rrsub2profile-'+protocol+'-'+lane+'-'+root.name[-8:]
        require(re.fullmatch('[a-z0-9-]{1,100}',self.name),'OWNED_NAME')
        self.net=self.name+'-net';self.containers=[];self.network_id=None;self.image=None;self.base_tag=None
        self.deadline=None;self.collector=None;self.rows=[];self.checkpoints=[];self.cleanup_errors=[]
        self.identity=None;self.started=None;self.baseline=None
        self.toolchain_env=None
    def toolchain_environment(self):
        if self.toolchain_env is None:
            self.toolchain_env={k:v for k,v in os.environ.items() if k in ('PATH','LANG')}
            self.toolchain_env.update(GOENV='off',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off',
                CGO_ENABLED='0',GOOS='linux',GOARCH='amd64',GOCACHE=self.c['compilation_cache'],GOMODCACHE=self.c['modules_cache'],GOMAXPROCS='2')
        return self.toolchain_env
    def cmd(self,args,timeout=30,input=None,env=None):
        if self.deadline is not None: timeout=min(timeout,(self.deadline-mono())/1000)
        require(timeout>0,'COMMAND_DEADLINE')
        r=subprocess.run(args,input=input,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
        require(r.returncode==0,'COMMAND_FAILED');return r.stdout
    def docker(self,*args,**kw): return self.cmd(['docker',*args],**kw)
    def inspect(self,name): return strict_json(self.docker('inspect',name).decode())[0]
    def own(self,name):
        obj=self.inspect(name);require(obj['Config']['Labels'].get('rrsub2profile.owner')==self.name,'OWNERSHIP_CHANGED');return obj
    def create(self,suffix,image,args,command=()):
        service_gate(suffix,image,args,command,self.c,self.private,self.env.get('REDIS_PASSWORD'))
        name=self.name+'-'+suffix
        # Register before execution: ambiguous creates are inspected by owned name
        # during cleanup; never retry a create or attach an existing container.
        self.containers.append(name)
        self.docker('create','--name',name,'--label','rrsub2profile.owner='+self.name,
          '--network',self.net,'--log-driver','none','--no-healthcheck',*args,image,*command)
        self.own(name);self.docker('start',name);return name
    def preflight(self):
        config_gate(self.c)
        require(os.geteuid()==0,'ROOT_ONLY')
        require(Path('/etc/machine-id').read_text().strip()==MACHINE,'MACHINE_PIN')
        require(self.c['machine_id']==MACHINE and self.c['node_image']==NODE and self.c['base_image']==BASE,'FROZEN_PINS')
        require(self.c.get('synthetic_only') is True,'SYNTHETIC_ONLY')
        require(all(immutable(self.c[k]) for k in ('postgres_image','redis_image')),'DEPENDENCY_DIGESTS_REQUIRED')
        mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
        require(mem>=3*1024**3,'MEMORY_RESERVE')
        v=os.statvfs(self.root.parent);require(v.f_bavail*v.f_frsize>=5*1024**3,'DISK_RESERVE')
        require(not self.root.exists(),'ROOT_REUSE_DENIED');self.root.mkdir(mode=0o700)
        require(self.c['fixture_attestation_sha256']==sha(Path(self.c['fixture_dir'])/'profile-fixture.json'),'FIXTURE_ATTESTATION_PIN')
        fixture=Path(self.c['fixture_dir']);f=strict_json((fixture/'profile-fixture.json').read_text())
        require(f['source']=='transport-isolated-r4' and f['status']=='PASS' and f['real_provider_keys_copied'] is False,'SYNTHETIC_FIXTURE_ATTESTATION')
        require(f['images']['postgres']==self.c['postgres_image'] and f['images']['redis']==self.c['redis_image'],'FIXTURE_SERVICE_IMAGE_PINS')
        for name in ('snapshot.sql','engine.env','lab.json'):
            require(sha(fixture/name)==f['hashes'][name],'PRIVATE_FIXTURE_PIN')
        self.fixture=f;self.env=env_file(fixture/'engine.env');self.lab=strict_json((fixture/'lab.json').read_text())
        require(self.env['DATABASE_HOST']=='postgres' and self.env['REDIS_HOST']=='redis','PRIVATE_FIXTURE_HOSTS')
        require(self.env.get('RUN_MODE','standard')!='simple','BILLING_DISABLED')
        require('RR_SUB2_PROFILE_DIR' not in self.env,'PROFILE_ENV_COLLISION')
        # Keep exact preexisting memory settings, including absence. They are
        # compared against effective image environment, without exporting values.
        self.memory_env={k:self.env.get(k) for k in ('GOGC','GOMEMLIMIT','GODEBUG')}
        for image in (BASE,NODE,self.c['postgres_image'],self.c['redis_image']):self.docker('image','inspect',image)
        require(sha(Path(self.c['go_binary']))==self.c['go_binary_sha256'],'TOOLCHAIN_PIN')
        require(self.cmd([self.c['go_binary'],'version'],env=self.toolchain_environment()).decode().strip()=='go version go1.27.1 linux/amd64','GO_VERSION')
        require(self.cmd(['uname','-m']).decode().strip()=='x86_64','ARCH_PIN')
        # This is a read-only comparison of the ACTUAL build toolchain stdlib.
        goroot=Path(self.cmd([self.c['go_binary'],'env','GOROOT'],env=self.toolchain_environment()).decode().strip())
        require(goroot.is_absolute() and goroot.is_dir(),'EFFECTIVE_GOROOT_REQUIRED')
        self.effective_goroot=goroot
        receipt=Path(self.c['toolchain_receipt'])
        require(sha(receipt)==self.c['toolchain_receipt_sha256'],'TOOLCHAIN_RECEIPT_PIN')
        self.toolchain=strict_json(receipt.read_text());toolchain_gate(self.toolchain,self.c)
        require(Path(self.c['compilation_cache']).is_dir() and Path(self.c['modules_cache']).is_dir(),'OFFLINE_CACHE_REQUIRED')
        for n,h in self.toolchain['stdlib_sha256'].items():
            require(sha(goroot/'src'/n)==h,'MATCHING_STDLIB_REQUIRED')
        reviewed=None
        if 'reviewed_source' in self.c:
            path=Path(self.c['reviewed_source'])
            require(sha(path)==self.c['reviewed_source_sha256'],'REVIEWED_SOURCE_PIN')
            reviewed=path
        manifest,_=generate(self.root/'stage',collector_source=Path(self.c['collector_source']),reviewed=reviewed);self.source=manifest
        self.code=self.root/'stage/code'
        self.profile=self.root/'profiles';self.private=self.root/'private';self.evidence=self.root/'evidence';self.telemetry=self.root/'telemetry'
        for p in (self.profile,self.private,self.evidence,self.telemetry):
            p.mkdir(mode=0o700 if p!=self.telemetry else 0o755)
            if p!=self.telemetry:os.chown(p,1000,1000)
        shutil.copyfile(fixture/'engine.env',self.private/'engine.env')
        with (self.private/'engine.env').open('a') as out:out.write('\nRR_SUB2_PROFILE_DIR=/rr-profile\nLOG_OUTPUT_TO_FILE=false\nLOG_OUTPUT_TO_STDOUT=true\n')
        (self.private/'engine.env').chmod(0o600)
        # Private mounted inputs readable only by the test operator UID.
        pg=''.join(k+'='+v+'\n' for k,v in {'POSTGRES_USER':self.env['DATABASE_USER'],
             'POSTGRES_PASSWORD':self.env['DATABASE_PASSWORD'],'POSTGRES_DB':self.env['DATABASE_DBNAME']}.items())
        (self.private/'postgres.env').write_text(pg);(self.private/'postgres.env').chmod(0o600)
        self.prepare_redis()
        self.snapshot=fixture/'snapshot.sql'
    def prepare_redis(self):
        if self.env.get('REDIS_PASSWORD'):
            cfg=self.private/'redis-profile.conf'
            cfg.write_text('save ""\nappendonly no\nrequirepass '+json.dumps(self.env['REDIS_PASSWORD'])+'\n');cfg.chmod(0o444)
    def build(self):
        b=self.root/'build';b.mkdir(mode=0o700)
        context=b/'image';context.mkdir(mode=0o700)
        env=self.toolchain_environment()
        if hasattr(self,'effective_goroot'):
            require(sha(Path(self.c['go_binary']))==self.c['go_binary_sha256'],'TOOLCHAIN_PIN')
            for n,h in self.toolchain['stdlib_sha256'].items():
                require(sha(self.effective_goroot/'src'/n)==h,'MATCHING_STDLIB_REQUIRED')
        binary=b/'profile-server'
        args=[self.c['go_binary'],'-C',str(self.root/'stage/backend'),'build','-trimpath','-buildvcs=false','-tags=rrsub2profile','-o',str(binary),'./cmd/server']
        build_gate(args,env,self.c)
        self.cmd(args,timeout=240,env=env)
        digest=sha(binary);require(digest!=OLD_BINARY,'BINARY_MUST_BE_DISTINCT')
        if self.source.get('reviewed_source'):
            require(digest==self.source['reviewed_source']['binary_sha256'],'REVIEWED_BINARY_PIN')
        info=self.cmd([self.c['go_binary'],'version','-m',str(binary)],env=env).decode()
        require('go1.27.1' in info and '-tags=rrsub2profile' in info,'BINARY_BUILD_INFO')
        # Only fixed build fields are retained; no environment values are logged.
        self.build_info={'go_version':'go1.27.1','tag':'rrsub2profile','binary_sha256':digest,
          'fixture_attestation_sha256':self.c['fixture_attestation_sha256'],'engine_env_file_sha256':sha(self.private/'engine.env'),
          'logging':'stdout discarded by Docker log-driver none; file sink disabled; no environment values exported'}
        shutil.copyfile(binary,context/'profile-server')
        require(strict_json(self.docker('image','inspect',BASE).decode())[0]['Id']==BASE,'BASE_IMAGE_ID')
        tag=BASE_TAG
        self.base_tag=tag
        self.docker('image','tag',BASE,tag)
        require(strict_json(self.docker('image','inspect',tag).decode())[0]['Id']==BASE,'BASE_TAG_ID')
        dockerfile='FROM '+tag+'\nCOPY --chmod=755 profile-server /rr-profile-server\nUSER 1000:1000\nENTRYPOINT ["/rr-profile-server"]\nCMD []\n'
        dockerfile_gate(dockerfile,tag);(context/'Dockerfile').write_text(dockerfile)
        write(self.root/'root-base-pin.json',{'kind':'offline-verified-base-tag','base_image_id':BASE,'tag':tag,'dockerfile_sha256':sha(context/'Dockerfile')})
        self.docker('build','--network','none','--pull=false','--tag',self.name+'-image',str(context),timeout=60)
        image=strict_json(self.docker('image','inspect',self.name+'-image').decode())[0]
        require(type(image) is dict and type(image.get('Id')) is str and re.fullmatch('sha256:[a-f0-9]{64}',image['Id']),'DERIVED_IMAGE_ID')
        self.image=image['Id'];require(self.image!=BASE,'IMAGE_MUST_BE_DISTINCT')
        self.build_info.update(image_id=self.image,base_image_id=BASE,base_tag=tag,dockerfile_sha256=sha(context/'Dockerfile'),toolchain_receipt_sha256=self.c['toolchain_receipt_sha256'],compilation_gomaxprocs=2)
        write(self.root/'build-receipt.json',self.build_info)
    def node(self,mode,*args,timeout=40):
        suffix='operator-'+mode+'-'+str(len(self.containers))
        mounts=['--mount',f'type=bind,src={self.code},dst=/lab,readonly','--mount',f'type=bind,src={self.private},dst=/private',
          '--mount',f'type=bind,src={self.evidence},dst=/evidence','--mount',f'type=bind,src={self.telemetry},dst=/telemetry,readonly',
          '--workdir','/lab','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--read-only','--tmpfs','/tmp','--memory','512m','--pids-limit','128','--cpus','2']
        name=self.create(suffix,NODE,mounts,('node','sub2api-memory-profile/profile-runner.mjs',mode,*args))
        code=int(self.docker('wait',name,timeout=timeout).decode().strip())
        obj=self.own(name);self.docker('rm','-v',obj['Id']);self.containers.remove(name)
        require(code==0,'ADAPTER_STOP')
    def wait_postgres(self, pg):
        # PG18 bootstrap accepts connections before DB creation and final exec.
        ready=min(self.deadline,mono()+30000)
        while mono()<ready:
            try:
                result=self.docker('exec',pg,'sh','-c','test "$(cat /proc/1/comm)" = postgres && PGOPTIONS="-c default_transaction_read_only=on" exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"',
                                   timeout=min(2,(ready-mono())/1000))
                if mono()<ready and result.strip()==b'1': return
            except (ValueError, subprocess.TimeoutExpired):
                pass
            remaining=(ready-mono())/1000
            if remaining>0: time.sleep(min(.25,remaining))
        raise ValueError('PRIVATE_DB_READY_TIMEOUT')

    def launch(self):
        self.started=mono();self.deadline=self.started+600000
        write(self.private/'supervisor.json',{'deadline_ms':self.deadline});os.chown(self.private/'supervisor.json',1000,1000)
        self.network_id=self.docker('network','create','--internal','--label','rrsub2profile.owner='+self.name,self.net).decode().strip()
        pg=self.create('postgres',self.c['postgres_image'],['--network-alias','postgres','--env-file',str(self.private/'postgres.env'),
           '--tmpfs','/var/lib/postgresql','--memory','512m'])
        redis_args=['--network-alias','redis','--memory','256m']
        redis_command=('redis-server','--save','','--appendonly','no')
        if self.env.get('REDIS_PASSWORD'):
            redis_args+=['--mount',f'type=bind,src={self.private}/redis-profile.conf,dst=/rr-profile-redis.conf,readonly']
            redis_command=('redis-server','/rr-profile-redis.conf')
        self.create('redis',self.c['redis_image'],redis_args,redis_command)
        self.wait_postgres(pg)
        self.docker('exec','-i',pg,'psql','-v','ON_ERROR_STOP=1','-U',self.env['DATABASE_USER'],'-d',self.env['DATABASE_DBNAME'],input=self.snapshot.read_bytes(),timeout=30)
        # Dedicated groups/users/accounts are created by the actual native setup.
        # Reject snapshots containing any usable upstream accounts.
        q=self.docker('exec',pg,'psql','-At','-U',self.env['DATABASE_USER'],'-d',self.env['DATABASE_DBNAME'],
                      '-c','SELECT count(*) FROM accounts WHERE deleted_at IS NULL;').decode().strip()
        require(q=='0','NONEMPTY_UPSTREAM_FIXTURE')
        lo=mono()
        engine=self.create('engine',self.image,['--network-alias','sub2api','--memory','768m','--memory-swap','1g',
          '--cpus','2','--pids-limit','512','--env-file',str(self.private/'engine.env'),
          '--mount',f'type=bind,src={self.profile},dst=/rr-profile'])
        created=mono();pid_seen=mono()
        # Health checks only before collection; docker exec would spoil sole PID
        # occupancy if used while a collector is active.
        for _ in range(80):
            r=subprocess.run(['docker','exec',engine,'curl','-s','-o','/dev/null','-w','%{http_code}','http://127.0.0.1:8080/health'],
              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3)
            if r.stdout==b'200':break
            time.sleep(.25)
        else:raise ValueError('ENGINE_READY_TIMEOUT')
        e=self.own(engine);require(e['Image']==self.image and list(e['NetworkSettings']['Networks'])==[self.net],'ENGINE_PIN')
        require(not e['HostConfig']['PortBindings'],'NO_HOST_PORTS')
        actual_env=dict(x.split('=',1) for x in e['Config']['Env'])
        base_env=dict(x.split('=',1) for x in strict_json(self.docker('image','inspect',BASE).decode())[0]['Config']['Env'])
        require(all(actual_env.get(k)==self.env.get(k,base_env.get(k)) for k in self.memory_env),'MEMORY_ENV_CHANGED')
        proc=Path('/proc')/str(e['State']['Pid']);cgpath=(proc/'cgroup').read_text().strip().split('::')[1]
        cg=Path('/sys/fs/cgroup')/cgpath.lstrip('/');cs=cg.stat();exe=(proc/'exe').stat()
        require(sha(proc/'exe')==self.build_info['binary_sha256'],'RUNNING_BINARY_PIN')
        ticks=int((proc/'stat').read_text().rsplit(')',1)[1].split()[19])
        nspid=next(x.split()[1:] for x in (proc/'status').read_text().splitlines() if x.startswith('NSpid:'))
        self.namespace_pid=int(nspid[-1])
        self.identity={'instance':self.name,'engine_pid':e['State']['Pid'],'pid_start_ticks':ticks,'cgroup_path':cgpath,
          'cgroup_device':cs.st_dev,'cgroup_inode':cs.st_ino,'exe_device':exe.st_dev,'exe_inode':exe.st_ino,'container_id':e['Id'],
          'container_created_ms':created,'pid_created_ms':pid_seen,'fresh_container_inspected':True,
          'creation_time_evidence':{'container_lower_ms':lo,'container_upper_ms':created,'pid_created_ms_kind':'upper bound after dedicated start'}}
        self.engine=engine
        d={'source_sha':self.source['historical']['source_sha'],'image':'rrsub2profile@'+self.image,'variant':'patched',
          'patch_sha256':self.source['historical']['components'][0]['patch_sha256'],
          'source_manifest_sha256':sha(self.root/'stage/source-manifest.json'),'instance':self.name,'cgroup_limit_bytes':805306368,
          'engine_pid':e['State']['Pid'],'container_id':e['Id'],'inspected':True,'clock':'linux-CLOCK_MONOTONIC'}
        cfg=dict(self.lab);cfg.update(run_id=self.name[-36:],deployment=d)
        for name,v in (('lab.json',cfg),('deployed.json',d)):
            write(self.private/name,v);os.chown(self.private/name,1000,1000)
        mock_args=['--network-alias','mock','--user','1000:1000','--read-only','--tmpfs','/tmp','--cap-drop','ALL',
          '--security-opt','no-new-privileges','--memory','512m','--pids-limit','128','--cpus','2','--workdir','/lab',
          '--mount',f'type=bind,src={self.code},dst=/lab,readonly','--mount',f'type=bind,src={self.private},dst=/private,readonly']
        self.create('mock',NODE,mock_args,('node','sub2api-regression-lab/mock.mjs'))
        time.sleep(.5);self.node('setup',self.protocol)
        self.baseline=mono();self.checkpoint(0)
    def checkpoint(self,cp):
        temp=self.profile/'request.tmp';temp.write_text(str(cp)+'\n');temp.chmod(0o600);os.chown(temp,1000,1000)
        temp.rename(self.profile/'request')
        limit=min(self.deadline,mono()+15000)
        ack=self.profile/f'checkpoint-{cp:03d}.json'
        while not ack.exists() and mono()<limit:
            require(self.own(self.engine)['State']['Running'],'PROFILE_ENGINE_EXITED');time.sleep(.1)
        require(ack.exists(),'CHECKPOINT_TIMEOUT')
        # These root timestamps bind process profiles to each ordered burst.
        self.checkpoints.append({'checkpoint':cp,'elapsed_ms':mono()-self.baseline})
    def burst(self,i,n):
        require(mono()+110000<self.deadline,'FULL_BURST_RESERVE')
        cid=f'memory-{self.protocol}-8-{n}-b{i:02d}'
        spec={'id':cid,'stage':'memory','protocol':self.protocol,'streams':n,'count':n,'mib':8,'request_ids':[cid+f'.r{j:02d}' for j in range(1,n+1)]}
        write(self.private/'burst.json',spec);os.chown(self.private/'burst.json',1000,1000)
        specpath=self.root/(cid+'-collector.json')
        write(specpath,{**self.identity,'batch_id':cid,'start_path':str(self.evidence/(cid+'.start.json')),'end_path':str(self.evidence/(cid+'.end.json'))})
        # No engine restart, health exec, GC, peak reset, or account edit here.
        self.collector=subprocess.Popen(['python3',str(self.code/'sub2api-transport-r4/collector.py'),'--spec',str(specpath),
                  '--output',str(self.telemetry)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        limit=min(self.deadline,mono()+6000)
        while not (self.telemetry/(cid+'.ready.json')).exists() and mono()<limit:
            require(self.collector.poll() is None,'COLLECTOR_EARLY_EXIT');time.sleep(.05)
        require((self.telemetry/(cid+'.ready.json')).exists(),'COLLECTOR_READY_TIMEOUT')
        self.node('burst',timeout=90)
        require(self.collector.wait(timeout=6)==0,'COLLECTOR_EXIT');self.collector=None
        row=strict_json((self.evidence/(cid+'.json')).read_text());burst_gate(row,n,self.protocol)
        seq=[s for r in self.rows for s in r['sequences']]+row['attempt_sequences']
        require(len(seq)==len(set(seq)),'REPEATED_EFFECT')
        self.rows.append({'id':cid,'streams':n,'sequences':row['attempt_sequences'],'elapsed_ms':mono()-self.baseline})
        self.checkpoint(i)
    def control(self):
        match=strict_json((self.match/'run.json').read_text())
        require(match['status']=='COMPLETE' and match['lane'] in ('fixed','staircase') and match['protocol']==self.protocol,'CONTROL_REFERENCE')
        require(match['build']['binary_sha256']==self.build_info['binary_sha256'],'CONTROL_BINARY_CHANGED')
        require(match['source_manifest_sha256']==sha(self.root/'stage/source-manifest.json'),'CONTROL_SOURCE_CHANGED')
        targets=match['checkpoints'][1:]
        require(len(targets)==len(schedule(match['lane'])),'CONTROL_SCHEDULE_MISSING')
        loader=importlib.util.spec_from_file_location('owned_collector',self.code/'sub2api-transport-r4/collector.py')
        m=importlib.util.module_from_spec(loader);loader.loader.exec_module(m)
        spec={**self.identity,'batch_id':'control-'+self.protocol}
        path=self.root/'control-rss.ndjson';last=None;index=0
        with path.open('x') as out:
            while index<len(targets):
                require(mono()+1000<self.deadline,'CONTROL_BUDGET')
                tick=mono();r=m.read_sample(spec)
                require(r['sample_duration_ms']<=250 and (last is None or r['mono_ms']-last['mono_ms']<=250),'CONTROL_SAMPLE_GAP')
                out.write(json.dumps(r,allow_nan=False)+'\n');out.flush();last=r
                if mono()-self.baseline>=targets[index]['elapsed_ms']:
                    self.checkpoint(index+1);index+=1
                    # Profile writing gaps are measured explicitly, outside RSS
                    # measurement intervals; never claimed as continuous coverage.
                    last=None
                time.sleep(max(0,.1-(mono()-tick)/1000))
        self.control_reference={'run_sha256':sha(self.match/'run.json'),'lane':match['lane'],'targets':targets}
    def teardown(self):
        # Cleanup gets a separate bounded 20s reserve after admission closes.
        self.deadline=mono()+20000
        if self.collector and self.collector.poll() is None:
            self.collector.terminate()
            try:self.collector.wait(timeout=3)
            except subprocess.TimeoutExpired:self.collector.kill();self.collector.wait(timeout=3)
        if self.identity and (self.private/'profile-owned.json').exists():
            try:
                write(self.private/'supervisor.json',{'deadline_ms':self.deadline});os.chown(self.private/'supervisor.json',1000,1000)
                self.node('state',timeout=5);self.node('cleanup',timeout=10)
                clean=strict_json((self.evidence/'account-cleanup.json').read_text())
                require(clean['failures']==0 and clean['ambiguous_intent'] is False and clean['remaining_resources']==[],'ACCOUNT_CLEANUP_FAILED')
            except Exception:self.cleanup_errors.append('ACCOUNT_CLEANUP_UNVERIFIED')
        for name in reversed(self.containers):
            try:
                # Never remove by name without verifying this run's label.
                obj=self.own(name);self.docker('rm','-f','-v',obj['Id'],timeout=3)
            except Exception:self.cleanup_errors.append('OWNED_CONTAINER_CLEANUP_UNVERIFIED')
        if self.network_id:
            try:
                n=strict_json(self.docker('network','inspect',self.network_id).decode())[0]
                require(n['Labels'].get('rrsub2profile.owner')==self.name and not n['Containers'],'NETWORK_OWNERSHIP')
                self.docker('network','rm',self.network_id,timeout=3)
            except Exception:self.cleanup_errors.append('OWNED_NETWORK_CLEANUP_UNVERIFIED')
        if self.image:
            try:self.docker('image','rm',self.name+'-image',timeout=3)
            except Exception:self.cleanup_errors.append('OWNED_IMAGE_CLEANUP_UNVERIFIED')
        # The verified canonical base tag remains a fixture pin. Removing its
        # last tag could delete the preexisting bare-ID base before the control.
        # Keep binary, source hashes, partial receipts and all profile artifacts.
        write(self.root/'resource-cleanup.json',{'failures':len(self.cleanup_errors),'errors':self.cleanup_errors})
    def run(self):
        self.preflight();status='PARTIAL';failure=None
        try:
            self.phase='build';self.build();self.phase='launch';self.launch()
            if self.lane=='control':self.phase='control';self.control()
            else:
                for i,n in enumerate(schedule(self.lane),1):self.phase='burst-'+str(i);self.burst(i,n)
            status='COMPLETE'
        except Exception as e:failure=str(e) if isinstance(e,ContractError) and re.fullmatch('[A-Z_]+',str(e)) else 'PROFILE_RUN_STOP_NO_AUTORETRY'
        finally:
            self.measurement_end=mono();self.teardown()
            if self.cleanup_errors:status='PARTIAL'
            write(self.root/'run.json',{'schema':'rrsub2profile-run-v1','status':status,'failure':failure,
              'phase':getattr(self,'phase',None),'protocol':self.protocol,'lane':self.lane,'scheduled_streams':schedule(self.lane),
              'requests_completed':sum(r['streams'] for r in self.rows),'rows':self.rows,'checkpoints':self.checkpoints,
              'measurement_elapsed_ms':None if not self.started else self.measurement_end-self.started,
              'baseline_ms':self.baseline,'identity':self.identity,'namespace_pid':getattr(self,'namespace_pid',None),
              'source_manifest_sha256':sha(self.root/'stage/source-manifest.json'),
              'build':getattr(self,'build_info',None),'control_reference':getattr(self,'control_reference',None),
              'historical_reliability':'ALL 20 RSS return FAIL remain FAIL',
              'missing_counters':['handler/readers','body owners','slots/waiters','billing queue','reservation refs','idle pool'],
              'cleanup_failures':len(self.cleanup_errors),'no_forced_gc':True,'new_image_and_binary':True})
        return status

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--protocol',choices=['responses','messages'],required=True);ap.add_argument('--lane',choices=['fixed','staircase','control'],required=True)
    ap.add_argument('--match',type=Path);a=ap.parse_args()
    try:
        require((a.lane=='control')==(a.match is not None),'TIME_MATCHED_CONTROL_REQUIRED')
        r=Driver(strict_json(a.config.read_text()),a.out.resolve(),a.protocol,a.lane,a.match).run()
        print(json.dumps({'status':r,'root':str(a.out)}));raise SystemExit(0 if r=='COMPLETE' else 1)
    except Exception:raise SystemExit('ROOT_PROFILE_PREFLIGHT_OR_HANDOFF_STOP')
