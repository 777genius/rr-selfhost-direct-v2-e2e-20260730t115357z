import { open, mkdir, readFile, rename } from 'node:fs/promises';
import { dirname } from 'node:path';
export const fault = (status, code) => Object.assign(Error(code), { status, code });
export const serial = () => { let tail = Promise.resolve(); return fn => { const p = tail.then(fn); tail = p.catch(() => {}); return p; }; };
export async function atomicJSON(path, value) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temp = `${path}.new`; const h = await open(temp, 'w', 0o600);
  try { await h.writeFile(JSON.stringify(value)); await h.sync(); } finally { await h.close(); }
  await rename(temp, path); const d = await open(dirname(path), 'r'); try { await d.sync(); } finally { await d.close(); }
}
export async function loadJSON(path, fallback) { try { return JSON.parse(await readFile(path, 'utf8')); } catch (e) { if (e.code === 'ENOENT') return fallback; throw e; } }
export async function readJSON(req, limit = 2 * 1024 * 1024) {
  let size = 0; const chunks = [];
  for await (const b of req.iterator({ destroyOnReturn: false })) { size += b.length; if (size > limit) { req.resume(); throw fault(413, 'body_limit'); } chunks.push(b); }
  try { const x = JSON.parse(Buffer.concat(chunks)); if (!x || typeof x !== 'object' || Array.isArray(x)) throw Error(); return x; } catch { throw fault(400, 'invalid_json'); }
}
export function send(res, status, body) { if (res.destroyed) return; res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' }); res.end(JSON.stringify(body)); }
export function bearer(req) { const h = req.headers.authorization; if (typeof h !== 'string' || !/^Bearer [A-Za-z0-9_.-]+$/.test(h)) throw fault(401, 'unauthorized'); return h.slice(7); }
export async function listen(server) { await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); }); return `http://127.0.0.1:${server.address().port}`; }
export async function stop(server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
