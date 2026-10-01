// Trusted disposable diagnostic transport. Never mount private files in an agent.
import http from 'node:http';
import { readFile, writeFile, appendFile } from 'node:fs/promises';
import { StringDecoder } from 'node:string_decoder';
import { nativeErrorFilter } from '../native-errors.mjs';
const cfg = JSON.parse(await readFile('/private/tap.json', 'utf8'));
const master = (await readFile('/private/mimo.key', 'utf8')).trim();
let count = 0;
const allowedTypes = new Set(['response.created','response.in_progress','response.output_item.added','response.output_item.done','response.content_part.added','response.content_part.done','response.output_text.delta','response.output_text.done','response.function_call_arguments.delta','response.function_call_arguments.done','response.custom_tool_call_input.delta','response.custom_tool_call_input.done','response.reasoning_summary_text.delta','response.reasoning_summary_text.done','response.reasoning_text.delta','response.reasoning_text.done','response.completed','response.done','response.failed','response.incomplete','error']);
const numeric = n => Number.isSafeInteger(n) && n >= 0 ? n : null;
function item(i) { if (!i) return null; return {type:['message','reasoning','function_call','custom_tool_call','tool_search_call'].includes(i.type)?i.type:'other',role:['assistant','user'].includes(i.role)?i.role:null,phase:['final_answer','commentary'].includes(i.phase)?i.phase:null,status:['completed','in_progress','incomplete'].includes(i.status)?i.status:null,content:(i.content??[]).map(c=>({type:['output_text','refusal','reasoning_text'].includes(c.type)?c.type:'other',text_length:typeof c.text==='string'?c.text.length:0})),arguments_length:typeof i.arguments==='string'?i.arguments.length:0}; }
function observer(label, request) {
  let pending='',index=0;const decoder = new StringDecoder('utf8');
  return async chunk => {
    pending = (pending + decoder.write(Buffer.from(chunk))).replace(/\r\n/g,'\n');
    for(let p; (p=pending.indexOf('\n\n'))>=0;) {
      const frame=pending.slice(0,p);pending=pending.slice(p+2);
      const text=frame.split(/\r?\n/).filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n');
      if(!text || text==='[DONE]') continue;
      let e;try{e=JSON.parse(text)}catch{await appendFile('/evidence/trace.jsonl',JSON.stringify({request,label,index:index++,malformed:true})+'\n');continue;}
      const row={request,label,index:index++,type:allowedTypes.has(e.type)?e.type:'other',item:item(e.item),response_status:['completed','failed','incomplete','in_progress'].includes(e.response?.status)?e.response.status:null,delta_length:typeof e.delta==='string'?e.delta.length:0,text_length:typeof e.text==='string'?e.text.length:0,output:e.response?.output?.map(item),error_present:!!(e.error||e.response?.error),usage:e.response?.usage?{input_tokens:numeric(e.response.usage.input_tokens),output_tokens:numeric(e.response.usage.output_tokens),reasoning_tokens:numeric(e.response.usage.output_tokens_details?.reasoning_tokens)}:null};
      await appendFile('/evidence/trace.jsonl',JSON.stringify(row)+'\n');
    }
  };
}
// Full bodies stay root-only for exact deterministic replay, never public artifacts.
function server(port, upstream) {
  return http.createServer(async(req,res)=>{
    const id=++count;let body=[];
    try {
      if(req.method!=='POST'||!req.url.endsWith('/responses')){res.writeHead(404).end();return;}
      const auth=upstream?cfg.sentinel:cfg.capability;
      if(req.headers.authorization!==`Bearer ${auth}`){res.writeHead(401).end();return;}
      if(upstream && !(await readFile('/private/enabled','utf8').catch(()=>''))){res.writeHead(503).end();return;}
      for await(const c of req){body.push(c);if(body.reduce((a,b)=>a+b.length,0)>4*1024*1024)throw Error('body_limit');}
      body=Buffer.concat(body);const request=JSON.parse(body);
      await writeFile(`/private/request-${id}.json`,body,{mode:0o600});
      await appendFile('/evidence/requests.jsonl',JSON.stringify({request:id,hop:upstream?'provider':req.url.includes('/direct/')?'direct-client':'engine-client',model:request.model,input_count:request.input?.length,tools:(request.tools??[]).map(t=>({type:t.type,name:typeof t.name==='string'&&/^[a-zA-Z0-9_.-]{1,80}$/.test(t.name)?t.name:'other'})),max_output_tokens:request.max_output_tokens??null,reasoning:request.reasoning?{effort:['none','minimal','low','medium','high','xhigh'].includes(request.reasoning.effort)?request.reasoning.effort:null}:null})+'\n');
      const direct=upstream||req.url.includes('/direct/');
      const url=direct?'https://token-plan-sgp.xiaomimimo.com/v1/responses':'http://sub2api:8080/v1/responses';
      const headers={'content-type':'application/json',authorization:`Bearer ${direct?master:cfg.engineKey}`};
      // Preserve observed agent headers for engine classifiers. No arbitrary target/query/redirect.
      for(const h of ['user-agent','originator','version','openai-beta','session_id','x-codex-turn-metadata'])if(req.headers[h])headers[h]=req.headers[h];
      const response=await fetch(url,{method:'POST',headers,body,redirect:'error',signal:AbortSignal.timeout(180000)});
      res.writeHead(response.status,{'content-type':response.headers.get('content-type')??'application/json'});
      const rawObserver=observer(upstream?'provider-upstream':direct?'direct-upstream':'engine-upstream',id);
      const downstreamObserver=observer(upstream?'provider-to-engine':direct?'direct-to-client':'filtered-to-client',id);
      const filter=upstream?null:nativeErrorFilter();
      let chain=Promise.resolve();
      if(filter){filter.on('data',c=>{res.write(c);chain=chain.then(()=>downstreamObserver(c));});filter.on('error',()=>res.destroy());}
      let raw=[];
      for await(const chunk of response.body){raw.push(chunk);await rawObserver(chunk);if(filter)filter.write(chunk);else{res.write(chunk);await downstreamObserver(chunk);}}
      await writeFile(`/private/response-${id}.sse`,Buffer.concat(raw),{mode:0o600});
      if(filter){filter.end();await new Promise(r=>filter.on('end',r));await chain;}
      res.end();await appendFile('/evidence/http.jsonl',JSON.stringify({request:id,status:response.status,bytes:raw.reduce((a,b)=>a+b.length,0),finished:true})+'\n');
    }catch{res.destroy();await appendFile('/evidence/http.jsonl',JSON.stringify({request:id,failed:true})+'\n');}
  }).listen(port,'0.0.0.0');
}
server(8790,true);server(8787,false);
