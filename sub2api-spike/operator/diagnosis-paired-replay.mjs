// Trusted operator: two planned direct requests, no retries or raw output export.
import {readFile,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const a=JSON.parse(await readFile('/private/request-11.json','utf8'));
const b=JSON.parse(await readFile('/private/request-12.json','utf8'));
const withoutInput=x=>{const y={...x};delete y.input;return y};
assert.deepEqual(withoutInput(a),withoutInput(b));
assert.deepEqual(a.input.filter(x=>x.type!=='reasoning'),b.input);
const key=(await readFile('/private/mimo.key','utf8')).trim();
const receipts=[];
for(const [name,body] of [['stripped',b],['retained',a]]){
 const r=await fetch('https://token-plan-sgp.xiaomimimo.com/v1/responses',{method:'POST',headers:{'content-type':'application/json',authorization:`Bearer ${key}`,'user-agent':'codex_cli_rs/0.159.2','originator':'codex_cli_rs'},body:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(180000)});
 const raw=await r.text();await writeFile(`/private/paired-${name}.sse`,raw,{mode:0o600});
 const events=raw.split(/\r?\n\r?\n/).flatMap(f=>{const s=f.split(/\r?\n/).filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');try{return[JSON.parse(s)]}catch{return[]}});
 const end=events.findLast(e=>['response.completed','response.incomplete','response.failed'].includes(e.type));
 const receipt={name,http_status:r.status,terminal:end?.type??null,status:end?.response?.status??null,input_count:body.input.length,reasoning_items:body.input.filter(i=>i.type==='reasoning').length,output:(end?.response?.output??[]).map(i=>({type:['reasoning','message','function_call'].includes(i.type)?i.type:'other',role:i.role==='assistant'?'assistant':null,content:(i.content??[]).map(c=>({type:['output_text','reasoning_text'].includes(c.type)?c.type:'other',text_length:typeof c.text==='string'?c.text.length:0}))})),output_tokens:end?.response?.usage?.output_tokens??null,reasoning_tokens:end?.response?.usage?.output_tokens_details?.reasoning_tokens??null,error_present:events.some(e=>e.error||e.response?.error),raw_exported:false};
 receipts.push(receipt);await writeFile('/evidence/paired-replay.json',JSON.stringify({same_request_except_reasoning_history:true,planned_provider_requests:2,automatic_retries:0,receipts},null,2));console.log(JSON.stringify(receipt));
 if(r.status!==200||!end)throw Error('Stop after ambiguous or failed response; no retry');
}
