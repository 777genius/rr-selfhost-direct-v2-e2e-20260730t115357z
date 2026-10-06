import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const here=dirname(fileURLToPath(import.meta.url)), root=dirname(here);
const packageRoot=resolve(root,'.spike-inputs/candidate');
test('offline CLI reconstructs all 103 frozen hashes and unchanged --plan',async()=>{
 const temp=await mkdtemp(resolve(tmpdir(),'transport-packaging-'));
 try {
  const output=resolve(temp,'runtime');
  const result=spawnSync('python3',[resolve(here,'prepare-standalone.py'),'--base-root',resolve(root,'.spike-inputs/public-base'),'--package-root',packageRoot,'--output',output,'--plan'],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  assert.deepEqual(JSON.parse(result.stdout),JSON.parse(await readFile(resolve(packageRoot,'evidence/standalone-plan.json'),'utf8')));
  const ledger=JSON.parse(await readFile(resolve(here,'runtime-hashes.json'),'utf8'));
  assert.equal(Object.keys(ledger).length,103);
  for(const [path,hash] of Object.entries(ledger)) assert.equal(createHash('sha256').update(await readFile(resolve(output,path))).digest('hex'),hash,path);
  const again=spawnSync('python3',[resolve(here,'prepare-standalone.py'),'--base-root',resolve(root,'.spike-inputs/public-base'),'--package-root',packageRoot,'--output',output],{encoding:'utf8'});
  assert.notEqual(again.status,0); assert.match(again.stderr,/output already exists/);
 }finally{await rm(temp,{recursive:true,force:true});}
});
test('wrong/missing base fails before creating runtime',async()=>{
 const temp=await mkdtemp(resolve(tmpdir(),'transport-packaging-red-'));
 try{
  const output=resolve(temp,'runtime');
  const result=spawnSync('python3',[resolve(here,'prepare-standalone.py'),'--base-root',temp,'--package-root',packageRoot,'--output',output],{encoding:'utf8'});
  assert.notEqual(result.status,0); assert.match(result.stderr,/missing file/);
  assert.deepEqual(await readdir(temp),[]);
 }finally{await rm(temp,{recursive:true,force:true});}
});
