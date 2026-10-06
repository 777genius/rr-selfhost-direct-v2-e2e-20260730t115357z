import test from 'node:test';
import assert from 'node:assert/strict';
import { login as repaired } from './w7-runtime/sub2api-slot-lab/adapter.mjs';
import { admin } from './w7-runtime/sub2api-regression-lab/common.mjs';
const login = process.env.SLOT_LOGIN_OLD === '1' ? (c, body) => admin(c, '/auth/login', 'POST', body) : repaired;
const native = {error:'rate limit exceeded',message:'Too many requests, please try again later'};
const response = (status=200, data={code:0,data:{access_token:'test-fixture-literal'}}, header='2') => ({status,ok:status===200,headers:new Headers(header===null?{}:{'Retry-After':header}),arrayBuffer:async()=>Buffer.from(JSON.stringify(data))});
async function run(fn, {deadline=35000, replies=[response(429,native),response()], network=false, oversleep=0}={}) {
 let now=0; const calls=[], sleeps=[]; const realFetch=globalThis.fetch, realClock=process.hrtime.bigint;
 process.hrtime.bigint=()=>BigInt(now*1e6);
 globalThis.fetch=async(url,options)=>{calls.push({at:now,url,options}); if(network)throw new Error('network'); return replies.shift();};
 const c={engine_url:'http://sub2api:8080',admin_bearer:'private-admin',deadline,supervisor_deadline:1200000};
 const io={mono:()=>now,sleep:async(ms)=>{sleeps.push(ms);now+=ms+oversleep;}};
 try {await fn(()=>login(c,{email:'synthetic@example.invalid',password:'private-password'},io),calls,sleeps);} finally {globalThis.fetch=realFetch;process.hrtime.bigint=realClock;}
}
test('known native 429 waits exactly Retry-After once; request bytes, redirect and signal retained',async()=>run(async(login,calls,sleeps)=>{
 assert.deepEqual(await login(),{access_token:'test-fixture-literal'});assert.deepEqual(sleeps,[2000]);assert.deepEqual(calls.map(c=>c.at),[0,2000]);
 for(const {url,options:o} of calls){assert.equal(url,'http://sub2api:8080/api/v1/auth/login');assert.equal(o.method,'POST');assert.equal(o.redirect,'error');assert.ok(o.signal instanceof AbortSignal);assert.deepEqual(o.headers,{'content-type':'application/json',authorization:'Bearer private-admin'});assert.equal(o.body,JSON.stringify({email:'synthetic@example.invalid',password:'private-password'}));}
}));
for(const header of [null,'','0','01','-1','1.0','1e1','61','99999999999999999999999','Thu, 01 Oct 2026 18:00:00 GMT'])test(`invalid header ${header} fails without retry`,async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{replies:[response(429,native,header)]}));
for(const status of [401,403,500,503])test(`${status} exactly one dispatch`,async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{replies:[response(status)]}));
test('network exactly one dispatch',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{network:true}));
test('unknown 429 effect no retry',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{replies:[response(429,{error:'unknown'})]}));
test('second native 429 no third dispatch',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,2);assert.deepEqual(sleeps,[2000]);},{replies:[response(429,native),response(429,native)]}));
test('near zero admission budget no dispatch',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,0);assert.deepEqual(sleeps,[]);},{deadline:.01}));
test('wait plus normal response cannot fit no retry',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{deadline:6999}));
test('60 second header cannot extend original 35 second deadline',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{replies:[response(429,native,'60')]}));
test('sleep deadline overrun no retry dispatch',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[2000]);},{oversleep:35000}));
test('body limit preserved',async()=>run(async(login,calls)=>{await assert.rejects(login(),/CONTROL_OR_ADMIN_LIMIT/);assert.equal(calls.length,1);},{replies:[{...response(),arrayBuffer:async()=>Buffer.alloc(2097153)}]}));
test('code rejection preserved',async()=>run(async(login,calls)=>{await assert.rejects(login(),/ADMIN_API_REJECTED/);assert.equal(calls.length,1);},{replies:[response(200,{code:1,data:{access_token:'bad'}})]}));
for(const seconds of [1,60])test(`valid boundary ${seconds} waits exactly once`,async()=>run(async(login,calls,sleeps)=>{assert.deepEqual(await login(),{access_token:'test-fixture-literal'});assert.deepEqual(sleeps,[seconds*1000]);assert.deepEqual(calls.map(c=>c.at),[0,seconds*1000]);},{deadline:seconds*1000+5000,replies:[response(429,native,String(seconds)),response()]}));
test('known 429 with rejected API code cannot retry',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login(),/ADMIN_API_REJECTED/);assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{replies:[response(429,{...native,code:1})]}));
test('malformed response cannot retry',async()=>run(async(login,calls,sleeps)=>{await assert.rejects(login());assert.equal(calls.length,1);assert.deepEqual(sleeps,[]);},{replies:[{...response(429,native),arrayBuffer:async()=>Buffer.from('{')}]}));
