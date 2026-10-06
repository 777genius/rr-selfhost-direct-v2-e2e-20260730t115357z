#!/usr/bin/env python3
"""ROOT OPERATOR ONLY: fresh private Docker network/PG18/Redis/engine.
The worker runs only offline unit tests, never this entry point.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, secrets, signal, subprocess, time, stat, importlib.util
from prepare import assemble, sha, HERE

LABEL = 'rr.slot-lab.owner'
def need(ok, code):
    if not ok: raise ValueError(code)
def mono(): return time.monotonic_ns()/1e6
def immutable(value): return isinstance(value,str) and re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}', value)
def dump(path, value):
    with Path(path).open('w', encoding='utf8') as f: json.dump(value,f,indent=2); f.write('\n')
    Path(path).chmod(0o600)
def load(path): return json.loads(Path(path).read_text())
def private_read(path):
    p=Path(path); need(p.is_absolute() and '..' not in p.parts, 'PRIVATE_FILE_REQUIRED')
    fd=os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            child=os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd=child
        leaf=os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            st=os.fstat(leaf)
            need(stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode)==0o600 and st.st_uid==os.geteuid(), 'OPERATOR_REGULAR_EXACT_0600_REQUIRED')
            with os.fdopen(leaf, 'rb', closefd=False) as f: data=f.read()
            end=os.fstat(leaf)
            need((st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(end.st_size,end.st_mtime_ns,end.st_ctime_ns), 'PRIVATE_FILE_CHANGED')
            return data
        finally: os.close(leaf)
    except OSError: raise ValueError('PRIVATE_SYMLINK_OR_OPEN_DENIED') from None
    finally: os.close(fd)
def private_file(path):
    private_read(path); return Path(path)
def private_json(path, expected=None):
    data=private_read(path)
    if expected is not None: need(hashlib.sha256(data).hexdigest()==expected, 'PRIVATE_INPUT_HASH')
    return json.loads(data)
def env_file(path, expected=None):
    out={}
    data=private_read(path)
    if expected is not None: need(hashlib.sha256(data).hexdigest()==expected,'PRIVATE_FIXTURE_BYTES')
    for line in data.decode().splitlines():
        if not line or line.startswith('#'): continue
        key,sep,value=line.partition('='); need(sep and re.fullmatch('[A-Z0-9_]+',key) and key not in out,'FIXTURE_ENV_FORMAT')
        out[key]=value
    return out

def verify_build(c):
    spec=importlib.util.spec_from_file_location('slot_build_gate', HERE/'build-gate.py')
    gate=importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
    return gate.verify(c, load(HERE/'build-manifest.json'), private_read)

def certificate_commands(tls):
    tls=Path(tls)
    return [
      ['openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','2',
       '-subj','/CN=Disposable slot lab CA','-addext','basicConstraints=critical,CA:TRUE',
       '-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout',str(tls/'ca.key'),'-out',str(tls/'ca.crt')],
      ['openssl','req','-new','-newkey','rsa:2048','-nodes','-sha256','-subj','/CN=mock',
       '-keyout',str(tls/'server.key'),'-out',str(tls/'server.csr')],
      ['openssl','x509','-req','-sha256','-days','2','-in',str(tls/'server.csr'),
       '-CA',str(tls/'ca.crt'),'-CAkey',str(tls/'ca.key'),'-set_serial','1',
       '-extfile',str(HERE/'tls-server.ext'),'-out',str(tls/'server.crt')]]

class Driver:
    def __init__(self,c,output):
        self.c=c; self.root=Path(output); self.run_id='slot-'+secrets.token_hex(6)
        self.owner=self.run_id; self.net=self.owner+'-net'; self.containers=[]; self.network=None
        self.cleanup_errors=[]; self.deadline=mono()+20*60*1000; self.cleaned=False; self.root_created=False
    def journal(self):
        dump(self.root/'cleanup-journal.json', {'owner':self.owner,'network_name':self.net,'network_id':self.network,
          'containers':self.containers,'cleanup_errors':self.cleanup_errors,'cleaned':self.cleaned})
    def cmd(self,args,timeout=30,input=None,cleanup=False):
        timeout=min(timeout,(self.deadline-mono())/1000)
        need(timeout>0,'ROOT_DEADLINE')
        r=subprocess.run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout,
                         env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8'})
        need(r.returncode==0,'OPERATOR_COMMAND_FAILED'); return r.stdout
    def docker(self,*args,**kw): return self.cmd(['docker',*args],**kw)
    def inspect(self,name,cleanup=False): return json.loads(self.docker('inspect',name,cleanup=cleanup))[0]
    def own(self,name,cleanup=False):
        obj=self.inspect(name,cleanup); need(obj['Config'].get('Labels',{}).get(LABEL)==self.owner,'FOREIGN_CONTAINER_DENIED')
        return obj
    def create(self,suffix,image,args,command=()):
        name=self.owner+'-'+suffix
        self.containers.append(name); self.journal() # intention before ambiguous Docker create
        self.docker('create','--pull=never','--name',name,'--label',LABEL+'='+self.owner,'--network',self.net,
          '--log-driver','none','--restart','no','--no-healthcheck','--pids-limit','256','--cpus','2',
          '--security-opt','no-new-privileges',*args,image,*command)
        self.own(name); self.docker('start',name); return name
    def prepare(self):
        need(os.geteuid()==0,'ROOT_ONLY'); need(self.c.get('synthetic_only') is True,'SYNTHETIC_ONLY')
        need(self.root.is_absolute() and not self.root.exists(),'NEW_ABSOLUTE_OWNED_OUTPUT')
        need(not any(p.is_symlink() for p in [self.root,*self.root.parents]),'OUTPUT_SYMLINK_DENIED')
        for key in ('engine_image','node_image','postgres_image','redis_image'): need(immutable(self.c[key]),'LOCAL_IMMUTABLE_IMAGES_REQUIRED')
        need(re.match(r'(?:docker.io/library/)?postgres:18(?:[.-]|@)',self.c['postgres_image']),'POSTGRES18_REQUIRED')
        need(re.match(r'(?:docker.io/library/)?node:24(?:[.-]|@)',self.c['node_image']),'NODE24_REQUIRED')
        self.build=verify_build(self.c)
        image=json.loads(self.docker('image','inspect',self.c['engine_image']))[0]
        need(image['Id']==self.build['image_id'] and hashlib.sha256(json.dumps(image['Config'],sort_keys=True,separators=(',',':')).encode()).hexdigest()==self.build['image_config_sha256'], 'ROOT_RECEIPT_OBSERVED_IMAGE')
        self.root.mkdir(mode=0o700); self.root_created=True; self.journal()
        for name in ('private','evidence'): (self.root/name).mkdir(mode=0o700)
        self.private=self.root/'private'; self.evidence=self.root/'evidence'
        assemble(self.root/'code', Path(self.c['canonical_base_root']) if self.c.get('canonical_base_root') else None)
        fixture=Path(self.c['fixture_dir']); need(fixture.is_absolute() and fixture.is_dir() and not fixture.is_symlink(),'PRIVATE_SYNTHETIC_FIXTURE')
        f=private_json(str(fixture/'profile-fixture.json'), self.c['fixture_attestation_sha256']); need(f['source']=='transport-isolated-r4' and f['status']=='PASS' and f['real_provider_keys_copied'] is False,'SYNTHETIC_FIXTURE_ATTESTATION')
        need(f['images']['postgres']==self.c['postgres_image'] and f['images']['redis']==self.c['redis_image'],'FIXTURE_DEPENDENCY_IMAGE_PINS')
        for name in ('snapshot.sql','engine.env','lab.json'):
            data=private_read(str(fixture/name)); need(hashlib.sha256(data).hexdigest()==f['hashes'][name],'PRIVATE_FIXTURE_BYTES')
        e=env_file(fixture/'engine.env', f['hashes']['engine.env']); lab=private_json(fixture/'lab.json', f['hashes']['lab.json']); self.snapshot=fixture/'snapshot.sql'; self.snapshot_sha=f['hashes']['snapshot.sql']
        need(e['DATABASE_HOST']=='postgres' and e['REDIS_HOST']=='redis' and e.get('RUN_MODE','standard')=='standard','ISOLATED_STANDARD_FIXTURE')
        need(e.get('DATABASE_SSLMODE','disable')=='disable' and len(lab['admin_bearer'])>=24,'FIXTURE_DB_OR_NATIVE_ADMIN')
        need(re.fullmatch('[a-z][a-z0-9_]{0,30}',e['DATABASE_USER']) and re.fullmatch('[a-z][a-z0-9_]{0,30}',e['DATABASE_DBNAME']),'PRIVATE_DB_IDENTIFIERS')
        self.dbuser=e['DATABASE_USER']; self.dbname=e['DATABASE_DBNAME']
        redis_password=secrets.token_hex(32)
        # Password appears only in mode-0600 mounted files, never argv/env/logs.
        (self.private/'redis.conf').write_text('bind 0.0.0.0\nport 6379\nprotected-mode yes\nsave ""\nappendonly no\nrequirepass '+redis_password+'\n')
        (self.private/'redis.conf').chmod(0o600)
        pg={'POSTGRES_USER':self.dbuser,'POSTGRES_DB':self.dbname,'POSTGRES_PASSWORD':e['DATABASE_PASSWORD'],'PGDATA':'/var/lib/postgresql/18/docker'}
        (self.private/'postgres.env').write_text(''.join(k+'='+v+'\n' for k,v in pg.items())); (self.private/'postgres.env').chmod(0o600)
        config={'server':{'host':'0.0.0.0','port':8080,'mode':'release','max_request_body_size':2097152}, 'run_mode':'standard',
          'database':{'host':'postgres','port':5432,'user':self.dbuser,'password':e['DATABASE_PASSWORD'],'dbname':self.dbname,'sslmode':'disable'},
          'redis':{'host':'redis','port':6379,'password':redis_password,'db':0}, 'jwt':{'secret':e['JWT_SECRET'],'expire_hour':24},
          'security':{'url_allowlist':{'enabled':True,'allow_insecure_http':False,'allow_private_hosts':True,'upstream_hosts':['mock']}},
          'gateway':{'max_body_size':2097152,'text_max_body_size':2097152,'max_account_switches':0,'max_account_switches_gemini':0,'failover_on_400':False,
            'log_upstream_error_body':False,'response_header_timeout':30,'openai_response_header_timeout':30,
            'scheduling':{'sticky_session_wait_timeout':'15s','fallback_wait_timeout':'15s','sticky_session_max_waiting':3,'fallback_max_waiting':3}},
          'log':{'level':'error','output_to_file':False,'output_to_stdout':True}}
        # JSON is valid YAML and avoids handwritten secret escaping.
        dump(self.private/'config.yaml',config)
        safe_env={'SKIP_SETUP':'true','CONFIG_FILE':'/private/config.yaml','DATA_DIR':'/app/data','RUN_MODE':'standard',
                  'SSL_CERT_FILE':'/private/tls/ca.crt','LOG_OUTPUT_TO_FILE':'false','LOG_OUTPUT_TO_STDOUT':'true','TOTP_ENCRYPTION_KEY':e.get('TOTP_ENCRYPTION_KEY',secrets.token_hex(32))}
        (self.private/'engine.env').write_text(''.join(k+'='+v+'\n' for k,v in safe_env.items())); (self.private/'engine.env').chmod(0o600)
        self.lab={'run_id':self.run_id,'admin_bearer':lab['admin_bearer'],'redis_password':redis_password,
          'control_token':secrets.token_hex(32),'sentinels':{p:'rr-synthetic-'+secrets.token_hex(24) for p in ('responses','messages')},
          'mock_url':'https://mock:8099','engine_url':'http://sub2api:8080',
          'deployment':{k:self.build[k] for k in ('image','binary_sha256','source_manifest_sha256','image_config_sha256')}}
        dump(self.private/'lab.json',self.lab); dump(self.private/'supervisor.json',{'deadline_ms':self.deadline-15000})
        for key in ('engine_image','node_image','postgres_image','redis_image'): self.docker('image','inspect',self.c[key])
    def generate_tls(self):
        # Root runtime only. No certificate/key bytes or hashes enter evidence.
        need(os.geteuid()==0, 'ROOT_ONLY')
        tls=self.private/'tls'; tls.mkdir(mode=0o700)
        old=os.umask(0o077)
        try:
            for command in certificate_commands(tls): self.cmd(command)
            for p in tls.iterdir(): p.chmod(0o600)
        finally: os.umask(old)

    def snapshot_bytes(self):
        data=private_read(self.snapshot); need(hashlib.sha256(data).hexdigest()==self.snapshot_sha,'PRIVATE_FIXTURE_BYTES'); return data
    def sql(self,query):
        return self.docker('exec',self.pg,'psql','-At','-v','ON_ERROR_STOP=1','-U',self.dbuser,'-d',self.dbname,'-c',query).decode().strip()
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
        self.network=self.docker('network','create','--internal','--label',LABEL+'='+self.owner,self.net).decode().strip(); self.journal()
        self.pg=self.create('postgres',self.c['postgres_image'],['--network-alias','postgres','--env-file',str(self.private/'postgres.env'),
          '--tmpfs','/var/lib/postgresql:rw,size=1g','--memory','768m'])
        self.wait_postgres(self.pg)
        need(self.sql('SHOW server_version_num;').startswith('18'),'ACTUAL_POSTGRES18_VERSION')
        self.docker('exec','-i',self.pg,'psql','-v','ON_ERROR_STOP=1','-U',self.dbuser,'-d',self.dbname,input=self.snapshot_bytes(),timeout=40)
        # A dedicated authenticated cache is always empty initially. DB must have
        # no accounts or API keys from the restored synthetic control snapshot.
        need(self.sql('SELECT count(*) FROM accounts;')=='0' and self.sql('SELECT count(*) FROM api_keys;')=='0','NONEMPTY_SYNTHETIC_DB')
        self.redis=self.create('redis',self.c['redis_image'],['--network-alias','redis','--user','0:0','--memory','128m',
          '--cap-drop','ALL','--entrypoint','redis-server','--tmpfs','/data:rw,size=16m','--mount',f'type=bind,src={self.private}/redis.conf,dst=/private/redis.conf,readonly'],
          ('/private/redis.conf',))
        node_args=['--env','NODE_EXTRA_CA_CERTS=/private/tls/ca.crt','--user','0:0','--read-only','--cap-drop','ALL','--tmpfs','/tmp:rw,size=16m','--memory','256m','--workdir','/lab',
          '--mount',f'type=bind,src={self.root}/code,dst=/lab,readonly','--mount',f'type=bind,src={self.private},dst=/private',
          '--mount',f'type=bind,src={self.evidence},dst=/evidence']
        self.mock=self.create('mock',self.c['node_image'],['--network-alias','mock',*node_args],('node','sub2api-regression-lab/mock.mjs'))
        # Engine uses only trusted private native config; no broker or external
        # ports/networks. No read-write mount of product source or auth homes.
        self.engine=self.create('engine',self.c['engine_image'],['--network-alias','sub2api','--user','0:0','--memory','768m',
          '--cap-drop','ALL','--entrypoint','/app/sub2api','--tmpfs','/app/data:rw,size=64m','--tmpfs','/tmp:rw,size=32m','--env-file',str(self.private/'engine.env'),
          '--mount',f'type=bind,src={self.private}/config.yaml,dst=/private/config.yaml,readonly',
          '--mount',f'type=bind,src={self.private}/tls/ca.crt,dst=/private/tls/ca.crt,readonly'])
        obj=self.own(self.engine); image=json.loads(self.docker('image','inspect',self.c['engine_image']))[0]
        config_hash=hashlib.sha256(json.dumps(image['Config'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        need(config_hash==self.build['image_config_sha256'],'ACTUAL_IMAGE_CONFIG_BINDING')
        need(image['Id']==self.build['image_id'] and obj['Image']==image['Id'] and not obj['HostConfig']['PortBindings'] and list(obj['NetworkSettings']['Networks'])==[self.net],'ACTUAL_ENGINE_ISOLATION')
        ready=min(self.deadline,mono()+15000)
        while mono()<ready:
            obj=self.own(self.engine); pid=obj['State']['Pid']
            if pid>0 and sha(Path('/proc')/str(pid)/'exe')==self.build['binary_sha256']: break
            time.sleep(.1)
        else: raise ValueError('ACTUAL_NATIVE_BINARY_BINDING')
        dump(self.evidence/'deployment.json',{'status':'INSPECTED','image_id':image['Id'],'container_id':obj['Id'],
          'binary_sha256':self.build['binary_sha256'],'image_config_sha256':config_hash,'source_manifest_sha256':self.build['source_manifest_sha256'],
          'build_attestation_sha256':self.c['build_attestation_sha256'],
          'trust_model':'external-root-build-receipt', 'source_fingerprint_sha256':self.build['source_fingerprint_sha256'],
          'production_patch_sha256':self.build['production_patch_sha256'], 'build_id':self.build['build_id'], 'components':{k:v['sha256'] for k,v in self.build['components'].items()},
          'postgres_major':18,'internal_network':True,'published_ports':False,'private_redis_auth':True})
        self.operator=self.create('operator',self.c['node_image'],node_args,('node','sub2api-slot-lab/run.mjs'))
        # Bounded inspect polls: do not let a Docker wait process outlive budget.
        while mono()<self.deadline-10000:
            state=self.own(self.operator)['State']
            if not state['Running']:
                need(state['ExitCode']==0,'NATIVE_SLOT_GATE_FAILED')
                need(load(self.evidence/'result.json')['status']=='PASS' and load(self.evidence/'final-zero.json')['status']=='PASS','ALL_84_AND_FINAL_ZERO_REQUIRED')
                return
            time.sleep(.5)
        raise ValueError('ROOT_DEADLINE')
    def cleanup(self):
        # Only label-verified exact resource identities. No prune, foreign IDs,
        # Redis lease deletes, global SCAN or flush. Kept journal allows audit.
        for name in list(reversed(self.containers)):
            try:
                obj=self.own(name,cleanup=True); self.docker('rm','-f','-v',obj['Id'],cleanup=True,timeout=5)
                self.containers.remove(name)
            except Exception:
                # Distinguish absent ambiguous creation from a surviving owned
                # container/foreign collision, without printing Docker output.
                try:
                    names=self.docker('container','ls','-a','--filter','name=^/'+name+'$','--format','{{.Names}}',cleanup=True).decode().splitlines()
                    if name not in names: self.containers.remove(name)
                    else: self.cleanup_errors.append({'resource':name,'code':'OWNERSHIP_OR_REMOVE_FAILED'})
                except Exception: self.cleanup_errors.append({'resource':name,'code':'CLEANUP_OBSERVATION_FAILED'})
            self.journal()
        try:
            rows=json.loads(self.docker('network','inspect',self.net,cleanup=True))
            n=rows[0]; need(n.get('Labels',{}).get(LABEL)==self.owner,'FOREIGN_NETWORK_DENIED')
            if self.network: need(n['Id']==self.network,'NETWORK_ID_CHANGED')
            self.docker('network','rm',n['Id'],cleanup=True,timeout=5); self.network=None
        except Exception:
            try:
                names=self.docker('network','ls','--filter','name=^'+self.net+'$','--format','{{.Name}}',cleanup=True).decode().splitlines()
                if self.net in names: self.cleanup_errors.append({'resource':self.net,'code':'NETWORK_CLEANUP_FAILED'})
            except Exception: self.cleanup_errors.append({'resource':self.net,'code':'NETWORK_CLEANUP_OBSERVATION_FAILED'})
        self.cleaned=not self.containers and not self.cleanup_errors; self.journal()

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--config',required=True); p.add_argument('--output',required=True)
    a=p.parse_args(); need(os.geteuid()==0,'ROOT_ONLY'); c=private_json(a.config); d=Driver(c,a.output)
    def stop(*_): raise ValueError('OPERATOR_INTERRUPTED')
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,stop)
    status='FAIL'; reason=None
    try: d.prepare(); d.generate_tls(); d.launch(); status='PASS'
    except Exception as e: reason=str(e) if isinstance(e,ValueError) else 'OPERATOR_RUNTIME_FAILED'
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,signal.SIG_IGN)
        if d.root_created:
            d.cleanup()
            if not d.cleaned: status='FAIL'; reason=reason or 'CLEANUP_INCOMPLETE'
            dump(d.root/'root-result.json',{'status':status,'reason':reason,'cleanup':d.cleaned,'real_provider':False})
    print(json.dumps({'status':status,'output':str(d.root),'cleanup':d.cleaned})); return 0 if status=='PASS' else 1

if __name__=='__main__': raise SystemExit(main())
