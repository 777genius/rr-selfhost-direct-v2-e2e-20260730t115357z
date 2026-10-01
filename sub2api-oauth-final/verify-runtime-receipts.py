#!/usr/bin/env python3
"""Validate actual controller Go JSONL receipts; never executes services or models."""
import argparse, hashlib, json, sys
from pathlib import Path
OUT = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def require(condition, message):
    if not condition:
        raise ValueError(message)
def load(path):
    return json.loads(path.read_text())
def logs(paths):
    terminal, receipts, observations = {}, {}, {}
    pending = {}
    for path in paths:
        for line in path.read_text().splitlines():
            event = json.loads(line)
            require(isinstance(event, dict), 'Go JSONL event must be an object')
            action, test = event.get('Action'), event.get('Test')
            if action in ('pass', 'fail', 'skip') and test:
                require(test not in terminal, 'duplicate terminal test event: '+test)
                terminal[test] = action
            require(action != 'skip', 'skipped test/package: '+str(test))
            if action == 'fail' and not test:
                terminal['package:'+event.get('Package','unknown')] = 'fail'
            stream = (event.get('Package'),test)
            output = pending.pop(stream,'') + event.get('Output','')
            for fragment in output.splitlines(keepends=True):
                if not fragment.endswith('\n'):
                    pending[stream] = fragment
                    continue
                for prefix, records in [('OAUTH_LAB_RECEIPT ',receipts),('OAUTH_FORK_W9_OBSERVATION ',observations)]:
                    if prefix in fragment:
                        record = json.loads(fragment.split(prefix,1)[1].strip())
                        name = record['case_id']
                        require(name not in records, 'duplicate receipt/observation: '+name)
                        records[name] = record
    require(not any('OAUTH_LAB_RECEIPT ' in fragment or 'OAUTH_FORK_W9_OBSERVATION ' in fragment for fragment in pending.values()), 'truncated actual receipt/observation output')
    return terminal, receipts, observations

def bindings(meta, paths, manifest, red, reuse_w9=False):
    require(meta.get('schema') == 'oauth-fork-w9-controller-runtime/v1', 'missing controller runtime provenance schema')
    require(bool(meta.get('controller_execution_id')), 'controller execution ID required')
    require(meta.get('exit') == (1 if red else 0), 'wrong process exit for RED/GREEN')
    require(meta.get('compile_failed') is False, 'compile failure/unknown is not regression proof')
    require(meta.get('jsonl_sha256') == [sha(p) for p in paths], 'raw JSONL hashes do not match controller receipt')
    if red:
        expected = manifest['w8_patches']
        backend = manifest['red_backend']
    elif reuse_w9:
        expected = manifest['old_w9_patches']
        backend = manifest['old_w9_backend']
        # This is retained repo/service evidence only. Current admin gates below
        # must independently bind the final source and the one-line microdelta.
        require(manifest['microdelta']['path'] == 'backend/internal/handler/admin/openai_oauth_handler.go', 'unexpected reuse delta path')
        require(manifest['microdelta']['added_lines'] == 0 and manifest['microdelta']['removed_lines'] == 1, 'unexpected reuse delta size')
        require(manifest['microdelta']['other_production_paths_unchanged'] == 40 and manifest['microdelta']['all_test_paths_unchanged'] == 12, 'unchanged source scope not established')
    else:
        expected = {'source.patch': manifest['patches']['fullsource.patch'], 'tests-overlay.patch': manifest['patches']['tests-overlay.patch']}
        backend = manifest['candidate_backend']
    require(meta.get('source_patch_sha256') == expected['source.patch'], 'wrong source patch; historical W8/W9 is not current GREEN')
    require(meta.get('tests_overlay_sha256') == expected['tests-overlay.patch'], 'wrong full overlay hash')
    require(meta.get('new_test_patch_sha256') == manifest['red_tests']['sha256'], 'wrong identical RED/GREEN new fixture')
    require(meta.get('backend_sha256') == backend['sha256'], 'wrong complete source fingerprint')


