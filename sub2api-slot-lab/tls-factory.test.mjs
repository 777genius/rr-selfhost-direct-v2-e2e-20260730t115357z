import test from 'node:test';
import assert from 'node:assert/strict';
import https from 'node:https';
import { mkdtemp, rm } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
test('generated mock creates one native HTTPS server with the existing handler, without a listening socket',async()=>{
  const temp=await mkdtemp(resolve('sub2api-slot-lab/build/tls-'));
  const original=https.createServer;
  try {
    execFileSync('python3',['sub2api-slot-lab/prepare.py','--output',`${temp}/code`],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
    const {createMock}=await import(pathToFileURL(`${temp}/code/sub2api-regression-lab/mock.mjs`));
    const calls=[]; const server={};
    https.createServer=(options,handler)=>{ calls.push({options,handler});return server; };
    const tls={key:Buffer.from('inert'),cert:Buffer.from('inert'),minVersion:'TLSv1.2'};
    assert.equal(createMock({control_token:'x'.repeat(32),sentinels:{},tls}),server);
    assert.equal(calls.length,1); assert.equal(calls[0].options,tls);
    // Exercise original control authentication through the installed handler.
    const response={writeHead(status){this.status=status;},end(body){this.body=JSON.parse(body);}};
    await calls[0].handler({url:'/__lab/state',method:'GET',headers:{}},response);
    assert.equal(response.status,403); assert.equal(response.body.code,'CONTROL_DENIED');
    await calls[0].handler({url:'/__lab/state',method:'GET',headers:{'x-lab-control':'x'.repeat(32)}},response);
    assert.equal(response.status,200); assert.equal(response.body.effects,0);
    assert.equal(response.body.total,0);
  } finally {https.createServer=original; await rm(temp,{recursive:true,force:true});}
});
