#!/usr/bin/env python3
"""Enabled bounded lexical scan for private runtime material in this package."""
import argparse,json,re,sys
from pathlib import Path
PATTERNS={
 'private-key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
 'credentialed-service-URL':r'(?:postgres(?:ql)?|redis)://[^\s"\x27/]+:[^\s"\x27@]+@',
 'runtime-private-path':r'/(?:srv/(?:worker-state|workers)|etc/subscription-runtime|root)/',
 'provider-key':r'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}',
 'AWS-key':r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
 'JWT-value':r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b',
}
def scan(root):
    findings=[];paths=list(root.rglob('*'))
    for p in paths:
        if not p.is_file():continue
        text=p.read_bytes().decode('utf-8')
        for kind,pattern in PATTERNS.items():
            if re.search(pattern,text):findings.append({'path':p.relative_to(root).as_posix(),'kind':kind})
    return {'result':'FAIL' if findings else 'PASS','scanner':'ON','scope':'bounded lexical private-material checks; original source literals and synthetic fixture values preserved','files':sum(p.is_file() for p in paths),'findings':findings,'encoding_or_waiver':False}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,default=Path(__file__).resolve().parent);a=p.parse_args();r=scan(a.package);print(json.dumps(r,indent=2));sys.exit(bool(r['findings']))