def current_gate(meta, path, manifest, kind):
    require(meta.get('schema') == 'oauth-final-controller-gate/v1', 'missing current gate provenance')
    require(meta.get('kind') == kind and bool(meta.get('controller_execution_id')), 'wrong/missing gate identity')
    require(meta.get('exit') == 0 and meta.get('compile_failed') is False, 'current gate failed or unknown')
    require(meta.get('go_version') == 'go1.27.1', 'current Go toolchain missing/wrong')
    require(meta.get('jsonl_sha256') == sha(path), 'current gate log hash mismatch')
    require(meta.get('source_patch_sha256') == manifest['patches']['fullsource.patch'], 'current gate requires final production patch')
    require(meta.get('tests_overlay_sha256') == manifest['patches']['tests-overlay.patch'], 'current gate overlay mismatch')
    require(meta.get('labtests_patch_sha256') == manifest['patches']['labtests.patch'], 'current gate canonical patch mismatch')
    require(meta.get('backend_sha256') == manifest['candidate_backend']['sha256'], 'current gate complete final source mismatch')
    require(meta.get('microdelta_patch_sha256') == manifest['microdelta']['patch_sha256'], 'old-to-new delta binding missing')


def compile_gate(path):
    expected = {'github.com/Wei-Shaw/sub2api/internal/' + name for name in ['service','handler','handler/admin','repository']}
    packages = {}
    for line in path.read_text().splitlines():
        event = json.loads(line)
        require(isinstance(event,dict), 'compile JSONL event must be an object')
        require(event.get('Action') not in ['skip','fail'], 'compile gate FAIL/SKIP')
        require(not event.get('Test'), 'compile gate must use -run ^$')
        if event.get('Action') == 'pass':
            package = event.get('Package')
            require(package not in packages, 'duplicate compile package event')
            packages[package] = 'pass'
    require(set(packages) == expected, 'four-package compile PASS missing or extra package')


def receipt(record, status):
    require(record.get('status') == status, 'wrong actual fixture status: '+record['case_id'])
    require(record.get('synthetic_account_id',0) > 0 and bool(record.get('synthetic_identity_id')), 'missing actual synthetic row/identity')
    for key in ['owned_cleanup_ok','child_exits_ok','expected_child_terminations_ok']:
        require(record.get(key) is True, 'cleanup/termination evidence failed: '+key)
    require(record.get('go_version') == 'go1.27.1' and record.get('postgres_version') == '18.6' and record.get('redis_version') == '8.10.2', 'wrong/missing actual tool/service versions')

def concurrency(names, terminal, receipts, observations, red):
    for name in sorted(names):
        require(terminal.get(name) == ('fail' if red else 'pass'), 'missing/wrong terminal concurrency event: '+name)
        require(name in receipts and name in observations, 'missing actual concurrency receipt/observation: '+name)
        record, observation = receipts[name], observations[name]
        receipt(record, 'FAIL' if red else 'PASS')
        require(set(['admin_conversion_holds_row_lock_and_waits_on_owned_advisory_lock','actual_management_update_blocked_behind_admin_conversion']) <= set(record.get('barriers',[])), 'actual database blocking barriers absent')
        require(record.get('counts',{}).get('issuer_requests') == 0 and record.get('counts',{}).get('effective_rotations') == 0, 'unexpected issuer operation in management concurrency case')
        pids = [observation.get(key,0) for key in ['backend_a','backend_b','barrier_backend']]
        require(all(isinstance(pid,int) and pid > 0 for pid in pids) and len(set(pids)) == 3, 'three distinct actual PostgreSQL backends required')
        require(bool(observation.get('application_a')) and bool(observation.get('application_b')) and observation['application_a'] != observation['application_b'], 'distinct named management backends required')
        for key in ['observed_b_blocked_by_barrier','observed_a_update_blocked_by_b','sibling_schedulable']:
            require(observation.get(key) is True, 'missing actual lock/sibling observation: '+key)
        for key in ['a_rejected_or_zero_mutation','converted_document_unchanged','converted_revision_unchanged','converted_schedulable']:
            require(observation.get(key) is (not red), 'RED/GREEN durable outcome mismatch: '+key)
        require(observation.get('a_rows') == (1 if red else 0), 'unexpected actual mutation count')

