import { Transform } from 'node:stream';

// No protocol conversion: healthy SSE frames retain their original bytes.
// Failed events expose a fixed diagnostic, never upstream error bodies.
export function nativeErrorFilter(maxFrameBytes = 2 * 1024 * 1024) {
  let pending = Buffer.alloc(0);
  const decoder = new TextDecoder('utf-8', { fatal: true });
  function frame(raw) {
    const text = decoder.decode(raw);
    const data = text.split(/\r?\n/).filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n');
    if (!data || data === '[DONE]') return raw;
    const event = JSON.parse(data);
    if (!['error', 'response.error', 'response.failed', 'response.incomplete'].includes(event.type) && !event.error && !event.response?.error && !['failed', 'incomplete'].includes(event.response?.status)) return raw;
    const error = { type: 'api_error', code: 'upstream_failure', message: 'Upstream request failed' };
    const safe = event.type?.startsWith('response.')
      ? { type: 'response.failed', sequence_number: Number.isSafeInteger(event.sequence_number) ? event.sequence_number : 0, response: { id: 'gateway_failed', object: 'response', status: 'failed', output: [], error } }
      : { type: 'error', error: { type: 'api_error', message: error.message } };
    return Buffer.from(`event: ${safe.type}\ndata: ${JSON.stringify(safe)}\n\n`);
  }
  return new Transform({
    transform(chunk, _encoding, callback) {
      try {
        pending = Buffer.concat([pending, chunk]);
        while (true) {
          const lf = pending.indexOf('\n\n'), crlf = pending.indexOf('\r\n\r\n');
          const index = lf < 0 ? crlf : crlf < 0 ? lf : Math.min(lf, crlf);
          if (index < 0) break;
          const end = index + (index === crlf ? 4 : 2);
          if (end > maxFrameBytes) throw Error('Upstream frame limit');
          this.push(frame(pending.subarray(0, end))); pending = pending.subarray(end);
        }
        if (pending.length > maxFrameBytes) throw Error('Upstream frame limit');
        callback();
      } catch { callback(Error('Invalid upstream stream')); }
    },
    flush(callback) { callback(pending.length ? Error('Incomplete upstream frame') : undefined); }
  });
}
