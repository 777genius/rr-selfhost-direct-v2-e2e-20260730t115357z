import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import { randomBytes } from 'node:crypto';
import { setImmediate as immediate, setTimeout as sleep } from 'node:timers/promises';
import { request, success } from './overlay/sub2api-regression-lab/client.mjs';
import { request as oldRequest } from './historical-input/prior-code/sub2api-regression-lab/client.mjs';
import { fixture } from './overlay/sub2api-regression-lab/wire.mjs';
import { createMock } from './overlay/sub2api-regression-lab/mock.mjs';
const MiB=1048576;
// Standard Node Agent redirects synthetic test hostnames to Linux abstract Unix sockets.
// No DNS, IP socket, external service or production-specific test hook is involved.
const paths=new Map(), originalAgent=http.globalAgent;
const agent=new http.Agent({keepAlive:false});
agent.createConnection=options=>{
  const path=paths.get(options.host);assert.ok(path,'only owned synthetic destinations');
  return net.createConnection({path});
};
http.globalAgent=agent;
test.after(()=>{agent.destroy();http.globalAgent=originalAgent;});
async function listen(server,t) {
  const host=`lab${paths.size}.invalid`,path='\0rr-transport-r4-'+randomBytes(8).toString('hex');
  try { await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(path,resolve);}); }
  catch(error) { if(error.code==='EPERM'||error.code==='EACCES') { t.skip('NOT RUN: sandbox denies local socket listen'); return null; } throw error; }
  paths.set(host,path);
  t.after(async()=>{server.stopLab?.();server.closeAllConnections();await new Promise(r=>server.close(r));paths.delete(host);});
  return `http://${host}`;
}
async function fetch(url,{method='GET',headers={},body}={}) {
  return new Promise((resolve,reject)=>{
    const req=http.request(url,{method,headers},res=>{
      const parts=[];let n=0;
      res.on('data',b=>{n+=b.length;assert.ok(n<2*MiB);parts.push(b);});
      res.once('end',()=>resolve({status:res.statusCode,json:async()=>JSON.parse(Buffer.concat(parts))}));
      res.once('error',reject);
    });req.once('error',reject);req.end(body);
  });
}
function fragmentedServer(fragmentBytes) {
  const stats={closed:0,sent:0};
  const server=http.createServer(async(req,res)=>{
    req.resume(); res.on('close',()=>stats.closed++);
    const frames=fixture('messages').frames;
    const semantic=frames.reduce((n,b)=>n+b.length,0);
    const comment=Buffer.from(`: ${'x'.repeat(16380)}\n\n`);
    async function write(frame) {
      for(let i=0;i<frame.length&&!res.destroyed;i+=fragmentBytes) {
        const part=frame.subarray(i,i+fragmentBytes);stats.sent+=part.length;
        if(!res.write(part)) await new Promise(resolve=>{const done=()=>{res.off('drain',done);res.off('close',done);resolve();};res.once('drain',done);res.once('close',done);});
        await immediate(); // Actual separate write turns, exercise TCP fragmentation.
      }
    }
    try {
      res.writeHead(200,{'content-type':'text/event-stream'});res.flushHeaders();
      await write(frames[0]);
      let remain=2*MiB-semantic;
      while(remain>0&&!res.destroyed){const n=remain<=comment.length+4?remain:comment.length;
        await write(n===comment.length?comment:Buffer.from(`: ${'x'.repeat(n-4)}\n\n`));remain-=n;}
      for(const frame of frames.slice(1)) await write(frame);
      if(!res.destroyed)res.end();
    } catch {res.destroy();}
  });
  return {server,stats};
}
test('old chunk delay reproduces timeout; repaired byte pacing independent of actual local socket fragmentation',{timeout:12000},async t=>{
  const small=fragmentedServer(512),large=fragmentedServer(65536);
  const a=await listen(small.server,t);if(!a)return;const b=await listen(large.server,t);if(!b)return;
  const old=await oldRequest(a,'synthetic-only','messages','baseline',{slow:true,timeout:1800}).promise;
  assert.equal(old.transport,'deadline');assert.equal(success(old),false);
  const readings=[];
  for(const base of [a,b]) {
    const r=await request(base,'synthetic-only','messages','pacing',{slow:true,timeout:4000}).promise;
    assert.ok(success(r)); assert.equal(r.bytes,2*MiB);
    assert.ok(r.duration_ms>=900&&r.duration_ms<2000,`duration=${r.duration_ms}`);
    readings.push(r.duration_ms);
  }
  assert.ok(Math.abs(readings[0]-readings[1])<350,JSON.stringify(readings));
  process.stdout.write(JSON.stringify({local_socket_pacing_ms:readings,wire_bytes:2*MiB,old_transport:old.transport})+'\n');
});
test('deadline and cancel close owned socket and clear outstanding slow timer',{timeout:3000},async t=>{
  const f=fragmentedServer(65536),base=await listen(f.server,t);if(!base)return;
  let closes=0;
  const p=request(base,'synthetic-only','messages','cancel',{slow:true,onClose:()=>closes++});
  await sleep(40);p.cancel();p.cancel();
  const r=await p.promise;assert.equal(r.transport,'client_cancel');assert.equal(closes,1);
  const d=await request(base,'synthetic-only','messages','deadline',{slow:true,timeout:40}).promise;
  assert.equal(d.transport,'deadline');await sleep(50);assert.ok(f.stats.closed>=2);
});
test('actual synthetic mock wire8/32/64MiB native terminal/tool/effect checks; near2MiB bounded frames',{timeout:20000},async t=>{
  const sentinels={responses:'test-responses',messages:'test-messages'},control_token='synthetic-test-control-000000';
  const server=createMock({sentinels,control_token});const base=await listen(server,t);if(!base)return;
  for(const protocol of ['responses','messages'])for(const mib of [8,32,64]) {
    const id=`memory-${protocol}-${mib}-1`;
    const rule=await fetch(base+'/__lab/rule',{method:'POST',headers:{'content-type':'application/json','x-lab-control':control_token},body:JSON.stringify({id,mode:'memory',mib})});
    assert.equal(rule.status,200);
    const r=await request(base,sentinels[protocol],protocol,id,{timeout:10000}).promise;
    assert.ok(success(r),JSON.stringify(r));assert.equal(r.bytes,mib*MiB);
    assert.ok(r.max_frame_bytes>1.8*MiB&&r.max_frame_bytes<=2*MiB);
    assert.ok(r.comments>0&&r.tool_id&&r.text_delta_bytes>4096);
  }
  const state=await (await fetch(base+'/__lab/state',{headers:{'x-lab-control':control_token}})).json();
  assert.equal(state.total,6);assert.equal(state.effects,6);
  assert.ok(state.records.every(r=>r.bytes===Number(r.id.split('-')[2])*MiB&&r.finished&&r.close_ms!==null));
  assert.equal(state.active,0);
});
test('paced concurrency1/5/20 uses actual synthetic sockets and one effect per request',{timeout:20000},async t=>{
  const sentinels={responses:'test-responses',messages:'test-messages'},control_token='synthetic-test-control-000000';
  const server=createMock({sentinels,control_token});const base=await listen(server,t);if(!base)return;
  for(const streams of [1,5,20]) {
    const id=`memory-messages-8-${streams}`;
    await fetch(base+'/__lab/rule',{method:'POST',headers:{'content-type':'application/json','x-lab-control':control_token},body:JSON.stringify({id,mode:'memory',mib:8})});
    const results=await Promise.all(Array.from({length:streams},()=>request(base,sentinels.messages,'messages',id,{slow:true,timeout:7000}).promise));
    assert.ok(results.every(r=>success(r)&&r.bytes===8*MiB&&r.duration_ms>=3800&&r.duration_ms<6500));
  }
  const state=await(await fetch(base+'/__lab/state',{headers:{'x-lab-control':control_token}})).json();
  assert.equal(state.total,26);assert.equal(state.effects,26);assert.equal(state.active,0);
});
