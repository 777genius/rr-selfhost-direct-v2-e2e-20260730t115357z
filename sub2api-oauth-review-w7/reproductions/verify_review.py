#!/usr/bin/env python3
"""Offline independent audit: reads frozen inputs, writes only this review's evidence.
Does not execute supplied verifiers, Go, PostgreSQL, Redis, Git or network calls.
"""
from pathlib import Path
import collections, hashlib, json, re
ROOT=Path(__file__).resolve().parents[2]
INPUT=ROOT/'.spike-inputs'; OUT=ROOT/'sub2api-oauth-review-w7'
checks=[]
def need(ok,label):
    if not ok: raise AssertionError(label)
    checks.append(label)
def sha(b): return hashlib.sha256(b).hexdigest()
def read(p): return json.loads(p.read_text())
def fingerprint(tree): return sha(''.join(k+'\0'+sha(v)+'\n' for k,v in sorted(tree.items())).encode())
def patch(tree,path,reverse=False):
    ls=path.read_text().splitlines(keepends=True); i=0; summary=[]
    while i<len(ls):
        if not ls[i].startswith('--- '): i+=1; continue
        old=ls[i][4:].strip(); new=ls[i+1][4:].strip(); i+=2
        name=new.removeprefix('b/'); need(name.startswith('backend/') and '..' not in Path(name).parts,'confined patch path')
        source=tree.get(name,b'').decode().splitlines(keepends=True); result=[]; cursor=0; adds=dels=0
        while i<len(ls) and ls[i].startswith('@@ '):
            m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',ls[i]); i+=1
            need(bool(m),'valid hunk')
            a,ac,b,bc=int(m[1]),int(m[2] or 1),int(m[3]),int(m[4] or 1)
            start,count,end,newcount=(b,bc,a,ac) if reverse else (a,ac,b,bc)
            offset=start-1 if start else 0
            need(offset>=cursor,'ordered hunk'); result.extend(source[cursor:offset]); cursor=offset
            need(len(result)==(end-1 if end else 0),'exact new hunk offset')
            ro=rn=0
            while ro<count or rn<newcount:
                mark,content=ls[i][0],ls[i][1:]; i+=1
                adds+=mark=='+'; dels+=mark=='-'
                if reverse: mark={'+':'-','-':'+',' ':' '}[mark]
                if mark in ' -':
                    need(cursor<len(source) and source[cursor]==content,'byte exact patch context')
                    cursor+=1;ro+=1
                if mark in ' +': result.append(content);rn+=1
            need((ro,rn)==(count,newcount),'exact hunk counts')
        result.extend(source[cursor:])
        if reverse and old=='/dev/null':
            need(not result,'new file reverse empties');del tree[name]
        else: tree[name]=''.join(result).encode()
        summary.append({'path':name,'added_lines':adds,'removed_lines':dels})
    return summary
TAGS={'receipts':'OAUTH_LAB_RECEIPT ','observations':'OAUTH_BULK_RACE_OBSERVATION ','effects':'OAUTH_BULK_EFFECTS ','old_observations':'OAUTH_FORK_W9_OBSERVATION '}
def logs(name):
    es=[json.loads(x) for x in (INPUT/'actual-gates'/f'{name}.jsonl').read_text().splitlines()]
    terminals={};packages={}; streams=collections.defaultdict(str)
    for e in es:
        if e['Action'] in ('pass','fail','skip'):
            dest=terminals if e.get('Test') else packages; key=e.get('Test',e['Package'])
            need(key not in dest,'unique raw terminal '+name);dest[key]=e['Action']
        streams[(e['Package'],e.get('Test'))]+=e.get('Output','')
    records={k:{} for k in TAGS}; outputs=[]
    for stream,output in streams.items():
        outputs.extend(output.splitlines())
        for line in output.splitlines():
            for kind,tag in TAGS.items():
                if tag not in line:continue
                r=json.loads(line.split(tag,1)[1]); cid=r['case_id']
                need(cid not in records[kind],'unique structured identity '+name+' '+kind);records[kind][cid]=r
    meta=read(INPUT/'actual-gates'/f'{name}-receipt.json')
    need(meta['bulk_patch_sha256']==sha((INPUT/'bulk/w9-to-bulk.patch').read_bytes()) and meta['admin_fix_sha256']==sha((INPUT/'final-base/w9-to-final.patch').read_bytes()),'runtime patch bindings '+name)
    need(set(meta['passed_tests'])=={k for k,v in terminals.items() if v=='pass'},'summary PASS equals raw '+name)
    need(set(meta['failed_tests'])=={k for k,v in terminals.items() if v=='fail'},'summary FAIL equals raw '+name)
    need(not meta['compile_failed'] and not meta['skipped_tests'] and 'skip' not in terminals.values(),'no compile/skips '+name)
    public=read(INPUT/'actual-gates'/f'{name}-case-receipts.json')['receipts']
    need(len({r['case_id'] for r in public})==len(public)==meta['receipts'],'dedup public receipts '+name)
    need(all(records['receipts'].get(r['case_id'])==r for r in public),'public equals raw receipt '+name)
    for r in public:
        need(terminals[r['case_id']]==r['status'].lower(),'receipt terminal agrees '+name)
        need(all(r.get(k) is True for k in ['owned_cleanup_ok','child_exits_ok','expected_child_terminations_ok']),'cleanup/termination '+name)
        need((r['go_version'],r['postgres_version'],r['redis_version'])==('go1.27.1','18.6','8.10.2'),'actual versions '+name)
    need(len(records['observations'])==meta['observations'] and len(records['effects'])==meta['effects'],'structured counts '+name)
    return terminals,packages,records,outputs,public

