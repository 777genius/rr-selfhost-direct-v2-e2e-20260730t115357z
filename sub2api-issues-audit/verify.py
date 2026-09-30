#!/usr/bin/env python3
"""CLI-boundary verification; regressions documented before tests in VERIFY-REGRESSIONS.md."""
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE=pathlib.Path(__file__).resolve().parent
INPUTS=HERE.parent/'.spike-inputs'
OUTPUTS=('findings.json','AUDIT.md','dashboard.json')


def read(p):
    return json.loads(p.read_text())


def parse(s):
    return dt.datetime.fromisoformat(s.replace('Z','+00:00'))


def run(inputs,out):
    return subprocess.run([sys.executable,str(HERE/'analyze.py'),'--inputs',str(inputs),'--output',str(out)],
                          capture_output=True,text=True,timeout=30,cwd=HERE)


def main():
    started=time.monotonic(); checks=[]
    issues=read(INPUTS/'issues.json'); f=read(HERE/'findings.json')
    reference=parse(f['dataset']['analysis_reference_utc'])
    # 1: independent real census, no import from analyze.py.
    assert len(issues)==3935 and len({i['number'] for i in issues})==3935
    assert collections.Counter(i['state'] for i in issues)=={'open':2600,'closed':1335}
    assert f['census']['states']==dict(collections.Counter(i['state'] for i in issues))
    assert f['census']['unique_authors']==len({i['author'] for i in issues if i['author']})
    assert f['census']['without_labels']==sum(not i['labels'] for i in issues)==3921
    for days in (30,90):
        w=f['census']['windows'][str(days)]; earliest=reference-dt.timedelta(days=days)
        assert w['opened']==sum(earliest<=parse(i['created_at'])<=reference for i in issues)
        assert w['closed']==sum(bool(i['closed_at']) and earliest<=parse(i['closed_at'])<=reference for i in issues)
    names=('0–7','8–30','31–90','91–180','181+')
    for state,total in [('open',2600),('closed',1335)]:
        tally=collections.Counter()
        for i in issues:
            if i['state']!=state:continue
            elapsed=(reference-parse(i['created_at'])).total_seconds()
            idx=sum(elapsed >= bound*86400 for bound in (8,31,91,181))
            tally[names[idx]]+=1
        got=f['census'][state+'_age_since_creation_days']
        assert sum(got.values())==total and got==dict(tally)
    tally=collections.Counter()
    for i in issues:
        if i['state']=='closed':
            elapsed=(parse(i['closed_at'])-parse(i['created_at'])).total_seconds()
            tally[names[sum(elapsed>=bound*86400 for bound in (8,31,91,181))]]+=1
    assert f['census']['closed_duration_days']==dict(tally)
    versions=collections.Counter()
    import re
    for i in issues:
        found=set(re.findall(r'(?<![\d.])v?(0\.[12]\.\d{1,3})(?![\d.])',(i['title'] or '')+'\n'+(i['body'] or '')))
        versions.update('v'+v for v in found)
    assert dict(versions)==f['version_mentions']['counts']
    checks.append({'id':'independent_full_census','status':'PASS','records':3935,'windows_days':[30,90]})
    # 2: exact citations and hashes, including actual staged comments.
    byn={i['number']:i for i in issues}; cs=read(INPUTS/'comments.json')['issues']
    cbyn={e['number']:e['comments'] for e in cs}
    assert len(cbyn)>=48 and sum(len(v) for v in cbyn.values())>=66
    for r in f['reviewed_issues']:
        i=byn[r['number']]
        assert r['url']==i['html_url'] and r['state_reason']==i['state_reason']
        if r['number'] in cbyn:
            assert len(cbyn[r['number']])>=i['comments']
        real={c['id']:c for c in cbyn.get(r['number'],[])}
        for c in r['cited_comments']:
            assert c['url']==real[c['id']]['html_url']
    for s in f['source_findings']:
        path=INPUTS/'upstream'/s['path']
        assert s['available'] and s['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
        assert 1<=s['line']<=len(path.read_text().splitlines())
    checks.append({'id':'citations_and_fingerprints','status':'PASS','reviewed_issues':len(f['reviewed_issues']),'staged_comments':sum(len(v) for v in cbyn.values()),'source_files':len(f['source_findings']),
                   'limitation':'Snapshot count agreement; no independent pagination/commit authentication.'})
    # 3: actual CLI deterministic outputs, run from a different cwd.
    with tempfile.TemporaryDirectory(prefix='verify-',dir=HERE) as td:
        scratch=pathlib.Path(td); a=scratch/'a'; b=scratch/'b'
        for output in (a,b):
            result=run(INPUTS,output)
            assert result.returncode==0, result.stderr
        for name in OUTPUTS:
            assert (a/name).read_bytes()==(b/name).read_bytes()==(HERE/name).read_bytes()
        checks.append({'id':'real_corpus_cli_determinism','status':'PASS','runs':2})
        # 4: hostile public text must not enter any report; not an engine/mock test.
        evil=scratch/'inputs';evil.mkdir()
        synthetic_key='sk-SYNTHETIC_AUDIT_CANARY_78196342'
        hostile='<script>alert("AUDIT_HTML_CANARY_78196342")</script>'
        modified=json.loads(json.dumps(issues))
        for i in modified:
            i['title']+=' '+hostile+' '+synthetic_key
            i['body']=(i['body'] or '')+'\n'+hostile+' '+synthetic_key
            i['author']=synthetic_key
            if i['labels']:i['labels']=[{'name':synthetic_key}]
        (evil/'issues.json').write_text(json.dumps(modified))
        releases=read(INPUTS/'releases.json')
        for r in releases:r['body']=(r['body'] or '')+' '+hostile+' '+synthetic_key
        (evil/'releases.json').write_text(json.dumps(releases))
        comments=read(INPUTS/'comments.json')
        for e in comments['issues']:
            for c in e['comments']:c['body']=hostile+' '+synthetic_key;c['author']=synthetic_key
        (evil/'comments.json').write_text(json.dumps(comments))
        (evil/'upstream').symlink_to(INPUTS/'upstream',target_is_directory=True)
        out=scratch/'hostile';result=run(evil,out)
        assert result.returncode==0,result.stderr
        for path in out.iterdir():
            text=path.read_text()
            assert synthetic_key not in text and hostile not in text and 'AUDIT_HTML_CANARY_78196342' not in text
            assert '<script' not in text.lower() and '</script' not in text.lower()
        checks.append({'id':'hostile_corpus_cli_no_public_payload_export','status':'PASS','records_mutated':3935,
                       'surfaces':['title','body','author','label','release body','comment body/author']})
        # 5: corrupt dataset must be rejected before files are emitted.
        for cause in ('duplicate_number','pr_marker','unsafe_url'):
            bad=json.loads(json.dumps(issues))
            if cause=='duplicate_number':bad[1]['number']=bad[0]['number']
            elif cause=='pr_marker':bad[0]['pull_request']={'url':'synthetic.invalid'}
            else:bad[0]['html_url']='javascript:alert(1)'
            (evil/'issues.json').write_text(json.dumps(bad))
            bad_out=scratch/cause;result=run(evil,bad_out)
            assert result.returncode!=0 and (not bad_out.exists() or not list(bad_out.iterdir()))
        checks.append({'id':'invalid_full_census_fails_before_publication','status':'PASS','cases':3})
        # 7: actual source bytes may not drift underneath authored conclusions.
        (evil/'issues.json').write_text(json.dumps(issues))
        (evil/'comments.json').write_bytes((INPUTS/'comments.json').read_bytes())
        (evil/'releases.json').write_bytes((INPUTS/'releases.json').read_bytes())
        (evil/'upstream').unlink()
        (evil/'upstream').mkdir()
        for source in f['source_findings']:
            target=evil/'upstream'/source['path']
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(INPUTS/'upstream'/source['path'],target)
        drift_file=evil/'upstream/backend/internal/service/oauth_refresh_api.go'
        drift_file.write_text(drift_file.read_text()+'\n// synthetic evidence drift\n')
        drift_out=scratch/'source-drift';result=run(evil,drift_out)
        assert result.returncode!=0 and 'source bytes differ' in result.stderr
        assert not drift_out.exists() or not list(drift_out.iterdir())
        changed=read(out/'findings.json')
        assert changed['comments']['manual_interpretation_current'] is False
        assert all(not r['cited_comments'] for r in changed['reviewed_issues'])
        checks.append({'id':'authored_evidence_freshness','status':'PASS',
                       'source_drift_rejected_before_publication':True,
                       'changed_comment_conclusions_withheld':True,
                       'observed_before_fix':{'source_drift_exit_code':0,'reports_published':True}})

    # 6: no engine/live proof manufactured by output labels.
    assert len(f['reviewed_issues'])==52
    assert len({r['number'] for r in f['reviewed_issues']})==52
    assert all(r['independently_reproduced'] is False and r['maintainer_fix_confirmed'] is False for r in f['reviewed_issues'])
    assert any(r['assessment']=='off_project_support' for r in f['reviewed_issues'])
    dashboard=read(HERE/'dashboard.json')
    assert dashboard['live_e2e_status']=='NOT RUN by audit lane'
    assert len(dashboard['recommendations'])==3
    checks.append({'id':'bounded_claims_and_dashboard','status':'PASS','limitation':'No upstream tests/live security/E2E run by this verification.'})
    result={'status':'PASS','checks':checks,'duration_seconds':round(time.monotonic()-started,3),
            'python_version':sys.version.split()[0],'inputs':{n:hashlib.sha256((INPUTS/n).read_bytes()).hexdigest() for n in ('issues.json','releases.json','comments.json')},
            'output_sha256':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in OUTPUTS}}
    (HERE/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','checks':len(checks),'duration_seconds':result['duration_seconds']}))

if __name__=='__main__':main()
