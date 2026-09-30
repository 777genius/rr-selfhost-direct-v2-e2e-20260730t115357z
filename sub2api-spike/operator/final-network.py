import pathlib,json,subprocess
b=pathlib.Path("/srv/workers/jobs/review-router-gateway-spike/poc-20260930/sub2-operator")
checks=[]
for n,port in [("engine",8080),("postgres",5432),("redis",6379)]:
 d=json.loads(subprocess.check_output(["docker","inspect",f"rr-sub2-spike-20260930-{n}"]))[0]
 assert not d["HostConfig"]["PortBindings"]
 checks.append({"label":n,"host":d["NetworkSettings"]["Networks"]["rr-sub2-spike-20260930-control"]["IPAddress"],"port":port})
js="""const checks=JSON.parse(process.argv[1]);const out=[];for(const c of checks){try{const s=await import('node:net');await new Promise((ok,no)=>{const t=s.createConnection(c.port,c.host);t.setTimeout(700);t.on('connect',()=>{t.destroy();ok()});t.on('error',no);t.on('timeout',()=>{t.destroy();no(Error('blocked'))})});out.push({resource:c.label,reachable:true})}catch{out.push({resource:c.label,reachable:false})}}let broker=false;try{broker=(await fetch('http://broker:8787/denied',{signal:AbortSignal.timeout(2000)})).status===404}catch{}console.log(JSON.stringify({resources:out,broker_reachable:broker}));"""
r=subprocess.check_output(["docker","run","--rm","--name","rr-sub2-spike-20260930-netcheck","--label","rr.spike=sub2-20260930","--network","rr-sub2-spike-20260930-runner","--user","1001","--entrypoint","node","rr-gateway-spike-runner:20260930-sealed","-e",js,json.dumps(checks)],text=True)
p=json.loads(r);p.update({"id":"D04","evidence_kind":"live-container","status":"PASS" if p["broker_reachable"] and all(not x["reachable"] for x in p["resources"]) else "FAIL","no_published_ports":True,"limit":"Disposable nonroot probe on same runner bridge. Real terminal runners inspected for matching networks/mount isolation; live agent network request not replayed."});(b/"receipts/network-boundary.json").write_text(json.dumps(p,indent=2));print(json.dumps(p))
