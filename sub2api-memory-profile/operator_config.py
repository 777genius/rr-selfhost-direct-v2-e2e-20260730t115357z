#!/usr/bin/env python3
"""Controller-only offline config migration; never exports private values.
Read the existing synthetic config and reviewed W1 stdlib freeze. The actual
Go executable/version/stdlib are checked separately by root-driver preflight.
"""
import argparse,hashlib,json,os,stat
from pathlib import Path
from contracts import require,strict_json
from prepare import sha
from launch_contracts import config_gate,toolchain_gate

def private_parent(path):
    require(path.is_absolute() and path.name not in ('','.', '..') and '..' not in path.parts,'OUTPUT_PATH_REQUIRED')
    # Traverse with directory descriptors: no symlink ancestor can redirect publication.
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parent.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        st=os.fstat(fd)
        require(st.st_uid==os.geteuid() and stat.S_IMODE(st.st_mode)==0o700,'PRIVATE_OUTPUT_PARENT_REQUIRED')
        return fd
    except BaseException:
        os.close(fd);raise

def migrate(old,out,receipt,freeze,cache,collector):
    c=strict_json(old.read_text())
    require(out!=receipt,'OUTPUT_REUSE_DENIED')
    require(sha(Path(c['go_binary']))==c['go_binary_sha256'],'TOOLCHAIN_PIN')
    require(cache.is_dir() and collector.is_file(),'OFFLINE_INPUTS_MISSING')
    r={'go_version':'go1.27.1','go_binary_sha256':c['go_binary_sha256'],'compilation_cache':str(cache),
      'stdlib_sha256':{n:sha(freeze/n) for n in ('runtime/mprof.go','runtime/mstats.go','runtime/pprof/pprof.go','runtime/pprof/protomem.go')}}
    receipt_bytes=(json.dumps(r,indent=2)+'\n').encode()
    c.update(compilation_cache=str(cache),toolchain_receipt=str(receipt),collector_source=str(collector),
      toolchain_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest())
    config_gate(c);toolchain_gate(r,c)
    config_bytes=(json.dumps(c,indent=2)+'\n').encode()
    parents=[];created=[]
    try:
        # Validate both destinations before first creation. O_EXCL also closes
        # the check/create race; a concurrent existing output is never overwritten.
        for path in (receipt,out):
            fd=private_parent(path);parents.append((path,fd))
            try:os.stat(path.name,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:require(False,'OUTPUT_REUSE_DENIED')
        for (path,parent),data in zip(parents,(receipt_bytes,config_bytes)):
            fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            created.append((path,parent,fd,os.fstat(fd)))
        for (_,_,fd,_),data in zip(created,(receipt_bytes,config_bytes)):
            view=memoryview(data)
            while view:
                count=os.write(fd,view);require(count>0,'PRIVATE_OUTPUT_WRITE_FAILED');view=view[count:]
            os.fsync(fd)
    except BaseException:
        for path,parent,fd,initial in reversed(created):
            try:
                current=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
                if (current.st_dev,current.st_ino)==(initial.st_dev,initial.st_ino):os.unlink(path.name,dir_fd=parent)
            except FileNotFoundError:pass
        raise
    finally:
        for _,_,fd,_ in created:os.close(fd)
        for _,fd in parents:os.close(fd)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for key in ('old-config','out','receipt','stdlib-freeze','compilation-cache','collector-source'):ap.add_argument('--'+key,type=Path,required=True)
    a=ap.parse_args()
    try:
        migrate(a.old_config.resolve(),a.out.absolute(),a.receipt.absolute(),a.stdlib_freeze.resolve(),a.compilation_cache.resolve(),a.collector_source.resolve())
    except Exception:raise SystemExit('PRIVATE_CONFIG_MIGRATION_STOP_NO_VALUES_EXPORTED')
    print('PRIVATE_CONFIG_AND_REVIEWED_TOOLCHAIN_RECEIPT_WRITTEN')
