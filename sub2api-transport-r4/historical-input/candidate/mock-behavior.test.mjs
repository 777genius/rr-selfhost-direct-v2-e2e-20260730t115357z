import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { Duplex } from 'node:stream';
import { request, success } from './overlay/sub2api-regression-lab/client.mjs';
import { createMock } from './overlay/sub2api-regression-lab/mock.mjs';
const MiB=1048576;
// Real http.Server/ClientRequest parsers linked by standard Duplex streams.
// No kernel socket or engine; synthetic fixture/effect correctness only.
class Endpoint extends Duplex {
  setNoDelay(){return this;}setTimeout(){return this;}setKeepAlive(){return this;}
  _read(){const cb=this.peer?.pending;this.peer&&(this.peer.pending=undefined);cb?.();}
  _write(b,_enc,cb){if(this.peer.destroyed)return cb(Error('OWNED_PEER_CLOSED'));if(this.peer.push(b))cb();else this.pending=cb;}
  _final(cb){this.peer.push(null);cb();}
  _destroy(error,cb){this.pending?.();this.pending=undefined;if(!this.peer.destroyed)this.peer.destroy();cb(error);}
}
const original=http.globalAgent,agent=new http.Agent({keepAlive:false});
let server;
agent.createConnection=options=>{
  assert.equal(options.host,'synthetic.invalid');
  const client=new Endpoint(),upstream=new Endpoint();client.peer=upstream;upstream.peer=client;
  server.emit('connection',upstream);return client;
};
http.globalAgent=agent;
test.after(()=>{server?.stopLab();server?.closeAllConnections();agent.destroy();http.globalAgent=original;});
const sentinels={responses:'test-responses',messages:'test-messages'},control_token='synthetic-test-control-000000';
async function control(action,body){return new Promise((resolve,reject)=>{
  const req=http.request(`http://synthetic.invalid/__lab/${action}`,{method:body?'POST':'GET',headers:{'content-type':'application/json','x-lab-control':control_token}},res=>{
    let raw='';res.on('data',b=>raw+=b);res.once('end',()=>{assert.equal(res.statusCode,200);resolve(JSON.parse(raw));});res.once('error',reject);
  });req.once('error',reject);req.end(body?JSON.stringify(body):undefined);
});}
test('actual adopted mock over HTTP/Duplex: exact8/32/64MiB and native bounded terminal/effects',{timeout:30000},async()=>{
  server=createMock({sentinels,control_token});
  const observations=[];
  for(const protocol of ['responses','messages'])for(const mib of [8,32,64]) {
    const id=`memory-${protocol}-${mib}-1`;
    await control('rule',{id,mode:'memory',mib});
    const r=await request('http://synthetic.invalid',sentinels[protocol],protocol,id,{timeout:15000}).promise;
    assert.ok(success(r),JSON.stringify(r));assert.equal(r.bytes,mib*MiB);
    assert.ok(r.max_frame_bytes>1.8*MiB&&r.max_frame_bytes<=2*MiB);
    assert.ok(r.comments>0&&r.text_delta_bytes>4096&&r.tool_id);
    observations.push({protocol,mib,wire_bytes:r.bytes,max_frame_bytes:r.max_frame_bytes});
  }
  const state=await control('state');assert.equal(state.total,6);assert.equal(state.effects,6);
  assert.equal(state.active,0);assert.ok(state.records.every(r=>r.finished&&r.close_ms!==null&&r.bytes===Number(r.id.split('-')[2])*MiB));
  process.stdout.write(JSON.stringify({synthetic_mock_http_duplex:observations,attempts:state.total,effects:state.effects,active:state.active})+'\n');
});
test('actual adopted mock over HTTP/Duplex: paced1/5/20 streams preserve one effect and cleanup',{timeout:20000},async()=>{
  for(const streams of [1,5,20]) {
    const id=`memory-messages-8-${streams}.concurrency`;
    await control('rule',{id,mode:'memory',mib:8});
    const results=await Promise.all(Array.from({length:streams},()=>request('http://synthetic.invalid',sentinels.messages,'messages',id,{slow:true,timeout:7000}).promise));
    assert.ok(results.every(r=>success(r)&&r.bytes===8*MiB&&r.duration_ms>=3800&&r.duration_ms<6500),JSON.stringify(results.map(r=>({bytes:r.bytes,duration:r.duration_ms,transport:r.transport}))));
  }
  const state=await control('state');assert.equal(state.total,32);assert.equal(state.effects,32);assert.equal(state.active,0);
});
test('Messages32/64MiB slow discard completes within original65sec deadline over HTTP/Duplex',{timeout:60000},async()=>{
  const observations=[];
  for(const mib of [32,64]) {
    const id=`memory-messages-${mib}-1.paced`;
    await control('rule',{id,mode:'memory',mib});
    const r=await request('http://synthetic.invalid',sentinels.messages,'messages',id,{slow:true,timeout:65000}).promise;
    assert.ok(success(r),JSON.stringify(r));assert.equal(r.bytes,mib*MiB);
    assert.ok(r.duration_ms>=mib*500-250&&r.duration_ms<mib*500+1500);
    observations.push({mib,bytes:r.bytes,duration_ms:r.duration_ms,transport:r.transport});
  }
  const state=await control('state');assert.equal(state.total,34);assert.equal(state.effects,34);assert.equal(state.active,0);
  process.stdout.write(JSON.stringify({paced_messages_http_duplex:observations,attempts:state.total,effects:state.effects,active:state.active})+'\n');
});
