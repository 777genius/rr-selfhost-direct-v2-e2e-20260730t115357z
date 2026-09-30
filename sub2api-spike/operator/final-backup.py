import json,subprocess,pathlib,time,os
b=pathlib.Path("/srv/workers/jobs/review-router-gateway-spike/poc-20260930/sub2-operator")
source="rr-sub2-spike-20260930-postgres";clone="rr-sub2-spike-20260930-pg-restore"
assert pathlib.Path("/etc/machine-id").read_text().strip()=="d856d40da5ad4e23b4f67773e5942842"
def q(container,sql):return subprocess.check_output(["docker","exec",container,"psql","-U","rr_sub2","-d","rr_sub2","-At","-c",sql],text=True).strip()
tables=q(source,"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
selected=[x for x in tables if x in ["accounts","groups","users","api_keys","account_groups","schema_migrations"]]
counts={x:int(q(source,'SELECT count(*) FROM "'+x+'"')) for x in selected}
dump=b/"ci-private/backup.dump"
with dump.open("wb") as f:subprocess.run(["docker","exec",source,"pg_dump","-U","rr_sub2","-d","rr_sub2","-Fc"],stdout=f,check=True)
os.chmod(dump,0o600)
subprocess.run(["docker","run","-d","--name",clone,"--label","rr.spike=sub2-20260930","--network","none","--cpus","1","--memory","1g","-e","POSTGRES_USER=rr_sub2","-e","POSTGRES_DB=rr_sub2","-e","POSTGRES_HOST_AUTH_METHOD=trust","postgres@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873"],check=True,stdout=subprocess.DEVNULL)
for _ in range(30):
 r=subprocess.run(["docker","exec",clone,"pg_isready","-U","rr_sub2"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if r.returncode==0:break
 time.sleep(.5)
with dump.open("rb") as f:subprocess.run(["docker","exec","-i",clone,"pg_restore","-U","rr_sub2","-d","rr_sub2","--exit-on-error"],stdin=f,check=True,stdout=subprocess.DEVNULL)
after={x:int(q(clone,'SELECT count(*) FROM "'+x+'"')) for x in selected}
ledger=json.loads((b/"broker-state/run-ledger.json").read_text())
receipt={"id":"G04","status":"PASS" if counts==after else "FAIL","evidence_kind":"live-container","tables":counts,"restored_tables":after,"restore_network":"none","public_ports":[],"dump_custody":"root-only; contains credentials; removed after restore","stale_run_access":"Broker run ledger separately preserved; database restore does not erase run tombstones. Combined restored-engine admission NOT RUN.","ledger_entries":len(ledger) if isinstance(ledger,list) else len(ledger.keys()),"at":time.time()}
(b/"receipts/backup-restore.json").write_text(json.dumps(receipt,indent=2));dump.unlink();subprocess.run(["docker","rm","-fv",clone],check=True,stdout=subprocess.DEVNULL);print(json.dumps(receipt))
