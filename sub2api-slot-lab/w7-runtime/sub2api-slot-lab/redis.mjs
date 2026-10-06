import net from 'node:net';
import { mono, requireFact, ownedKeys, snapshotShape } from './contracts.mjs';

export function encode(parts) {
  return Buffer.concat([Buffer.from(`*${parts.length}\r\n`), ...parts.flatMap(p => {
    const b = Buffer.from(String(p)); return [Buffer.from(`$${b.length}\r\n`), b, Buffer.from('\r\n')];
  })]);
}
// Incremental RESP2 parser; errors never expose Redis text or credentials.
export function decode(buffer, start = 0) {
  const end = buffer.indexOf('\r\n', start); if (end < 0) return null;
  const kind = String.fromCharCode(buffer[start]), value = buffer.toString('utf8', start + 1, end);
  let offset = end + 2;
  if (kind === '-') throw Object.assign(Error('REDIS_REJECTED'), { code: 'REDIS_REJECTED' });
  if (kind === '+') return { value, offset };
  if (kind === ':') { requireFact(/^-?\d+$/.test(value), 'RESP_INTEGER'); return { value: Number(value), offset }; }
  requireFact(['$', '*'].includes(kind) && /^-?\d+$/.test(value), 'RESP_FORMAT');
  const n = Number(value); requireFact(n >= -1 && n <= 65536, 'RESP_SIZE');
  if (n === -1) return { value: null, offset };
  if (kind === '$') {
    if (buffer.length < offset + n + 2) return null;
    requireFact(buffer.toString('ascii', offset + n, offset + n + 2) === '\r\n', 'RESP_TERMINATOR');
    return { value: buffer.toString('utf8', offset, offset + n), offset: offset + n + 2 };
  }
  const list = [];
  for (let i = 0; i < n; i++) {
    const item = decode(buffer, offset); if (!item) return null;
    list.push(item.value); offset = item.offset;
  }
  return { value: list, offset };
}
export class RedisObserver {
  constructor(password) { requireFact(/^[a-f0-9]{64}$/.test(password), 'PRIVATE_REDIS_AUTH'); this.password = password; }
  async transaction(commands, deadline) {
    requireFact(mono() < deadline, 'REDIS_DEADLINE');
    // New bounded observation connection; no lease mutations, cleanup or SCAN.
    return new Promise((resolve, reject) => {
      const socket = net.createConnection({ host: 'redis', port: 6379 });
      let buffer = Buffer.alloc(0), replies = [], settled = false;
      const finish = (error, value) => { if (settled) return; settled = true; clearTimeout(timer); socket.destroy(); error ? reject(error) : resolve(value); };
      const fail = code => finish(Object.assign(Error(code), { code }));
      const timer = setTimeout(() => fail('REDIS_DEADLINE'), Math.max(1, Math.floor(deadline - mono())));
      socket.once('connect', () => socket.write(Buffer.concat([
        encode(['AUTH', this.password]), encode(['MULTI']), ...commands.map(encode), encode(['EXEC'])
      ])));
      socket.on('data', bytes => {
        try {
          buffer = Buffer.concat([buffer, bytes]); requireFact(buffer.length <= 262144, 'REDIS_REPLY_LIMIT');
          while (buffer.length) { const item = decode(buffer); if (!item) break; replies.push(item.value); buffer = buffer.subarray(item.offset); }
          if (replies.length === commands.length + 3) {
            requireFact(replies[0] === 'OK' && replies[1] === 'OK' && replies.slice(2, -1).every(x => x === 'QUEUED'), 'REDIS_TRANSACTION');
            finish(null, replies.at(-1));
          }
        } catch (e) { finish(e); }
      });
      socket.once('error', () => fail('REDIS_TRANSPORT'));
      socket.once('end', () => { if (!settled) fail('REDIS_TRUNCATED'); });
    });
  }
  async snapshot(ids, deadline) {
    const keys = ownedKeys(ids), commands = [], started_ms = mono();
    for (const k of ['user', 'account', 'key']) commands.push(['ZCARD', keys[k]], ['ZRANGE', keys[k], '0', '-1'], ['PTTL', keys[k]]);
    for (const k of ['userWait', 'accountWait']) commands.push(['GET', keys[k]], ['PTTL', keys[k]]);
    const values = await this.transaction(commands, deadline), s = { keys, started_ms, observed_ms: mono() };
    let index = 0;
    for (const k of ['user', 'account', 'key']) s[k] = { count: values[index++], members: values[index++], ttl_ms: values[index++] };
    for (const k of ['userWait', 'accountWait']) {
      const raw = values[index++]; requireFact(raw === null || /^(0|[1-9]\d*)$/.test(raw), 'WAIT_COUNTER_INVALID');
      s[k] = { raw, count: raw === null ? 0 : Number(raw), ttl_ms: values[index++] };
    }
    // Keep real leak counts / expiring TTLs observable. Admission and recovery
    // assertions run after the runner has journaled the complete observation.
    requireFact(values.length === 13, 'SNAPSHOT_INVENTORY'); return snapshotShape(s);
  }
}
