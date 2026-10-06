import json,subprocess,pathlib,shutil,time,os
b=pathlib.Path("/srv/workers/jobs/review-router-gateway-spike/poc-20260930/sub2-operator");t=b.parent/"sub2-transfer"
assert pathlib.Path("/etc/machine-id").read_text().strip()=="d856d40da5ad4e23b4f67773e5942842"
orig=[pathlib.Path("/etc/subscription-runtime/secrets/review-router/"+n) for n in ["mimo-token-plan-api-key","openrouter-e2e-api-key"]]
before=[(x.stat().st_ino,x.stat().st_size,x.stat().st_mtime_ns) for x in orig]
names=subprocess.check_output(["docker","ps","-a","--filter","label=rr.spike=sub2-20260930","--format","{{.Names}}"],text=True).splitlines();assert all(n.startswith("rr-sub2-spike-20260930-") for n in names)
for n in names:subprocess.run(["docker","rm","-fv",n],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
nets=subprocess.check_output(["docker","network","ls","--filter","label=rr.spike=sub2-20260930","--format","{{.Name}}"],text=True).splitlines();assert all(n.startswith("rr-sub2-spike-20260930-") for n in nets)
for n in nets:subprocess.run(["docker","network","rm",n],check=True,stdout=subprocess.DEVNULL)
paths=["broker-private","broker-state","engine-data","postgres","lab-private","ci-private","bootstrap-private.json","admin.key","admin-token","login.json","redis.conf","pg.env","engine.env","live-customer-state.json","live-workspaces.json","live-scope-keys.json"]+[f"runner-work-{i}" for i in range(1,5)]
paths += [x.name for x in b.glob("live-*.key")]
removed=[]
for n in paths:
 p=b/n
 if p.is_symlink():p.unlink();removed.append(n)
 elif p.is_dir():shutil.rmtree(p);removed.append(n)
 elif p.exists():p.unlink();removed.append(n)
for p in t.glob("*private.log"):p.unlink()
after=[(x.stat().st_ino,x.stat().st_size,x.stat().st_mtime_ns) for x in orig];assert before==after
assert all(x.stat().st_uid==0 and x.stat().st_mode&0o777==0o600 for x in orig)
remaining=subprocess.check_output(["docker","ps","-a","--filter","label=rr.spike=sub2-20260930","--format","{{.Names}}"],text=True).strip()
receipt={"status":"PASS" if not remaining else "FAIL","ids":["D09","G07"],"evidence_kind":"actual-operator-teardown","containers_removed":len(names),"networks_removed":len(nets),"private_paths_removed":len(removed),"remaining_owned_containers":bool(remaining),"original_root_only_provider_files_preserved":before==after,"public_ports":[],"workflow":"disabled_manually","live_oauth_identities_imported":0,"production_pool_imported_or_replaced":False,"at":time.time(),"custody_limit":"Logical file/container removal; no secure-erasure guarantee for underlying storage snapshots."}
(b/"receipts/teardown.json").write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