def historical_main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--red-execution',type=Path,required=True)
    p.add_argument('--red-jsonl',type=Path,action='append',required=True)
    p.add_argument('--green-execution',type=Path,required=True)
    p.add_argument('--green-jsonl',type=Path,action='append',required=True)
    p.add_argument('--import-jsonl',type=Path,required=True)
    p.add_argument('--import-execution',type=Path,required=True)
    p.add_argument('--compile-jsonl',type=Path,required=True)
    p.add_argument('--compile-execution',type=Path,required=True)
    p.add_argument('--reuse-w9',action='store_true',help='reuse only exact old W9 repo/service logs; require final current admin/compile gates')
    args = p.parse_args()
    manifest, inventory = load(OUT/'source-manifest.json'), load(OUT/'case-inventory.json')
    red_meta, green_meta = load(args.red_execution), load(args.green_execution)
    bindings(red_meta,args.red_jsonl,manifest,True)
    bindings(green_meta,args.green_jsonl,manifest,False,args.reuse_w9)
    require(red_meta['controller_execution_id'] != green_meta['controller_execution_id'], 'RED/GREEN require distinct fresh execution identities')
    red_events, red_receipts, red_observations = logs(args.red_jsonl)
    green_events, green_receipts, green_observations = logs(args.green_jsonl)
    names = {r['case_id'] for r in inventory['cases']}
    races = {name for name in names if name.startswith('TestOAuthForkW9ManagementConversionConcurrency/')}
    require(len(races) == 16, 'exact16 concurrency cases required')
    require(set(red_receipts) == races and set(red_observations) == races, 'RED must cover exact16 races without unrelated fixture failures')
    concurrency(races,red_events,red_receipts,red_observations,True)
    require(all(green_events.get(name) == 'pass' for name in names), 'GREEN missing a terminal PASS for one or more of160 inventory identities')
    require(all(action == 'pass' for action in green_events.values()), 'GREEN contains FAIL/SKIP')
    for name in ['TestOAuthForkSchedulerMetadataProjection','TestOAuthForkManualValidationHTTP','TestOAuthForkWSReuseCredentialTuple','TestOAuthForkEmptyRefreshHTTPBoundary']:
        require(green_events.get(name) == 'pass', 'retained unit root missing: '+name)
    historical_receipts = set(load(OUT/'retained-actual-evidence.json')['historical_w8_receipt_ids'])
    new_cases = {name for name in names if name.startswith('TestOAuthForkW9')}
    require(len(historical_receipts) == 51 and len(new_cases) == 82, 'historical/new inventory counts changed')
    require(historical_receipts | new_cases <= set(green_receipts), 'GREEN missing retained or new fixture receipts')
    for record in green_receipts.values():
        receipt(record,'PASS')
        require(green_events.get(record['case_id']) == 'pass', 'fixture receipt lacks matching Go terminal PASS')
    require(set(green_observations) == races, 'GREEN requires exact16 actual concurrency observations')
    concurrency(races,green_events,green_receipts,green_observations,False)
    import_events, _, _ = logs([args.import_jsonl])
    require(import_events.get('TestOAuthForkW7ImportIdentityTypes') == 'pass' and all(action == 'pass' for action in import_events.values()), 'mandatory actual raw-import unit did not PASS')
    import_meta, compile_meta = load(args.import_execution), load(args.compile_execution)
    current_gate(import_meta,args.import_jsonl,manifest,'admin-raw-import')
    current_gate(compile_meta,args.compile_jsonl,manifest,'four-package-compile')
    compile_gate(args.compile_jsonl)
    admin_package = 'github.com/Wei-Shaw/sub2api/internal/handler/admin'
    import_package_passes = 0
    for line in args.import_jsonl.read_text().splitlines():
        event = json.loads(line)
        require(event.get('Package') == admin_package, 'raw-import log contains wrong package')
        if event.get('Action') == 'pass' and not event.get('Test'):
            import_package_passes += 1
    require(import_package_passes == 1, 'raw-import package terminal PASS missing/duplicate')
    if args.reuse_w9:
        permitted = {'github.com/Wei-Shaw/sub2api/internal/repository','github.com/Wei-Shaw/sub2api/internal/service'}
        for path in args.green_jsonl:
            for line in path.read_text().splitlines():
                require(json.loads(line).get('Package') in permitted, 'retained W9 reuse is limited to unchanged repo/service packages')
    else:
        require(green_meta.get('import_jsonl_sha256') == sha(args.import_jsonl), 'raw-import JSONL not bound to current GREEN receipt')
    print(json.dumps({'schema':'oauth-final-runtime-receipt-gate/v1','result':'PASS','actual_RED_cases':16,'actual_GREEN_inventory':len(names),'actual_GREEN_fixture_receipts':len(green_receipts),'actual_import':'PASS','actual_four_package_compile':'PASS','GREEN_evidence_scope':'retained exact W9 repo/service plus current final admin gates' if args.reuse_w9 else 'current final full execution','source_sha256':manifest['patches']['fullsource.patch'],'overlay_sha256':manifest['patches']['tests-overlay.patch'],'live_OAuth_upgrade':'NOT RUN','production_GO':False},indent=2))

