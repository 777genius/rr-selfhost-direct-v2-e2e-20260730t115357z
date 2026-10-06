"""Run unchanged frozen suites with the supplied complete W2 original input tree.
Only offline Python/Node subprocesses; disposable assembly stays in our package.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
OWN=Path(__file__).resolve().parent
ROOT=OWN.parent

def run():
    evidence=OWN/'evidence';env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    original=ROOT/'.spike-inputs/original-inputs'
    require=original/'INPUT-HASHES.json'
    if not require.is_file():raise SystemExit('COMPLETE_ORIGINAL_W2_INPUTS_REQUIRED')
    results={}
    with tempfile.TemporaryDirectory(dir=evidence) as td:
        harness=Path(td);package=harness/'sub2api-memory-profile';package.mkdir();(package/'evidence').mkdir()
        for p in OWN.iterdir():
            if p.is_file():shutil.copyfile(p,package/p.name)
        shutil.copytree(OWN/'overlay',package/'overlay')
        (harness/'.spike-inputs').symlink_to(original,target_is_directory=True)
        for name in ('sub2api-spike','sub2api-transport-r4'):
            (harness/name).symlink_to(ROOT/name,target_is_directory=True)
        commands={
          'python-tests-w3':[sys.executable,'-m','unittest','discover','-s',str(package),'-p','test_*.py','-v'],
          'node-tests-w3':['node','--test',str(package/'offline.test.mjs')],
          'source-audit-w3':[sys.executable,str(package/'prepare.py'),'--verify-only','--out',str(evidence/'source-audit-w3.json')],
          'actual-audit-w3':[sys.executable,str(package/'audit_actual.py'),'--out',str(evidence/'actual-audit-w3.json')],
        }
        for name,cmd in commands.items():
            cp=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=90)
            (evidence/(name+'.txt')).write_text(cp.stdout+cp.stderr)
            results[name]={'returncode':cp.returncode}
    # The prescribed reviewer script is byte-for-byte untouched. Its positive
    # assertions detect vulnerabilities, so PASS means reproduced, FAIL removed.
    for side in ('original','fixed'):
        with tempfile.TemporaryDirectory(dir=evidence) as td:
            base=Path(td);(base/'harness').mkdir()
            target=ROOT/'.spike-inputs/candidate/sub2api-memory-profile' if side=='original' else OWN
            (base/'harness/sub2api-memory-profile').symlink_to(target,target_is_directory=True)
            shutil.copyfile(evidence/'review-w2-original/reproduce.py',base/'reproduce.py')
            cp=subprocess.run([sys.executable,str(base/'reproduce.py')],capture_output=True,text=True,env=env,timeout=30)
        (evidence/('prescribed-'+side+'-w3.txt')).write_text(cp.stdout+cp.stderr)
        results['prescribed-'+side]={'returncode':cp.returncode,'meaning':'vulnerability assertions'}
    # Identical fixed-contract regression assertions against old and new code.
    with tempfile.TemporaryDirectory(dir=evidence) as td:
        old=Path(td)/'sub2api-memory-profile'
        shutil.copytree(ROOT/'.spike-inputs/candidate/sub2api-memory-profile',old)
        shutil.copyfile(OWN/'test_w3_regressions.py',old/'test_w3_regressions.py')
        cp=subprocess.run([sys.executable,str(old/'test_w3_regressions.py')],capture_output=True,text=True,env=env,timeout=30)
        (evidence/'regressions-old-red-w3.txt').write_text(cp.stdout+cp.stderr)
        results['regressions-old-red']={'returncode':cp.returncode}
    cp=subprocess.run([sys.executable,str(OWN/'test_w3_regressions.py')],capture_output=True,text=True,env=env,timeout=30)
    (evidence/'regressions-new-green-w3.txt').write_text(cp.stdout+cp.stderr)
    results['regressions-new-green']={'returncode':cp.returncode}
    results['legacy_full_analyzer_fixture']='NOT RUN: complete W1 actual-execution/case/collector/profile fixture tree absent; original skipped class retained'
    results['runtime']='NOT RUN: no Go/Docker/root/network/key/auth/Git-write/subagent operations'
    (evidence/'verification-w3.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
    return 0 if all(results[n]['returncode']==0 for n in commands) and results['prescribed-original']['returncode']==0 and results['prescribed-fixed']['returncode']!=0 and results['regressions-old-red']['returncode']!=0 and results['regressions-new-green']['returncode']==0 else 1

if __name__=='__main__':raise SystemExit(run())
