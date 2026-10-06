import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { plan, limits, ownedKeys, counts, finalZero, retainsFirst, recordSet, cancelEvidence, pollUntil } from './contracts.mjs';
import { decode, encode, RedisObserver } from './redis.mjs';
import { fixture, Inspector } from './build/sub2api-regression-lab/wire.mjs';
import { setup, cleanup } from './build/sub2api-slot-lab/adapter.mjs';
const clone = x => structuredClone(x);
function snap(user = 1, account = 1, userWait = 0, accountWait = 0) {
  const slots = (count, prefix) => ({ count, members: Array.from({ length: count }, (_, i) => `${prefix}.${i}`), ttl_ms: 900000 });
  return { started_ms: 100, observed_ms: 110, user: slots(user, 'user'), account: slots(account, 'account'), key: slots(user, 'key'),
    userWait: { count: userWait, ttl_ms: 900000 }, accountWait: { count: accountWait, ttl_ms: 900000 } };
}
const wire = () => ({ id: 'first', identity: 'responses', protocol: 'responses', first_flush_ms: 50, hold_until_ms: 60,
  close_ms: 150, socket_close_ms: 152, finished: false, terminal_ms: null, effects: 1, release_ms: null, reset_ms: null });

test('matrix is exactly 20 opt-in cycles per protocol/lane plus four default controls, unique requests', () => {
  const specs = plan(); assert.equal(specs.length, 84);
  for (const protocol of ['responses', 'messages']) for (const lane of ['account', 'user']) {
    assert.equal(specs.filter(s => s.protocol === protocol && s.lane === lane && s.optin).length, 20);
    assert.equal(specs.filter(s => s.protocol === protocol && s.lane === lane && !s.optin).length, 1);
  }
  assert.equal(new Set(specs.flatMap(s => ['first','pending','third'].map(x => `${s.id}.${x}`))).size, 252);
  assert.deepEqual(limits('account'), { user: 2, account: 1 }); assert.deepEqual(limits('user'), { user: 1, account: 2 });
});
test('exact numeric owned Redis namespaces and rejection of non-owned IDs', () => {
  assert.deepEqual(ownedKeys({ user: 2, account: 3, key: 4 }), { user: 'concurrency:user:2', account: 'concurrency:account:3',
    key: 'concurrency:api_key:4', userWait: 'concurrency:wait:2', accountWait: 'wait:account:3' });
  for (const value of ['*', '1', -1, 0, 1.5, Number.MAX_SAFE_INTEGER+1]) assert.throws(() => ownedKeys({ user: value, account: 1, key: 1 }));
});
test('real-handler queue shape requires correct lane, pending lease and original first members', () => {
  const active = snap(), accountQueue = snap(2, 1, 0, 1), userQueue = snap(1, 1, 1, 0);
  assert.ok(counts(accountQueue, 2, 1, 0, 1)); assert.ok(counts(userQueue, 1, 1, 1, 0));
  assert.ok(retainsFirst(active, accountQueue));
  const lost = clone(accountQueue); lost.account.members = ['different']; assert.equal(retainsFirst(active, lost), false);
  assert.equal(counts(snap(), 1, 1, 1, 0), false); // a transport bottleneck never enters the user queue
  const expiring = snap(); expiring.user.ttl_ms = 200; assert.throws(() => counts(expiring, 1, 1));
});
test('RED mutations: waiter, pending lease, retained active lease, forced close, late close and duplicate effect all fail', () => {
  const zero = snap(0,0); zero.observed_ms = 160;
  assert.doesNotThrow(() => cancelEvidence(wire(), zero, 120, 170));
  for (const [field,value] of [['close_ms',null],['close_ms',1400],['close_ms',175],['socket_close_ms',null],['socket_close_ms',1400],['socket_close_ms',175],['finished',true],['terminal_ms',145],['release_ms',130],
    ['reset_ms',130],['safety_stop_ms',130],['effects',2],['first_flush_ms',null],['first_flush_ms',undefined],['first_flush_ms',Infinity],
    ['first_flush_ms',125],['hold_until_ms',125]]) {
    const r = wire(); r[field]=value; assert.throws(() => cancelEvidence(r, zero, 120, 170), field);
  }
  for (const s of [snap(1,0),snap(0,1),snap(0,0,1,0),snap(0,0,0,1)]) assert.throws(() => cancelEvidence(wire(),s,120,170));
  assert.throws(() => cancelEvidence(wire(),zero,120,1371)); // poll completed too late despite earlier wire close
  const state = { exceeded:false,total:1,records:[wire()] };
  assert.equal(recordSet(state,['first'],1).length,1);
  assert.throws(() => recordSet({ ...state, records:[wire(),wire()] },['first'],2));
  assert.throws(() => recordSet({ ...state, exceeded:true },['first'],1));
});
test('deadline counts slow observation overhead and never restarts after timeout', async () => {
  let now=0, calls=0;
  await assert.rejects(pollUntil(async () => { calls++; now+=1260; return true; }, x=>x,1250,
    { now:()=>now, pause:async ms=>{now+=ms;} }), /OBSERVATION_DEADLINE/);
  assert.equal(calls,1);
  now=0; const result=await pollUntil(async () => { now+=30; return now>=90; },x=>x,1250,
    { now:()=>now,pause:async ms=>{now+=ms;} }); assert.equal(result,true);
});
test('deadline also counts assertion overhead after an otherwise timely observation', async () => {
  let now=0, calls=0;
  await assert.rejects(pollUntil(async () => { calls++; now=1240; return true; }, x=>{ now+=20; return x; },1250,
    { now:()=>now, pause:async ms=>{now+=ms;} }), /OBSERVATION_DEADLINE/);
  assert.equal(calls,1);
});
test('RESP parser handles arbitrary partial frames, null GET, arrays and redacted Redis errors offline', () => {
  const b=Buffer.from('*3\r\n:2\r\n$3\r\nfoo\r\n$-1\r\n');
  for(let n=0;n<b.length;n++) assert.equal(decode(b.subarray(0,n)),null);
  assert.deepEqual(decode(b),{ value:[2,'foo',null],offset:b.length });
  assert.equal(encode(['GET','wait:account:12']).toString(),'*2\r\n$3\r\nGET\r\n$15\r\nwait:account:12\r\n');
  assert.throws(()=>decode(Buffer.from('-ERR private-sensitive-detail\r\n')), e=>e.message==='REDIS_REJECTED');
});
test('Redis snapshot requests only read-only exact keys and rejects malformed real-count replies', async () => {
  const r = new RedisObserver('a'.repeat(64)); let commands;
  r.transaction = async x => { commands=x; return [1,['user'],900000,1,['account'],900000,1,['key'],900000,null,-2,'0',900000]; };
  const s=await r.snapshot({ user:12,account:14,key:16 },Infinity); assert.ok(counts(s,1,1));
  assert.equal(commands.length,13); assert.ok(commands.every(x=>['ZCARD','ZRANGE','PTTL','GET'].includes(x[0])));
  assert.ok(commands.every(x=>/:\d+$/.test(x[1])));
  r.transaction=async()=>[1,['user'],900000,1,['account'],900000,1,['key'],900000,'-1',900000,null,-2];
  await assert.rejects(r.snapshot({ user:12,account:14,key:16 },Infinity),/WAIT_COUNTER_INVALID/);
});
test('actual Redis leak cardinalities and near-expiry TTLs remain available for failure evidence', async () => {
  const r = new RedisObserver('a'.repeat(64));
  r.transaction = async () => [3,['first','pending','orphan'],900000,1,['first-account'],900000,
    3,['first-key','pending-key','orphan-key'],900000,'2',900000,null,-2];
  const leaked = await r.snapshot({ user:12,account:14,key:16 },Infinity);
  assert.equal(leaked.user.count,3); assert.equal(leaked.userWait.raw,'2');
  assert.equal(counts(leaked,2,1,0,1),false); assert.equal(finalZero(leaked),false);
  r.transaction = async () => [1,['first'],100,1,['first-account'],900000,1,['first-key'],900000,null,-2,null,-2];
  const expiring = await r.snapshot({ user:12,account:14,key:16 },Infinity);
  assert.equal(expiring.user.ttl_ms,100); assert.throws(() => counts(expiring,1,1),/LEASE_EXPIRY_TOO_NEAR/);
});
test('late invalid or expiring failure snapshots fail closed without throwing past resource cleanup', () => {
  const expired=snap(); expired.user.ttl_ms=100;
  for(const s of [null,{},expired,snap(0,0,2,0),snap(3,0)])
    assert.doesNotThrow(() => { assert.equal(finalZero(s),false); });
  assert.equal(finalZero(snap(0,0)),true);
});
test('reused genuine SSE fixtures validate fragmented Responses and Messages healthy terminals', () => {
  for (const protocol of ['responses','messages']) {
    const inspector=new Inspector(protocol), bytes=Buffer.concat(fixture(protocol).frames);
    for(let i=0;i<bytes.length;i+=3) inspector.push(bytes.subarray(i,i+3));
    const result=inspector.finish(); assert.equal(result.malformed,false); assert.equal(result.failed,false);
    assert.ok(result.terminal_ms!==null && result.text_delta_bytes>4096 && result.ack_ms!==null);
  }
});
test('actual admin adapter persists trusted opt-in/default, limits and stable native key, journals create before transport', async () => {
  const temporary=await mkdtemp(resolve('sub2api-slot-lab/build/offline-')); const previous=globalThis.fetch;
  try {
    for(const optin of [true,false]) for(const lane of ['account','user']) for(const protocol of ['responses','messages']) {
      let n=10; const objects={}, writes=[], path=`${temporary}/${lane}-${protocol}-${optin}.json`, journal={ path, resources:[], intent:null };
      globalThis.fetch=async(url,options) => {
        const route=new URL(url).pathname.replace('/api/v1',''), body=options.body&&JSON.parse(options.body);
        let data;
        if(options.method==='POST' && route==='/auth/login') data={ access_token:'fixture-user' };
        else if(options.method==='POST') {
          assert.ok(JSON.parse(await readFile(path,'utf8')).intent); writes.push({route,body});
          const kind=route.split('/').at(-1); data={...body,id:++n,status:'active'};
          if(kind==='keys') Object.assign(data,{key:'offline-synthetic-native-key',user_id:objects.users.id});
          objects[kind]=data;
        } else if(options.method==='DELETE') { assert.ok(journal.resources.some(r=>r.id===Number(route.split('/').at(-1)))); data={}; }
        else data=objects[route.split('/').at(-2)];
        return { ok:true, arrayBuffer:async()=>Buffer.from(JSON.stringify({code:0,data})) };
      };
      const spec={id:`offline.${protocol}.${lane}.${optin}`,protocol,lane,optin}, c={engine_url:'http://sub2api:8080',mock_url:'http://mock:8099',
        sentinels:{responses:'rr-synthetic-offline-responses',messages:'rr-synthetic-offline-messages'},admin_bearer:'offline-admin',deadline:Infinity};
      const tenant=await setup(c,spec,journal); assert.equal(tenant.key,'offline-synthetic-native-key');
      const account=writes.find(w=>w.route==='/admin/accounts').body, user=writes.find(w=>w.route==='/admin/users').body;
      assert.equal(account.concurrency,limits(lane).account); assert.equal(user.concurrency,limits(lane).user);
      assert.equal(Object.hasOwn(account.extra,'native_api_key_cancel_on_disconnect'),optin);
      assert.equal(account.extra.openai_disable_capability_probe,true); assert.equal(journal.intent,null);
      assert.deepEqual(await cleanup(c,journal),{failures:0,ambiguous_intent:false,remaining:[]});
    }
  } finally { globalThis.fetch=previous; await rm(temporary,{recursive:true,force:true}); }
});