# Actual producer schema extension. Retained functions above preserve the old
# historical checks. All current checks consume supplied process/raw data.
def actual_logs(path):
    terminal, packages = {}, {}
    records = {key:{} for key in ['receipts','observations','effects','old_observations']}
    prefixes = {'OAUTH_LAB_RECEIPT ':'receipts','OAUTH_BULK_RACE_OBSERVATION ':'observations','OAUTH_BULK_EFFECTS ':'effects','OAUTH_FORK_W9_OBSERVATION ':'old_observations'}
    pending = {}
    for line in path.read_text().splitlines():
        e = json.loads(line)
        require(isinstance(e,dict), 'JSONL event must be an object')
        action, name, package = e.get('Action'), e.get('Test'), e.get('Package')
        require(action != 'skip', 'actual suite contains SKIP')
        if action in ['pass','fail']:
            target,key = (terminal,name) if name else (packages,package)
            require(key and key not in target, 'duplicate/missing terminal identity')
            target[key] = action
        stream = (package,name)
        output = pending.pop(stream,'') + e.get('Output','')
        for fragment in output.splitlines(keepends=True):
            if not fragment.endswith('\n'):
                pending[stream] = fragment
                continue
            for prefix,kind in prefixes.items():
                if prefix in fragment:
                    r = json.loads(fragment.split(prefix,1)[1].strip())
                    require(isinstance(r,dict) and r.get('case_id') == name, 'record/test identity mismatch')
                    require(name not in records[kind], 'duplicate actual '+kind)
                    records[kind][name] = r
    require(not any(prefix in fragment for fragment in pending.values() for prefix in prefixes), 'truncated actual record')
    return terminal,packages,records


