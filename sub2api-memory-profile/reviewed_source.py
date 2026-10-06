"""Thin offline extension: apply reviewed, exact hash-pinned native Go patches.
No fuzzy matching, Git, downloads, platform abstraction, or receipt promotion.
"""
from pathlib import Path
import hashlib,re
from contracts import require,strict_json
from launch_contracts import digest

def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def apply_patch(files,text):
    lines=text.splitlines(keepends=True);i=0;changed=set()
    while i<len(lines):
        if lines[i].startswith(('diff --git ','index ')):
            i+=1;continue
        require(lines[i].startswith('--- a/backend/') or lines[i]=='--- /dev/null\n','PATCH_OLD_PATH')
        new_file=lines[i]=='--- /dev/null\n'
        name=None if new_file else lines[i][6:].strip();i+=1
        require(i<len(lines) and lines[i].startswith('+++ b/backend/'),'PATCH_NEW_PATH')
        new_name=lines[i][6:].strip();require(new_file or name==new_name,'PATCH_NEW_PATH');name=new_name;i+=1
        require((name not in files if new_file else name in files) and name.startswith('backend/') and name.endswith('.go') and name!='backend/cmd/server/rr_sub2_profile.go' and Path(name).as_posix()==name and '..' not in Path(name).parts and name not in changed,'PATCH_SOURCE_SCOPE')
        old=[] if new_file else files[name].decode().splitlines(keepends=True);out=[];cursor=0;hunks=0
        while i<len(lines) and lines[i].startswith('@@ '):
            m=re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n',lines[i]);require(m is not None,'PATCH_HUNK_HEADER')
            start=max(0,int(m[1])-1);oldn=int(m[2] or 1);newn=int(m[4] or 1);i+=1
            require(cursor<=start<=len(old),'PATCH_HUNK_ORDER');out+=old[cursor:start];cursor=start;seen_old=seen_new=0
            require(int(m[3])-1==len(out),'PATCH_NEW_OFFSET')
            while i<len(lines) and not lines[i].startswith(('@@ ','--- ','diff --git ','index ')):
                l=lines[i];i+=1;require(l and l[0] in ' +-','PATCH_HUNK_LINE')
                if l[0] in ' -':
                    require(cursor<len(old) and old[cursor]==l[1:],'PATCH_CONTEXT_MISMATCH');cursor+=1;seen_old+=1
                if l[0] in ' +':out.append(l[1:]);seen_new+=1
            require((seen_old,seen_new)==(oldn,newn),'PATCH_HUNK_COUNTS');hunks+=1
        require(hunks>0,'PATCH_MISSING_HUNKS');files[name]=''.join(out+old[cursor:]).encode();changed.add(name)
    require(changed,'PATCH_EMPTY');return changed

def apply_reviewed(path,legacy,source_bytes):
    spec=strict_json(path.read_text())
    require(type(spec) is dict and set(spec)=={'schema','base_manifest_sha256','base_image','binary_sha256','patches'},'REVIEWED_FIELDS')
    require(spec['schema']=='rrsub2profile-reviewed-v1' and spec['base_manifest_sha256']==sha_bytes(legacy.read_bytes()),'REVIEWED_BASE_MANIFEST')
    from launch_contracts import BASE
    require(spec['base_image']==BASE and digest(spec['binary_sha256']),'REVIEWED_BASE_BINARY')
    require(type(spec['patches']) is list and 1<=len(spec['patches'])<=2,'REVIEWED_PATCH_LIST')
    receipts=[]
    for row in spec['patches']:
        require(type(row) is dict and set(row)=={'path','sha256','files'},'REVIEWED_PATCH_FIELDS')
        require(type(row['path']) is str and Path(row['path']).is_absolute() and digest(row['sha256']),'REVIEWED_PATCH_PIN')
        p=Path(row['path']);b=p.read_bytes();require(sha_bytes(b)==row['sha256'],'REVIEWED_PATCH_HASH')
        fs=row['files'];require(type(fs) is dict and fs,'REVIEWED_FILE_MAP')
        for name,h in fs.items():
            require(type(h) is dict and set(h)=={'before_sha256','after_sha256'} and (h['before_sha256'] is None or digest(h['before_sha256'])) and digest(h['after_sha256']),'REVIEWED_FILE_HASH_FIELDS')
            require((name not in source_bytes if h['before_sha256'] is None else name in source_bytes and sha_bytes(source_bytes[name])==h['before_sha256']),'REVIEWED_BEFORE_HASH')
        changed=apply_patch(source_bytes,b.decode());require(changed==set(fs),'REVIEWED_PATCH_FILE_LIST')
        require(all(sha_bytes(source_bytes[n])==fs[n]['after_sha256'] for n in changed),'REVIEWED_AFTER_HASH')
        receipts.append({'sha256':row['sha256'],'files':fs})
    return {'schema':spec['schema'],'base_manifest_sha256':spec['base_manifest_sha256'],'base_image':BASE,'binary_sha256':spec['binary_sha256'],'patches':receipts,'reviewed_manifest_sha256':sha_bytes(path.read_bytes())}
