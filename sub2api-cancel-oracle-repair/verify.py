"""Focused reproducible offline RED/GREEN plus source preservation and actual-row audit."""
import sys
sys.dont_write_bytecode = True
import hashlib, json, os, re, subprocess, tempfile
from pathlib import Path
from prepare import prepare, OWN, INPUT, MODULES, digest

def main():
    changed, ledger=prepare()
    (OWN/'w2-source-ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
    original={n:(INPUT/'canonical'/n).read_text() for n in MODULES}
    before=original['sub2api-regression-lab/receipts.mjs']; after=changed['sub2api-regression-lab/receipts.mjs']
    assert before[:before.index('export function cancellationVerdict')] == after[:after.index('export function cancellationVerdict')]
    assert before[before.index('export function telemetryVerdict'):] == after[after.index('export function telemetryVerdict'):]
    before=original['sub2api-regression-lab/run.mjs']; after=changed['sub2api-regression-lab/run.mjs']
    assert before[before.index('async function uncertain('):] == after[after.index('async function uncertain('):]
    assert before[:before.index('async function setup(')] == after[:after.index('async function setup(')]
    assert before[before.index('export async function cleanup('):before.index('async function broker(')] == after[after.index('export async function cleanup('):after.index('async function broker(')]
    assert "await control(c, 'release', { id: spec.id });" not in after[after.index('async function cancel('):after.index('async function uncertain(')]
    evidence=OWN/'w2-evidence';evidence.mkdir(exist_ok=True)
    tests=['oracle.test.mjs','broker.test.mjs','runner.test.mjs']
    test_hashes={n:digest((OWN/n).read_bytes()) for n in tests}
    results={}
    with tempfile.TemporaryDirectory(prefix='.offline-',dir=OWN) as tmp:
        for mode in ['old','new']:
            stage=Path(tmp)/mode; prepare(stage,baseline=mode=='old')
            env=dict(os.environ,CANCEL_CODE=str(stage))
            syntax=[]
            for name in MODULES:
                result=subprocess.run(['node','--check',str(stage/name)],capture_output=True,text=True)
                assert result.returncode==0,result.stderr
                syntax.append(name)
            cmd=['node','--experimental-vm-modules','--test','--test-reporter=tap']+[str(OWN/n) for n in tests]
            r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=60)
            tap=r.stdout+r.stderr;(evidence/(mode+'.tap')).write_text(tap)
            counts={k:int(re.search(r'^# '+k+r' (\d+)$',tap,re.M)[1]) for k in ['tests','pass','fail','cancelled','skipped']}
            results[mode]={'exit_code':r.returncode,**counts,'syntax_checked':syntax,'test_sha256':test_hashes}
            if mode=='old': assert r.returncode!=0 and counts['fail']>0 and counts['cancelled']==0
            else: assert r.returncode==0 and counts['fail']==0 and counts['skipped']==0 and counts['cancelled']==0,tap
    image=json.loads((INPUT/'actual-image.json').read_text())
    rows=[]
    for path in sorted((INPUT/'actual-faults').glob('*.json')):
        row=json.loads(path.read_text());r=row['upstream'][0];d=row['downstream']
        assert row['deployment']['image'].endswith(image['image_id'])
        assert row['deployment']['clock']=='linux-CLOCK_MONOTONIC'
        assert r==row['upstream_at_immediate_oracle'][0]
        rows.append({'id':row['id'],'source_sha256':digest(path.read_bytes()),'recorded_status':row['status'],
          'recorded_reason':row['reason'],'trusted_cancel_policy':row['trusted_native_cancel_policy'],
          'action_requested_ms':row['action_requested_ms'],'physical_close_ms':r['close_ms'],
          'broker_response_close_ms':row['broker_boundary_close_ms'],
          'physical_minus_response_ms':r['close_ms']-row['broker_boundary_close_ms'],
          'physical_minus_setup_action_ms':r['close_ms']-row['action_requested_ms'],
          'downstream_http_status':d['http_status'],'downstream_transport':d['transport'],
          'downstream_terminal_ms':d['terminal_ms'],'finished':r['finished'],'effects':r['effects'],
          'terminal_ms':r['terminal_ms'],'release_ms':r['release_ms'],'reset_ms':r['reset_ms'],
          'healthy_ack_bytes':row['preparation_control']['downstream']['ack_frame_bytes'],'early_ack_bytes':d['ack_frame_bytes'],
          'causal_pre_abort_observed':False,'historical_receipt_promoted':False})
    audit={'input_image_id':image['image_id'],'input_binary_sha256':image['binary_sha256'],
      'rows':rows,'summary':{'rows':len(rows),'recorded_fail':sum(r['recorded_status']=='FAIL' for r in rows),
        'recorded_pass':sum(r['recorded_status']=='PASS' for r in rows),'close_before_response':sum(r['physical_minus_response_ms']<0 for r in rows)},
      'runtime':'NOT RUN','body_close_invocation':'NOT PROVEN','historical_statuses_unchanged':True}
    (OWN/'w2-actual-row-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    results['preservation']={'uncertainty_verdict':'byte-identical','telemetry_verdict':'byte-identical','uncertainty_load_and_main_runner':'byte-identical',
      'mock_client_wire_plan_adapter_and_all_other_runtime_inputs':'unchanged pinned inputs','fixture_policy_sha256':ledger['fixture_policy_sha256'],
      'production_source':'untouched','delta_modules':list(MODULES),'actual_e2e':'NOT RUN'}
    results['delta_sha256']=ledger['delta_sha256'];results['node']=subprocess.check_output(['node','--version'],text=True).strip()
    (OWN/'w2-verification.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({'old':results['old'],'new':results['new'],'delta_sha256':ledger['delta_sha256'],'actual_e2e':'NOT RUN'}))
if __name__=='__main__':main()
