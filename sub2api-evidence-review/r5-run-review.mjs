import {readFile,writeFile,readdir,stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root=resolve('.'), out=resolve('sub2api-evidence-review');
const hash=b=>createHash('sha256').update(b).digest('hex');
const manifest=JSON.parse(await readFile('.spike-inputs/INPUT-HASHES.json'));
const audit=[];
for(const [path,expected] of Object.entries(manifest)){const bytes=await readFile('.spike-inputs/'+path);audit.push({path,expected,actual:hash(bytes),matches:hash(bytes)===expected});}
const prior={};for(const f of await readdir(out))if(!f.startsWith('r5-')&&!f.startsWith('R5-'))prior[f]=hash(await readFile(out+'/'+f));
await writeFile(out+'/r5-input-hashes.json',JSON.stringify({manifest_sha256:hash(await readFile('.spike-inputs/INPUT-HASHES.json')),entries:audit,prior_artifacts:prior},null,2));
const testPath='.spike-inputs/candidate/sub2api-evidence-r2/client-contract.test.mjs';
const testURL=pathToFileURL(resolve(testPath)).href;
const text=await readFile(testPath,'utf8');
for(const mode of ['green','red']){
 let copy=text.replaceAll(', import.meta.url)',', reviewTestURL)').replace("resolve('sub2api-evidence-r2/selected-source-')","resolve('sub2api-evidence-review/r5-selected-source-')");
 copy=`const reviewTestURL=${JSON.stringify(testURL)};\n`+copy;
 if(mode==='red')copy=copy.replaceAll("'../sub2api-spike/", "'../../../sub2api-spike/").replaceAll('`../sub2api-spike/','`../../../sub2api-spike/');
 await writeFile(out+`/r5-${mode}-contract.test.mjs`,copy);
}
const results=[];
function run(name,args,env={}){const r=spawnSync(process.execPath,args,{env:{...process.env,...env},encoding:'utf8',timeout:90000});writeFile(out+'/'+name+'.tap',r.stdout+(r.stderr?'\n'+r.stderr:''));const lines=r.stdout.split('\n').filter(l=>/^# (tests|pass|fail|skipped)/.test(l));results.push({name,args,env,exit:r.status,signal:r.signal,summary:lines});console.log(name,r.status,lines.join('; '));}
for(const mode of ['green','red'])run('r5-'+mode,['--test','--test-reporter=tap','.spike-inputs/candidate/sub2api-spike/evidence.test.mjs','.spike-inputs/candidate/sub2api-spike/run-client.test.mjs',out+`/r5-${mode}-contract.test.mjs`],{CONSUMER_WORKFLOW_SOURCE:resolve('.github/workflows/sub2api-gateway-spike.yml')});
run('r5-grant',['--test','--test-reporter=tap','.spike-inputs/candidate/sub2api-spike/granted-run.test.mjs']);
for(const file of ['.spike-inputs/candidate/sub2api-spike/run-client.mjs',testPath,'.spike-inputs/candidate/sub2api-spike/evidence.mjs'])run('r5-syntax-'+results.length,['--check',file]);
await writeFile(out+'/r5-command-results.json',JSON.stringify({node:process.version,results},null,2));
console.log('manifest',audit.length,'mismatch',audit.filter(x=>!x.matches).length);