def main():
    bindings=read(INPUT/'INPUT-HASHES.json')
    for name,h in bindings.items():
        p=INPUT/name;need(not p.is_symlink() and p.is_file() and sha(p.read_bytes())==h,'input binding '+name)
    tree={'backend/'+p.relative_to(INPUT/'executed-source/backend').as_posix():p.read_bytes() for p in (INPUT/'executed-source/backend').rglob('*') if p.is_file()}
    ledger=read(INPUT/'actual-gates/executed-source-hashes.json')
    need({k:sha(v) for k,v in tree.items()}==ledger,'complete executed source ledger')
    bulk=read(INPUT/'bulk/manifest.json'); final=read(INPUT/'final-base/source-manifest.json')
    without_admin=dict(tree); admin_delta=patch(without_admin,INPUT/'final-base/w9-to-final.patch',True)
    need(admin_delta==[{'path':'backend/internal/handler/admin/openai_oauth_handler.go','added_lines':0,'removed_lines':1}],'admin only unused import')
    need({k:sha(v) for k,v in without_admin.items()}=={r['path']:r['after_sha256'] for r in bulk['files']},'all bulk ledger bytes plus separate admin compose')
    need(fingerprint(without_admin)==bulk['after_backend_sha256'],'bulk fingerprint')
    composed=dict(without_admin);patch(composed,INPUT/'final-base/w9-to-final.patch')
    need(composed==tree,'forward admin composition exact executed source')
    old=dict(without_admin);delta=patch(old,INPUT/'bulk/w9-to-bulk.patch',True)
    need(len(old)==3156 and fingerprint(old)==bulk['before_backend_sha256']==final['old_w9_backend']['sha256'],'exact W9 reverse reconstruction')
    prod=[r for r in delta if not r['path'].endswith('_test.go')]
    need(prod==[{'path':'backend/internal/repository/account_repo.go','added_lines':29,'removed_lines':6}],'production plus29 minus6 only repository')
    k='backend/internal/repository/account_repo.go';newtext=tree[k].decode();oldtext=old[k].decode()
    start='func (r *accountRepository) BulkUpdate(';end='type accountGroupQueryOptions'
    need(newtext[newtext.index(start):newtext.index('query := \"UPDATE accounts SET',newtext.index(start))]==oldtext[oldtext.index(start):oldtext.index('query := \"UPDATE accounts SET',oldtext.index(start))],'all bulk preflight SET WHERE predicate bytes unchanged')
    need(newtext[:newtext.index(start)]==oldtext[:oldtext.index(start)] and newtext[newtext.index(end):]==oldtext[oldtext.index(end):],'production mutation confined BulkUpdate')
    prod_paths=[r['path'] for r in final['production_files']]
    unchanged=[k for k in prod_paths if k not in [prod[0]['path'],admin_delta[0]['path']]]
    need(len(prod_paths)==41 and len(unchanged)==39 and all(tree[k]==old[k] for k in unchanged),'39 other production files unchanged; 41 total historical production files')
    # Including the bulk-changed repository, 40 historical production paths are unchanged by the admin microdelta.
    need(sum(tree[k]==without_admin[k] for k in prod_paths)==40,'40 production paths unchanged by admin fix')
    w9='backend/internal/repository/oauth_fork_contract_w9_test.go'
    need(tree[w9]==old[w9],'original16 singleton W9 race fixture unchanged')
    for k,h in final['migrations'].items():need(sha(tree['backend/migrations/'+k])==h and tree['backend/migrations/'+k]==old['backend/migrations/'+k],'migration preserved '+k)
    for k in set(old)&set(tree):
        if k.endswith('_test.go'):
            assertions=lambda b:[l for l in b.decode().splitlines() if re.search(r'\b(?:require|assert)\.',l)]
            need(assertions(old[k])==assertions(tree[k]),'old unit assertions preserved '+k)
    suites={n:logs(n) for n in ['full-green','mixed-red','compile','import-unit','unit-bulk']}
    gt,gp,gr,gout,gpublic=suites['full-green'];rt,rp,rr,rout,rpublic=suites['mixed-red']
    need(len(gt)==211 and set(gt.values())=={'pass'} and len(gp)==2 and set(gp.values())=={'pass'},'211 GREEN terminals two successful packages')
    oldexec=read(INPUT/'w9-gates/execution.json');oldnames=set(oldexec['passed_tests'])
    need(len(oldnames)==193 and oldnames<=set(gt),'all193 old terminal identities retain PASS')
    inventory={r['case_id'] for r in read(INPUT/'final-base/case-inventory.json')['cases']}
    need(len(inventory)==160 and inventory<=set(gt),'all160 inventory identities PASS')
    oldreceipts=read(INPUT/'w9-gates/case-receipts.json');oldreceiptids={r['case_id'] for r in oldreceipts};greenids={r['case_id'] for r in gpublic}
    need(len(oldreceiptids)==133 and oldreceiptids<=greenids and len(greenids)==144,'all133 old receipt identities plus11 new')
    originalrace={k for k in gt if k.startswith('TestOAuthForkW9ManagementConversionConcurrency/')}
    need(len(originalrace)==16 and originalrace<=oldnames,'all16 old singleton races PASS')
    races={k for k in gt if k.startswith('TestOAuthBulkAffectedIDsConversionConcurrency/')}
    need(len(races)==8 and set(rt)==races|{'TestOAuthBulkAffectedIDsConversionConcurrency'} and set(rt.values())=={'fail'} and set(rp.values())=={'fail'},'RED exactly8 same fixture leaves plus parent fail')
    normalized=[]
    for color,rec in [('GREEN',gr),('RED',rr)]:
        need(set(rec['observations'])==races,'eight matched observations '+color)
        for cid,o in rec['observations'].items():
            need(len({o[k] for k in ['backend_a','backend_b','barrier_backend']})==3,'three distinct PG backends '+color)
            need(all(o[k] is True for k in ['observed_b_blocked_by_barrier','observed_a_update_blocked_by_b','a_exactly_one_actual_native_update','converted_document_unchanged','converted_revision_unchanged','converted_schedulable','sibling_schedulable']) and o['a_rows']==1,'both lock dependencies and durable preservation '+color)
            ef=rec['effects'][cid]; need(ef['b_own_account_changed_events']==2,'separate B trigger/admin events '+color)
            if color=='GREEN':need(len(ef['bulk_event_ids'])==1 and ef['bulk_event_ids'][0]==ef['cache_effect_ids'] and len(ef['cache_effect_ids'])==1 and ef['cache_after_commit'],'actual updated only cache/outbox GREEN')
            else:need(len(ef['bulk_event_ids'][0])==4 and len(set(ef['bulk_event_ids'][0]))==2 and len(ef['cache_effect_ids'])==2,'RED submitted duplicate/excluded target effects')
            receipt=rec['receipts'][cid]
            if color=='GREEN':need(receipt['synthetic_account_id'] not in ef['cache_effect_ids'] and receipt['synthetic_account_id'] not in ef['bulk_event_ids'][0],'converted ID absent from GREEN publication')
            else:need(receipt['synthetic_account_id'] in ef['cache_effect_ids'] and receipt['synthetic_account_id'] in ef['bulk_event_ids'][0],'converted ID present in RED publication')
            need(set(receipt['barriers']) >= {'admin_conversion_holds_row_lock_and_waits_on_owned_advisory_lock','actual_management_update_blocked_behind_admin_conversion'},'receipt barriers '+color)
            need(receipt['counts']['issuer_requests']==receipt['counts']['effective_rotations']==0,'zero race issuer consumption '+color)
            normalized.append({'run':color,'observation':o,'effects':ef})
    need(sum('bulk event IDs differ from actual updated rows/order' in l for l in rout)==8 and sum('immediate cache effect IDs differ from actual updated rows' in l for l in rout)==8,'RED sixteen exact propagation assertion failures')
    for mode in ['zero','all','mixed_missing']:
        ef=gr['effects']['TestOAuthBulkAffectedIDsControls/'+mode];need(ef['cache_after_commit'],'control commit '+mode)
        if mode=='zero':need(not ef['bulk_event_ids'] and not ef['cache_effect_ids'],'zero effect control')
        else:need(ef['bulk_event_ids'][0]==([gr['receipts']['TestOAuthBulkAffectedIDsControls/'+mode]['synthetic_account_id']+1,gr['receipts']['TestOAuthBulkAffectedIDsControls/'+mode]['synthetic_account_id']] if mode=='all' else [gr['receipts']['TestOAuthBulkAffectedIDsControls/'+mode]['synthetic_account_id']]),'exact requested native ordering '+mode)
        if mode!='zero':need(len(ef['bulk_event_ids'])==1 and sorted(ef['bulk_event_ids'][0])==ef['cache_effect_ids'] and len(ef['cache_effect_ids'])==(2 if mode=='all' else 1),'native control count/dedup '+mode)
    ct,cp,*_=suites['compile'];need(not ct and len(cp)==4 and set(cp.values())=={'pass'},'four package compile PASS')
    it,ip,*_=suites['import-unit'];need(it=={'TestOAuthForkW7ImportIdentityTypes':'pass'} and set(ip.values())=={'pass'},'actual raw admin import1 PASS')
    ut,up,*_=suites['unit-bulk'];need(len(ut)==49 and set(ut.values())=={'pass'} and set(up.values())=={'pass'},'bulk49 unit PASS')
    need(all(ut.get('TestOAuthBulkReturningCursorFailures/'+m)=='pass' for m in ['query','scan','iteration','close']),'query scan iteration close failure PASS')
    refs={}
    needles={
      'backend/internal/repository/account_repo.go':['func oauthIdentityWritePredicate','func (r *accountRepository) BulkUpdate',' RETURNING id','updatedRows.Scan','updatedRows.Err()','updatedRows.Close();','updatedIDs :=','"account_ids": updatedIDs','tx.Commit()','syncSchedulerAccountSnapshots(baseCtx, updatedIDs)'],
      'backend/internal/repository/oauth_bulk_affected_ids_test.go':['func (c *oauthBulkCacheObserver) SetAccount','func oauthBulkAssertEffects','oauthW9Blocked(t, f, pidB','oauthW9Blocked(t, f, pidA','after.Status == service.StatusActive','OAUTH_BULK_RACE_OBSERVATION'],
      'backend/internal/repository/oauth_bulk_sql_cursor_test.go':['func TestOAuthBulkReturningCursorFailures','mock.ExpectRollback()'],
      'backend/internal/repository/oauth_fork_contract_w9_test.go':['func oauthW9Blocked','pg_blocking_pids(pid)'],
      'backend/internal/handler/admin/account_codex_import.go':['func normalizeCodexImportEntry'],
      'backend/internal/service/openai_oauth_forward_binding.go':['func (s *OpenAIGatewayService) bindOAuthForward'],
      'backend/internal/repository/openai_oauth_durable.go':['func oauthNoPendingPredicate'],
    }
    for k,ns in needles.items():
        lines=tree[k].decode().splitlines();refs[k]={'sha256':sha(tree[k]),'anchors':{n:[i+1 for i,l in enumerate(lines) if n in l] for n in ns}}
    evidence={'schema':'oauth-independent-review-w7-evidence/v1','result':'PASS','input_hashes_verified':len(bindings),'checks':len(checks),'actual_backend_files':len(tree),'actual_backend_sha256':fingerprint(tree),'historical_w9_backend_sha256':fingerprint(old),'production_delta':prod,'admin_delta':admin_delta,'source_refs':refs,'green':{'test_terminals':211,'receipts':144,'mixed_observations':8,'effects':11,'retained_terminals':193,'retained_receipt_identities':133,'retained_inventory':160,'retained_singleton_races':16},'red':{'failed_leaves':8,'failed_parent':1,'receipts':8,'observations':8,'effects':8,'propagation_assertion_failures':16},'compile_packages':sorted(cp),'raw_admin_import':'PASS1','unit_bulk':'PASS49; four cursor fault boundaries','race_evidence':normalized,'current_terminal_identities':sorted(gt),'retained_receipt_identities':sorted(oldreceiptids),'new_terminal_identities':sorted(set(gt)-oldnames),'raw_green_structured_receipts':len(gr['receipts']),'raw_extra_records_not_counted_as_acceptance':len(gr['receipts'])-len(gpublic),'runtime_execution_by_reviewer':False,'cache_scope':'Immediate repository SetAccount observer after visible account/outbox commit; Redis implementation mutation not tested','limits':['Populated-history migration243 NO upgrade GO','Live OAuth NOT RUN deliberately; NO production GO','Source provenance supplied; no Git/network revalidation']}
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:evidence[k] for k in ['result','input_hashes_verified','checks','actual_backend_files','actual_backend_sha256','green','red','raw_admin_import','unit_bulk']},indent=2))
if __name__=='__main__':main()
