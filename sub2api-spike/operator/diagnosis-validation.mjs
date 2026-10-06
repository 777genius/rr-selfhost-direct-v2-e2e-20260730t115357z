import {readFile,writeFile} from 'node:fs/promises';
import {financialEvidence,parseFindingDocument} from '/checkout/sub2api-spike/evidence.mjs';
import {execFileSync} from 'node:child_process';
const receipts=[];
for(const mode of ['engine','direct','engine-none']){
 const home='/client/home-'+mode;
 const raw=await readFile(home+'/events.jsonl','utf8').catch(()=>null);if(raw===null)continue;
 const events=raw.split('\n').flatMap(l=>{try{return[JSON.parse(l)]}catch{return[]}});
 const review=await readFile(home+'/review.txt','utf8').catch(()=>'');
 const receipt={mode,valid_finding:false,financial_contract:false,numeric_tool_reproduction:false,independent_numeric_reproduction:false,raw_exported:false};
 try{
  financialEvidence('codex',events,review,'mimo');receipt.financial_contract=true;
  const f=parseFindingDocument(review).findings.find(f=>f.file==='wallet.mjs'&&f.function==='withdraw'&&f.example?.amount<0);
  const n=f.example;receipt.valid_finding=true;
  const repro=JSON.parse(execFileSync('node',['--input-type=module','-e',`import {withdraw} from '/opt/rr-gateway-spike-fixture/wallet.mjs';const a={balance:${n.initial_balance}};withdraw(a,${n.amount});console.log(JSON.stringify({final_balance:a.balance}))`],{encoding:'utf8'}));
  receipt.independent_numeric_reproduction=repro.final_balance===n.final_balance;
  receipt.numeric_tool_reproduction=events.some(e=>{const i=e.item;if(e.type!=='item.completed'||i?.type!=='command_execution'||i.exit_code!==0)return false;try{const o=JSON.parse(i.aggregated_output.trim());return ['initial_balance','amount','final_balance'].every(k=>Number.isFinite(o[k])&&o[k]===n[k])}catch{return false}});
 }catch{}
 receipt.result=Object.entries(receipt).filter(([k])=>['valid_finding','financial_contract','numeric_tool_reproduction','independent_numeric_reproduction'].includes(k)).every(([,v])=>v)?'PASS':'FAIL';
 receipts.push(receipt);
}
await writeFile('/evidence/client-validation.json',JSON.stringify(receipts,null,2));console.log(JSON.stringify(receipts));
