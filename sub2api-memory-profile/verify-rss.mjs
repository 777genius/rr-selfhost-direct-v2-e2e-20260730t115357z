// Independent full adapter replay of the actual kernel observations.
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const [root,id]=process.argv.slice(2);
assert.match(id,/^memory-(responses|messages)-8-(1|5|20)-b\d{2}$/);
const json=async name=>JSON.parse(await readFile(resolve(root,name),'utf8'));
const {telemetryVerdict}=await import(pathToFileURL(resolve(root,'stage/code/sub2api-transport-r4/adapter.mjs')));
const row=await json(`evidence/${id}.json`),ready=await json(`telemetry/${id}.ready.json`),done=await json(`telemetry/${id}.done.json`);
const text=await readFile(resolve(root,`telemetry/${id}.ndjson`),'utf8');assert.ok(text.endsWith('\n'));
const samples=text.trimEnd().split('\n').map(JSON.parse);
const verdict=telemetryVerdict(samples,{...row.telemetry_boundary,ended_ms:done.ended_ms},ready,{done});
assert.deepEqual(verdict,row.memory_envelope);
assert.ok(['PASS','FAIL'].includes(verdict.empirical_qualified_status));
assert.equal(verdict.physical_interval_rss_status,'NOTPROVEN');
