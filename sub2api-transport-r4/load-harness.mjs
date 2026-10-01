import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const MiB = 1048576;
const source = readFileSync(process.env.RR_LOAD_SOURCE || new URL('./overlay/sub2api-regression-lab/run.mjs', import.meta.url), 'utf8');
const start = source.indexOf('async function load('), end = source.indexOf('async function runOne(');
if (start < 0 || end <= start) throw Error('ACTUAL_LOAD_FUNCTION_MISSING');
export async function exercise({protocol='messages', mib=8, streams=1, stage='memory', count=streams, downstream={}, upstream={}, results: supplied}={}) {
  let now = 1100;
  const ready = {schema:'raw-observation-v2', fresh_container_inspected:true, engine_pid:42, instance:'offline-only', container_id:'a'.repeat(64)};
  const result = {http_status:200, transport:null, failed:false, malformed:false, terminal_ms:1200,
    bytes:mib*MiB, text_delta_bytes:5000, tool_id:protocol==='responses'?'call_rr_transport_01':'toolu_rr_transport_01',
    comments:1, duration_ms:10, max_frame_bytes:1992295, ...downstream};
  const results = supplied || Array.from({length:count},()=>({...result}));
  let issued=0;
  const receipts = Array.from({length:count},()=>({effects:1, finished:true, identity:protocol, close_ms:1000, bytes:mib*MiB, ...upstream}));
  const row={}, clients=[];
  const context = {MiB, readFile:async()=>JSON.stringify(ready), must:(ok,reason)=>{if(!ok)throw Error(reason)},
    mono:()=>now, save:async()=>{}, out:'owned-virtual-evidence', setInterval:()=>1, clearInterval:()=>{},
    telemetry:async()=>[], telemetryVerdict:()=>({status:'NOT RUN', empirical_qualified_status:'NOT RUN', physical_interval_rss_status:'NOTPROVEN'}),
    control:async()=>{}, request:()=>({promise:Promise.resolve(results[issued++]),cancel(){}}),
    success:r=>r.http_status===200&&!r.transport&&!r.failed&&!r.malformed&&r.terminal_ms!==null,
    waitFor:async()=>receipts, sleep:async ms=>{now+=ms}};
  const load = vm.runInNewContext(`(${source.slice(start,end)})`,context);
  await load({deadline:100000, observed:ready}, {id:`${stage}-${protocol}-${mib}-${streams}`, stage, protocol, mib, streams, ...(stage==='soak'?{count}:{})}, {key:'offline-only'}, row, clients);
  return row;
}
