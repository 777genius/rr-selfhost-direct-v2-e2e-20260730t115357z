import json,subprocess,pathlib,tarfile,time,os
b=pathlib.Path("/srv/workers/jobs/review-router-gateway-spike/poc-20260930/sub2-operator")
assert pathlib.Path("/etc/machine-id").read_text().strip()=="d856d40da5ad4e23b4f67773e5942842"
keys=[pathlib.Path("/etc/subscription-runtime/secrets/review-router/"+n).read_bytes().strip() for n in ["mimo-token-plan-api-key","openrouter-e2e-api-key"]];assert all(len(k)>12 for k in keys)
started=time.time();rows=[]
def scan(f):
 tail=b"";hits=0;size=0
 while True:
  block=f.read(1048576)
  if not block:break
  data=tail+block;hits+=sum(data.count(k) for k in keys);size+=len(block);tail=data[-max(map(len,keys))+1:]
 return hits,size
for i in range(1,5):
 name=f"rr-sub2-spike-20260930-runner-{i}";proc=subprocess.Popen(["docker","export",name],stdout=subprocess.PIPE);files=hits=size=0
 with tarfile.open(fileobj=proc.stdout,mode="r|") as t:
  for m in t:
   if m.isfile():
    f=t.extractfile(m);h,n=scan(f);hits+=h;size+=n;files+=1
 assert proc.wait()==0
 inspect=subprocess.check_output(["docker","inspect",name]);logs=subprocess.check_output(["docker","logs",name],stderr=subprocess.STDOUT)
 hits+=sum(inspect.count(k)+logs.count(k) for k in keys)
 for p in (b/f"runner-work-{i}").rglob("*"):
  if p.is_file() and not p.is_symlink():
   with p.open("rb") as f:h,n=scan(f)
   hits+=h;size+=n;files+=1
 rows.append({"runner":i,"files":files,"bytes":size,"provider_master_hits":hits,"config_env_logs_scanned":True})
private=hits=size=0
for root in [b/"ci-private",b.parent/"sub2-transfer"]:
 for p in root.rglob("*"):
  if p.is_file() and not p.is_symlink() and p.suffix in [".jsonl",".txt",".log",".json"]:
   with p.open("rb") as f:h,n=scan(f)
   hits+=h;size+=n;private+=1
# No raw exports, credential files or engine logs are promoted into public evidence.
receipt={"id":"D01","status":"PASS" if not hits and all(r["provider_master_hits"]==0 for r in rows) else "FAIL","evidence_kind":"live-container","runner_filesystem_exports":rows,"private_capture_and_actions_log_files":private,"capture_bytes":size,"capture_provider_master_hits":hits,"provider_master_values_or_hashes_output":False,"duration_s":round(time.time()-started,2),"limits":["Snapshots after terminal run, not a continuous process-memory dump.","Successful client temp home intentionally deleted; Docker config/logs/full residual filesystem and mounted work remain scanned.","This does not claim absence of run-scoped capability/OIDC tokens or engine-side secrets."]}
(b/"receipts/runner-custody.json").write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
