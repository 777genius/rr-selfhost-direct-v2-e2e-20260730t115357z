import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { Duplex } from 'node:stream';
import { setImmediate as immediate, setTimeout as sleep } from 'node:timers/promises';
import { request, success } from './overlay/sub2api-regression-lab/client.mjs';
import { request as oldRequest } from './historical-input/prior-code/sub2api-regression-lab/client.mjs';
import { fixture, Inspector } from './overlay/sub2api-regression-lab/wire.mjs';
const MiB=1048576;
// Real ClientRequest/IncomingMessage HTTP parser over a standard custom Agent/Duplex.
// No listening socket possible here. This is behavioral fallback, not a kernelTCP check.
class SyntheticSocket extends Duplex {
  constructor(fragment) {super();this.fragment=fragment;this.started=false;this.sent=0;this.wake=undefined;}
  setNoDelay(){return this;}setTimeout(){return this;}setKeepAlive(){return this;}
  _read(){this.wake?.();this.wake=undefined;}
  _destroy(error,done){this.wake?.();this.wake=undefined;done(error);}
  _write(_b,_encoding,done){if(!this.started){this.started=true;this.send().catch(e=>this.destroy(e));}done();}
  async output(b) {
    for(let i=0;i<b.length&&!this.destroyed;i+=this.fragment) {
      const part=b.subarray(i,i+this.fragment);
      if(!this.push(part))await new Promise(r=>this.wake=r);
      await immediate();
    }
  }
  async send() {
    await immediate();
    await this.output(Buffer.from('HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: 2097152\r\nConnection: close\r\n\r\n'));
    const frames=fixture('messages').frames,comment=Buffer.from(`: ${'x'.repeat(16380)}\n\n`);
    await this.output(frames[0]);let remaining=2*MiB-frames.reduce((n,b)=>n+b.length,0);
    while(remaining>0&&!this.destroyed){const n=remaining<=comment.length+4?remaining:comment.length;
      await this.output(n===comment.length?comment:Buffer.from(`: ${'x'.repeat(n-4)}\n\n`));remaining-=n;}
    for(const frame of frames.slice(1))await this.output(frame);
    if(!this.destroyed)this.push(null);
  }
}
const original=http.globalAgent,agent=new http.Agent({keepAlive:false}),sockets=[];
agent.createConnection=options=>{assert.equal(options.host,'synthetic.invalid');const s=new SyntheticSocket(Number(options.port)===64?65536:Number(options.port));sockets.push(s);return s;};
http.globalAgent=agent;test.after(()=>{agent.destroy();http.globalAgent=original;});
test('historical per-chunk5ms delay fails1800ms deadline on small fragments over realHTTP parser',{timeout:3000},async()=>{
  const r=await oldRequest('http://synthetic.invalid:512','synthetic-only','messages','baseline',{slow:true,timeout:1800}).promise;
  assert.equal(r.transport,'deadline');assert.ok(r.bytes<2*MiB);
  process.stdout.write(JSON.stringify({original_client_transport:r.transport,bytes_before_deadline:r.bytes,deadline_ms:1800,kind:'in-memory-duplex-not-kernelTCP'})+'\n');
});
test('HTTP parser fallback:2MiB/s cumulative byte debt across512/64K fragments',{timeout:8000},async()=>{
  const durations=[];
  for(const size of [512,64]) {
    const r=await request(`http://synthetic.invalid:${size}`,'synthetic-only','messages','pacing',{slow:true,timeout:3000}).promise;
    assert.ok(success(r),JSON.stringify(r));assert.equal(r.bytes,2*MiB);
    assert.ok(r.duration_ms>=900&&r.duration_ms<2000,JSON.stringify(r));durations.push(r.duration_ms);
  }
  assert.ok(Math.abs(durations[0]-durations[1])<350,JSON.stringify(durations));
  process.stdout.write(JSON.stringify({fallback_http_parser_pacing_ms:durations,wire_bytes:2*MiB,kind:'in-memory-duplex-not-kernelTCP'})+'\n');
});
test('HTTP parser fallback:deadline/cancel promptly close stream once and stop pacing',{timeout:2000},async()=>{
  let closed=0;
  const p=request('http://synthetic.invalid:64','synthetic-only','messages','cancel',{slow:true,onClose:()=>closed++});
  await sleep(40);p.cancel();p.cancel();assert.equal((await p.promise).transport,'client_cancel');
  assert.equal(closed,1);assert.equal(sockets.at(-1).destroyed,true);
  const r=await request('http://synthetic.invalid:64','synthetic-only','messages','deadline',{slow:true,timeout:40}).promise;
  assert.equal(r.transport,'deadline');assert.equal(sockets.at(-1).destroyed,true);
});
test('bounded native near2MiB frames parse fragmented UTF8 and full terminals',()=>{
  for(const protocol of ['responses','messages']) {
    const i=new Inspector(protocol);
    for(const frame of fixture(protocol,{near:true}).frames) for(let n=0;n<frame.length;n+=65536)i.push(frame.subarray(n,n+65536));
    const r=i.finish();assert.equal(r.malformed,false);assert.ok(r.terminal_ms!==null&&r.tool_id);
    assert.ok(r.max_frame_bytes>=1.9*MiB&&r.max_frame_bytes<2*MiB);
  }
});
