#!/usr/bin/env python3
"""Fresh relocated CLI and meaningful source/evidence rejection checks."""
import sys
sys.dont_write_bytecode=True
import argparse,copy,importlib.util,json,shutil,subprocess,tempfile
from pathlib import Path
import prepare
O=Path(__file__).resolve().parent
require=prepare.require
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,O/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upstream',type=Path,required=True);p.add_argument('--gofmt',type=Path,required=True);a=p.parse_args();a.upstream=a.upstream.resolve();a.gofmt=a.gofmt.resolve()
    runtime=module('runtime','verify-runtime-receipts.py');verifier=module('verifier','verify-artifacts.py');scanner=module('scanner','scan-package.py')
    source=prepare.prepare(a.upstream,a.gofmt)[0];b=json.loads((O/'actual-bindings.json').read_text());data=runtime.actual_suite(O/'evidence','full-green',b);names=set(data[2]['observations']);name=sorted(names)[0];checks=[]
    def reject(label,fn):
        try:fn()
        except (ValueError,OSError,KeyError,TypeError):checks.append(label);return
        raise ValueError('missing meaningful rejection: '+label)
    altered=copy.deepcopy(data);altered[2]['receipts'][name]['barriers']=[]
    reject('missing real database barriers',lambda:runtime.actual_races(names,altered,False))
    altered=copy.deepcopy(data);altered[2]['observations'][name]['backend_a']=altered[2]['observations'][name]['backend_b']
    reject('duplicate PostgreSQL backend IDs',lambda:runtime.actual_races(names,altered,False))
    altered=copy.deepcopy(data);excluded=altered[2]['receipts'][name]['synthetic_account_id'];altered[2]['effects'][name]['bulk_event_ids']=[[excluded]];altered[2]['effects'][name]['cache_effect_ids']=[excluded]
    reject('same-count excluded ID replaces allowed native ID',lambda:runtime.actual_races(names,altered,False))
    altered=copy.deepcopy(data);altered[2]['effects'][name]['cache_after_commit']=False
    reject('cache publication before commit',lambda:runtime.actual_races(names,altered,False))
    altered=copy.deepcopy(data);altered[2]['observations'][name]['converted_revision_unchanged']=False
    reject('excluded converted revision mutation',lambda:runtime.actual_races(names,altered,False))
    changed=source.copy();changed['backend/go.mod']+=b'\n'
    reject('complete actual source mutation',lambda:runtime.validate_actual(O/'evidence',changed))
    changed=source.copy();changed['backend/extra-unexecuted.go']=b'package unwanted\n'
    reject('unexecuted extra backend file',lambda:runtime.validate_actual(O/'evidence',changed))
    changed=source.copy();changed['backend/internal/repository/oauth_bulk_affected_ids_test.go']+=b'\n'
    reject('identical regression source mutation',lambda:runtime.validate_actual(O/'evidence',changed))
    reject('already-applied production patch',lambda:prepare.apply_exact(source.copy(),O/'bulk-production.patch'))
    with tempfile.TemporaryDirectory(prefix='.verification-',dir=O) as temp:
        root=Path(temp);bundle=root/'standalone';bundle.mkdir()
        for f in O.iterdir():
            if f.is_file():shutil.copyfile(f,bundle/f.name)
        shutil.copytree(O/'evidence',bundle/'evidence')
        # Relocated CLI has no sibling package, runtime-private environment or DSN.
        cmd=[sys.executable,'-B',str(bundle/'prepare.py'),'--upstream',str(a.upstream),'--gofmt',str(a.gofmt)]
        env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
        def run(args):
            r=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True);require(r.returncode==0,'fresh external CLI failed: '+r.stderr);return json.loads(r.stdout)
        prepared=root/'prepared';run(cmd+['--output',str(prepared)])
        require(prepare.read_tree(prepared)==source,'fresh prepared full tree differs from bound actual source')
        checks.append('fresh relocated prepare full output exact to actual3158 ledger')
        verified=run([sys.executable,'-B',str(bundle/'verify-runtime-receipts.py'),'--source',str(prepared)])
        require(verified['actual_GREEN_terminals']==211,'fresh actual source gate mismatch');checks.append('fresh relocated actual-receipt CLI PASS')
        refused=subprocess.run(cmd+['--output',str(prepared)],env=env,capture_output=True,text=True)
        require(refused.returncode==1 and prepare.read_tree(prepared)==source,'no-overwrite failed');checks.append('no-overwrite leaves output byte-exact')
        bad=root/'offset.patch';bad.write_text((O/'w9-to-final.patch').read_text().replace('@@ -9,7 +9,6 @@','@@ -10,7 +10,6 @@'))
        current=source.copy();handler='backend/internal/handler/admin/openai_oauth_handler.go';rows=current[handler].splitlines(True);current[handler]=b''.join(rows[:11]+[b'\t"github.com/Wei-Shaw/sub2api/internal/pkg/openai"\n']+rows[11:])
        reject('zero-offset shifted hunk',lambda:prepare.apply_exact(current.copy(),bad))
        bad.write_text((O/'w9-to-final.patch').read_text().replace('"time"','"modified_time"'))
        reject('zero-fuzz changed context',lambda:prepare.apply_exact(current.copy(),bad))
        bad.write_text((O/'w9-to-final.patch').read_text().replace('b/backend/','b/../backend/',1))
        reject('path traversal',lambda:prepare.apply_exact(current.copy(),bad))
        (bundle/'evidence/full-green.jsonl').write_bytes((bundle/'evidence/full-green.jsonl').read_bytes()+b'\n')
        # Check tampering at CLI integrity boundary, without rewriting producer receipts.
        r=subprocess.run([sys.executable,'-B',str(bundle/'verify-runtime-receipts.py'),'--source',str(prepared)],env=env,capture_output=True,text=True)
        require(r.returncode==1 and 'supplied actual artifact changed' in r.stderr,'changed raw receipt log accepted');checks.append('raw receipt integrity tamper rejection')
        empty=root/'empty.jsonl';empty.write_bytes(b'');reject('empty four-package compile',lambda:runtime.compile_gate(empty))
    require(scanner.scan(O)['result']=='PASS','package private-material scan failed')
    source_result=verifier.source_checks(a.upstream,a.gofmt)
    print(json.dumps({'result':'PASS','negative_and_external_checks':checks,'count':len(checks),'source_verification':source_result,'actual_receipt_verification':runtime.validate_actual(O/'evidence',source),'scanner':'ON','receipt_integrity':'unchanged exact supplied hashes','worker_Go_or_services':'NOT RUN','critical_independent_review':'W7 PENDING'},indent=2))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,IndexError) as e:print(json.dumps({'result':'FAIL','reason':str(e)}),file=sys.stderr);sys.exit(1)