def actual_suite(evidence,suite,binding):
    meta = load(evidence/(suite+'-receipt.json'))
    cases = load(evidence/(suite+'-case-receipts.json'))
    for filename in [suite+'.jsonl',suite+'-receipt.json',suite+'-case-receipts.json']:
        require(sha(evidence/filename) == binding['raw_artifact_sha256']['evidence/'+filename], 'supplied actual artifact changed: '+filename)
    require(meta.get('kind') == 'actual-Go1271-final-OAuth-bulk' and meta.get('suite') == suite, 'wrong actual process schema/suite')
    require(meta.get('image') == binding['go_image'], 'actual immutable Go image mismatch')
    require(meta.get('exit') == (1 if suite=='mixed-red' else 0) and meta.get('compile_failed') is False, 'actual exit/compile gate failed')
    require(meta.get('bulk_patch_sha256') == binding['bulk_patch_sha256'] and meta.get('admin_fix_sha256') == binding['admin_fix_sha256'], 'actual executed patch provenance mismatch')
    require(meta.get('provider_requests') == 0, 'unexpected provider activity')
    terminal,packages,records = actual_logs(evidence/(suite+'.jsonl'))
    require(not meta.get('skipped_tests'), 'process reports SKIP')
    for field,status in [('passed_tests','pass'),('failed_tests','fail')]:
        require(len(meta[field])==len(set(meta[field])) and set(meta[field]) == {n for n,v in terminal.items() if v==status}, 'process/raw terminal identity mismatch')
    require(packages and all(v == ('fail' if suite=='mixed-red' else 'pass') for v in packages.values()), 'missing/wrong package terminal')
    for kind in ['receipts','observations','effects']:
        require(len(cases[kind])==len({r['case_id'] for r in cases[kind]}), 'duplicate producer case identity')
        projected={r['case_id']:r for r in cases[kind]}
        extra=set(binding['raw_fragment_reassembled_additional_receipt_ids']) if suite=='full-green' and kind=='receipts' else set()
        require(set(records[kind])==set(projected)|extra and all(records[kind][n]==r for n,r in projected.items()), 'raw/producer case records mismatch: '+kind)
        require(meta[kind]==len(projected), 'process/projected record count mismatch')
    return terminal,packages,records


def actual_races(names,data,red):
    terminals,_,records=data
    require(set(records['observations'])==names, 'mixed actual observation identity set mismatch')
    for name in sorted(names):
        r,o,e=(records[k][name] for k in ['receipts','observations','effects'])
        require(terminals.get(name)==('fail' if red else 'pass'), 'mixed terminal mismatch')
        receipt(r,'FAIL' if red else 'PASS')
        require({'admin_conversion_holds_row_lock_and_waits_on_owned_advisory_lock','actual_management_update_blocked_behind_admin_conversion'} <= set(r['barriers']), 'real PostgreSQL barriers missing')
        require(r['counts']['issuer_requests']==0 and r['counts']['effective_rotations']==0, 'mixed race contacted issuer')
        pids=[o[k] for k in ['backend_a','backend_b','barrier_backend']]
        require(all(type(pid) is int and pid>0 for pid in pids) and len(set(pids))==3, 'three actual PostgreSQL backend IDs required')
        require(o['application_a'] and o['application_b'] and o['application_a']!=o['application_b'], 'distinct named PostgreSQL backends required')
        for key in ['observed_b_blocked_by_barrier','observed_a_update_blocked_by_b','a_exactly_one_actual_native_update','converted_document_unchanged','converted_revision_unchanged','converted_schedulable','sibling_schedulable']:
            require(o[key] is True, 'actual durable-state violation: '+key)
        require(o['a_rows']==1, 'actual mixed row count must be one in RED and GREEN')
        excluded=r['synthetic_account_id'];bulk,cache=e['bulk_event_ids'],e['cache_effect_ids']
        require(e['b_own_account_changed_events']==2 and e['cache_after_commit'] is True, 'admin/commit effects violated')
        require(e['cache_boundary']=='repository SetAccount observer; no Redis writes', 'unsupported real Redis effects claim')
        if red:
            require(len(bulk)==1 and excluded in bulk[0] and excluded in cache and len(bulk[0])==4 and len(set(bulk[0]))==2 and len(cache)==2, 'RED excluded/duplicate ID propagation not proved')
        else:
            require(len(bulk)==1 and len(bulk[0])==1 and cache==bulk[0] and excluded not in cache and type(cache[0]) is int and cache[0]>0, 'GREEN includes excluded/duplicate effect IDs')


