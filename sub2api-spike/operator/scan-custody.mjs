// TRUSTED OPERATOR ONLY: inspect actual bytes, emit counts only, never hashes/bytes.
import { readFile, readdir, lstat, open, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
const manifest = JSON.parse(await readFile(process.argv[2], 'utf8'));
const required = ['filesystem', 'environment', 'process-config', 'logs', 'artifacts'];
if (!Array.isArray(manifest.keyFiles) || !manifest.keyFiles.length || !required.every(k => manifest.surfaces?.[k]?.length)) throw Error('Complete declared custody surfaces required');
const needles = [];
for (const path of manifest.keyFiles) { const bytes = Buffer.from((await readFile(path, 'utf8')).trim()); if (bytes.length < 8) throw Error('Invalid private key file'); needles.push(bytes, Buffer.from(bytes.toString('base64'))); }
let files = 0, hits = 0, unreadable = 0, bytesScanned = 0;
const overlap = Math.max(...needles.map(n => n.length)) - 1;
async function scan(path) {
  let info; try { info = await lstat(path); } catch { unreadable++; return; }
  if (info.isSymbolicLink()) { unreadable++; return; } // Explicit completeness failure; operator supplies resolved snapshot.
  if (info.isDirectory()) { for (const entry of await readdir(path)) await scan(join(path, entry)); return; }
  if (!info.isFile()) { unreadable++; return; }
  let handle; try {
    handle = await open(path, 'r'); let carry = Buffer.alloc(0), matched = false; const buffer = Buffer.alloc(65536);
    for (;;) { const { bytesRead } = await handle.read(buffer); if (!bytesRead) break; bytesScanned += bytesRead; const chunk = Buffer.concat([carry, buffer.subarray(0, bytesRead)]); if (needles.some(n => chunk.includes(n))) matched = true; carry = chunk.subarray(Math.max(0, chunk.length - overlap)); }
    files++; if (matched) hits++;
  } catch { unreadable++; } finally { await handle?.close(); }
}
for (const surface of required) for (const path of manifest.surfaces[surface]) await scan(path);
const result = { schema: 1, evidence_kind: 'real-Actions', id: 'D01', status: hits === 0 && unreadable === 0 && files > 0 ? 'PASS' : 'FAIL', files, matching_files: hits, unreadable, bytes_scanned: bytesScanned, declared_surfaces: required, limitation: 'Coverage depends on independently reviewed operator snapshot manifest, including full runner process/env/log/artifact capture; scanner alone cannot attest completeness.' };
await writeFile(process.argv[3], JSON.stringify(result, null, 2) + '\n'); if (result.status !== 'PASS') process.exitCode = 1;
