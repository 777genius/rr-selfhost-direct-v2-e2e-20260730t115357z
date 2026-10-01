#!/usr/bin/env python3
"""Revalidate completion against available bytes; do not promote public summaries."""
from pathlib import Path
import json,hashlib,re,math
R=Path(__file__).resolve().parent.parent
O=R/'sub2api-memory-final-audit'
I=R/'.spike-inputs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,d):(O/name).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
findings=json.loads((O/'findings.json').read_text())
manifest=json.loads((R/'sub2api-native-merged/merged-hashes.json').read_text())
source_references=[]
for p in sorted((I/'source/service').glob('*.go')):
 if p.name.endswith('_test.go'):continue
 for n,line in enumerate(p.read_text().splitlines(),1):
  if 'keyHealth' in line:source_references.append({'path':str(p.relative_to(R)),'line':n,'text':line.strip()})
assert all(x['path'].endswith('/content_moderation.go') for x in source_references)
assert not any('delete(' in x['text'] for x in source_references)
mod=(I/'source/service/content_moderation.go').read_text()
body_reads=[mod[:m.start()].count('\n')+1 for m in re.finditer(r'input\.Body',mod)]
assert body_reads==[921,964,972]
# Text top corroboration checks totals with exactly their displayed rounding precision.
tops={}
for protocol in ('responses','messages'):
 d=json.loads((I/f'{protocol}-analysis.json').read_text())
 for cp in (0,10):
  p=I/'pprof-top'/f'{protocol}-{cp:03d}.txt';t=p.read_text()
  match=re.search(r'100% of ([0-9.]+)(kB|MB) total',t)
  assert match
  displayed=float(match[1]);unit={'kB':1024,'MB':1048576}[match[2]]
  summary=d['checkpoints'][cp]['profiles_sampled_weighted']['heap']['inuse_space']
  assert abs(displayed*unit-summary)<=0.005*unit+1
  build=re.search(r'^Build ID: (.+)$',t,re.M)[1]
  assert build=='413566fd6e71ea2f3a464e9bcc8dc96d39738862'
  assert re.search(r'^Type: inuse_space$',t,re.M)
  tops[f'{protocol}-{cp:03d}']={'sha256':sha(p),'displayed_total':displayed,'displayed_unit':match[2],'exact_summary_total_bytes':summary,'rounding_consistent':True,'build_id_text':build,'build_sha256_custody':'UNVERIFIED'}
missing_batch='backend/internal/repository/usage_log_repo_insert.go'
requests={
 'schema':'memory-final-missing-evidence-v1',
 'source':[{'path':missing_batch,'expected_sha256':manifest[missing_batch],'needed_for':'Inspect actual best-effort queue and batch flush/reset/clearing ownership; header source is insufficient.'}],
 'diagnostic_runs':[{'protocol':p,'run_json_expected_sha256':findings['protocols'][p]['run_sha256_reference'],'needed_files':['run.json','profiles/runtime.ndjson','profiles/checkpoint-000.json','profiles/checkpoint-010.json','profiles/checkpoint-000-heap.pb.gz','profiles/checkpoint-010-heap.pb.gz','burst end/DONE boundaries and all checkpoint acknowledgements for checkpoints 001-010','original burst RSS/READY/DONE receipts','matched idle-control raw runtime/profile/RSS records'],'needed_for':'Authenticate natural-GC boundaries and decoded profile samples against the exact run; retain no-forced-GC semantics.'} for p in ('responses','messages')],
 'identity':['Full diagnostic binary SHA-256 beginning 798 plus exact build/source/overlay and matching runtime profiler source receipts. A text pprof Build ID is not binary custody.','Final native c656/5e exact original twenty functional/RSS rows with burst baseline and qualifying five-second endpoint observations.'],
 'constraints':'Supply read-only public artifacts only; no credentials, request bodies, provider calls, replacement runs, production modifications, forced GC or runtime tuning. No complete input-tree copy required.'}
write('missing-evidence.json',requests)
requirements=[
 {'id':'R1','requirement':'Pin current source to final production 16bc','state':'PROVEN_FOR_SUPPLIED_SOURCE_SCOPE','evidence':['source-verification.json','input-hash-ledger.json'],'limit':'1377 files, not every backend/build byte; omitted batch insertion is separately R4.'},
 {'id':'R2','requirement':'Use exact natural-GC profile data from the final-source diagnostic binary','state':'INCOMPLETE','evidence':tops,'limit':'Totals/type/text Build ID corroborate analyses. Raw binary profiles, acknowledgements, runtime NDJSON and complete build pins absent.'},
 {'id':'R3','requirement':'Distinguish current retained references from static/runtime/allocator effects without unqualified live attribution','state':'PROVEN_AS_QUALIFIED_SOURCE_AND_SUMMARY_ASSESSMENT','evidence':['findings.json#fixed_allocation','findings.json#findings','findings.json#protocols'],'limit':'Source reference risks are verified; no causal fraction or live sampled per-request ownership is claimed.'},
 {'id':'R4','requirement':'Independently audit actual usage batch implementation','state':'INCOMPLETE','missing_source':missing_batch,'expected_sha256':manifest[missing_batch],'limit':'Supplied header, worker pool and sampled top do not include insertion/batcher implementation.'},
 {'id':'R5','requirement':'Explain strict empirical RSS failure and practical stability implications','state':'PROVEN_CRITERION_AND_LIMITS;FINAL_ROWS_USER_REPORTED','evidence':['REPORT.md','input-hash-ledger.json entries sub2api-transport-r4/adapter.mjs'],'limit':'Exact final native twenty rows not present; diagnostics must not supersede that result. No plateau or universal leak verdict.'},
 {'id':'R6','requirement':'Respect read-only production scope and provide reviewable artifacts with full input hash references','state':'PROVEN_FOR_THIS_WORK','evidence':['input-hash-ledger.json','artifact-hashes.json'],'limit':'Only sub2api-memory-final-audit artifacts written; no Go/network/Docker/Git writes or subagents.'}
]
write('completion-audit.json',{'schema':'memory-final-completion-audit-v1','goal_complete':False,'goal_status':json.loads((O/'blocked-audit.json').read_text())['goal_status'] if (O/'blocked-audit.json').exists() else 'active','previous_goal_turn_classification':'progress','current_turn_progress':['Independently corroborated all four pprof text totals/type/Build ID against exact supplied analysis totals at displayed precision.','Exhaustively checked non-test service source references to moderation health state and pinned missing batch source hash.','Produced requirement-by-requirement completion audit and minimal read-only missing-evidence manifest.'], 'same_blocking_condition_observed_goal_turns':json.loads((O/'blocked-audit.json').read_text())['same_blocking_condition_observed_goal_turns'] if (O/'blocked-audit.json').exists() else 2,'blocking_condition':'Exact original diagnostic raw profiles/runtime/build custody and actual usage batch insertion bytes are unavailable in permitted current workspace.','required_evidence':requirements,'exhaustive_health_map_reference_evidence':source_references,'moderation_raw_body_read_lines':body_reads,'missing_evidence_manifest':'missing-evidence.json'})
print(json.dumps({'profile_text_corroborations':len(tops),'health_state_references':len(source_references),'body_read_lines':body_reads,'missing_batch_sha256':manifest[missing_batch],'goal_complete':False}))