def validate_actual(evidence,source):
    binding,manifest=load(OUT/'actual-bindings.json'),load(OUT/'source-manifest.json')
    import prepare
    tree={p:b for p,b in source.items() if p.startswith('backend/')}
    require({p:prepare.digest(b) for p,b in tree.items()}==load(OUT/'executed-source-hashes.json'), 'complete actual source ledger mismatch')
    require(len(tree)==3158 and prepare.fingerprint(tree)==binding['executed_backend_sha256']==manifest['candidate_backend']['sha256'], 'actual source fingerprint mismatch')
    fixture='backend/internal/repository/oauth_bulk_affected_ids_test.go'
    require(prepare.digest(tree[fixture])==binding['regression_source_sha256'], 'actual regression bytes mismatch')
    require(sha(OUT/'bulk-regression.patch')==binding['identical_red_green_regression_patch_sha256'], 'identical RED/GREEN regression patch mismatch')
    reconstructed={};prepare.apply_exact(reconstructed,OUT/'bulk-regression.patch')
    require(reconstructed=={fixture:tree[fixture]}, 'regression patch differs from executed test bytes')
    require(sha(OUT/'w9-to-bulk.patch')==binding['bulk_patch_sha256'] and sha(OUT/'w9-to-final.patch')==binding['admin_fix_sha256'], 'actual patch binding mismatch')
    data={s:actual_suite(evidence,s,binding) for s in ['mixed-red','full-green','unit-bulk','compile','import-unit']}
    old=set(binding['old_193_terminal_ids']);additional=set(load(OUT/'bulk-case-inventory.json')['new_15_leaf_case_ids'])
    mixed={n for n in additional if n.startswith('TestOAuthBulkAffectedIDsConversionConcurrency/')}
    controls={n for n in additional if n.startswith('TestOAuthBulkAffectedIDsControls/')}
    cursor={n for n in additional if n.startswith('TestOAuthBulkReturningCursorFailures/')}
    require(len(old)==193 and len(additional)==15 and len(mixed)==8 and len(controls)==3 and len(cursor)==4, 'old/new identity inventory mismatch')
    roots={n.split('/')[0] for n in additional};green,_,records=data['full-green']
    require(set(green)==old|additional|roots and all(v=='pass' for v in green.values()), 'current GREEN exact211 identities mismatch')
    inventory={r['case_id'] for r in load(OUT/'case-inventory.json')['cases']}
    require(len(inventory)==160 and inventory<=set(green), 'retained160 identities missing')
    expected=set(binding['old_133_receipt_ids'])|mixed|controls
    extra=set(binding['raw_fragment_reassembled_additional_receipt_ids'])
    require(len(expected)==144 and len(extra)==27 and not expected & extra and set(records['receipts'])==expected|extra, 'current projected144/reassembled171 receipt identities mismatch')
    for name,r in records['receipts'].items():
        if name in extra:
            require(r['status']=='PASS' and r['owned_cleanup_ok'] is True and r['expected_child_terminations_ok'] is True, 'reassembled receipt status/cleanup mismatch')
            if r['child_exits_ok'] is not True:
                killed={e['pid'] for e in r['events'] if e.get('kind')=='owner_killed_after_consumption'}
                require(killed and killed<=set(r['child_pids']), 'unexplained abnormal child exit')
        else:receipt(r,'PASS')
        require(green[name]=='pass', 'receipt lacks terminal PASS')
    old_races={n for n in inventory if n.startswith('TestOAuthForkW9ManagementConversionConcurrency/')}
    require(len(old_races)==16 and set(records['old_observations'])==old_races, 'current W9 real16 observations missing')
    concurrency(old_races,green,records['receipts'],records['old_observations'],False)
    red,_,rr=data['mixed-red']
    require(set(red)==mixed|{'TestOAuthBulkAffectedIDsConversionConcurrency'} and all(v=='fail' for v in red.values()), 'actual RED requires eight leaves plus parent FAIL and zero PASS/SKIP')
    require(set(rr['receipts'])==set(rr['effects'])==mixed and set(records['effects'])==mixed|controls, 'actual RED/GREEN effect identity mismatch')
    actual_races(mixed,data['mixed-red'],True);actual_races(mixed,data['full-green'],False)
    for name in controls:
        e=records['effects'][name];r=records['receipts'][name]
        require(e['b_own_account_changed_events']==0 and e['cache_after_commit'] is True and e['cache_boundary']=='repository SetAccount observer; no Redis writes', 'control commit/cache boundary mismatch')
        bulk,cache=e['bulk_event_ids'],e['cache_effect_ids'];native=r['synthetic_account_id']
        if name.endswith('/zero'):require(bulk in (None,[]) and cache in (None,[]), 'zero update published effects')
        elif name.endswith('/mixed_missing'):require(bulk==[[native]] and cache==[native], 'nonexistent/native exact IDs mismatch')
        else:require(len(bulk)==1 and len(bulk[0])==2 and len(set(bulk[0]))==2 and bulk[0][-1]==native and sorted(cache)==sorted(bulk[0]), 'all-native reversed order/dedup effect IDs mismatch')
    units=data['unit-bulk'][0]
    require(len(units)==49 and all(v=='pass' for v in units.values()) and cursor<=set(units), 'actual49 units/four cursor failures did not PASS')
    require(not data['compile'][0], 'compile gate unexpectedly executes tests');compile_gate(evidence/'compile.jsonl')
    imports,packages,_=data['import-unit']
    require(imports=={'TestOAuthForkW7ImportIdentityTypes':'pass'} and packages=={'github.com/Wei-Shaw/sub2api/internal/handler/admin':'pass'}, 'actual raw import PASS missing')
    return {'result':'PASS','actual_RED_mixed_leaves':8,'actual_RED_pass':0,'actual_RED_skip':0,'actual_GREEN_terminals':len(green),'actual_GREEN_producer_receipts':len(expected),'actual_GREEN_reassembled_raw_receipts':len(records['receipts']),'additional_fragmented_receipts':len(extra),'actual_bulk_observations':len(records['observations']),'actual_W9_observations':len(records['old_observations']),'actual_bulk_effects':len(records['effects']),'actual_units':len(units),'actual_compile_packages':4,'actual_admin_raw_import':1,'backend_sha256':binding['executed_backend_sha256'],'go_image':binding['go_image'],'go_binary_checksum':'NOT SUPPLIED','Redis_scheduler_effects':'repository observer only; no Redis writes','critical_independent_review':'W7 PENDING','live_OAuth_upgrade':'NOT RUN','populated_history_migration243':'NO-GO; refusal retained','production_GO':False}


def main():
    parser=argparse.ArgumentParser(description='Verify actual supplied RED/GREEN against complete actual source')
    parser.add_argument('--evidence',type=Path,default=OUT/'evidence');parser.add_argument('--source',type=Path)
    parser.add_argument('--upstream',type=Path);parser.add_argument('--gofmt',type=Path)
    args=parser.parse_args()
    import prepare
    if args.source:
        require(args.upstream is None and args.gofmt is None, 'choose actual source or upstream/gofmt')
        source=prepare.read_tree(args.source)
    else:
        require(args.upstream is not None and args.gofmt is not None, 'upstream and gofmt required')
        source,_=prepare.prepare(args.upstream,args.gofmt)
    print(json.dumps(validate_actual(args.evidence,source),indent=2))

if __name__ == '__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
        print(json.dumps({'result':'FAIL','acceptance':'UNPROVEN','reason':str(error)}),file=sys.stderr);sys.exit(1)
