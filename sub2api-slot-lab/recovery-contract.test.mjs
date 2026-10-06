import test from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
const dir = resolve(process.env.SLOT_CONTRACT_RUNTIME ?? 'sub2api-slot-lab/build/sub2api-regression-lab');
const { Inspector, fixture, event } = await import(pathToFileURL(`${dir}/wire.mjs`));
const { success } = await import(pathToFileURL(`${dir}/client.mjs`));
function accepted(protocol, frames) {
  const i = new Inspector(protocol);
  try { for (const f of frames) for (let n=0; n<f.length; n+=173) i.push(f.subarray(n,n+173)); }
  catch { return false; }
  return success({ http_status:200, transport:null, ...i.finish() });
}
for (const protocol of ['responses','messages']) {
  test(`${protocol}: actual existing healthy mock remains valid`, () => assert.equal(accepted(protocol, fixture(protocol).frames),true));
  test(`${protocol}: review malformed reproduction fails recovery`, () => {
    const frames = protocol === 'responses' ? [event('message_start',{}),event('response.completed',{response:{status:'completed',output:[{}]}})] :
      [event('message_start',{}),event('message_delta',{delta:{stop_reason:'end_turn'}}),event('message_stop',{})];
    assert.equal(accepted(protocol,frames),false);
  });
  for (const mutation of ['start','terminal','usage','usage-conflict','id','delta','duplicate','junk','tool']) test(`${protocol}: reject ${mutation}`, () => {
    const frames=fixture(protocol,{tool:mutation==='tool'}).frames.map(x=>Buffer.from(x));
    if(mutation==='start') frames.shift();
    if(mutation==='terminal') frames.pop();
    if(mutation==='duplicate') frames.push(frames.at(-1));
    if(mutation==='junk') frames.push(event('unrelated',{}));
    if(mutation==='delta') frames.splice(protocol==='responses'?4:2,1);
    if(mutation==='usage') {
      const n=protocol==='responses'?frames.length-1:frames.length-2;
      frames[n]=Buffer.from(frames[n].toString().replace('"output_tokens":20','"output_tokens":-1'));
    }
    if(mutation==='usage-conflict') {
      const n=protocol==='responses'?frames.length-1:frames.length-2;
      frames[n]=Buffer.from(frames[n].toString().replace(protocol==='responses'?'"total_tokens":30':'"output_tokens":20',protocol==='responses'?'"total_tokens":31':'"input_tokens":999,"output_tokens":20'));
    }
    if(mutation==='id') {
      const n=protocol==='responses'?4:2;
      frames[n]=Buffer.from(frames[n].toString().replace(protocol==='responses'?'"item_id":"msg_lab"':'"index":0',protocol==='responses'?'"item_id":"other"':'"index":1'));
    }
    assert.equal(accepted(protocol,frames),false);
  });
}
