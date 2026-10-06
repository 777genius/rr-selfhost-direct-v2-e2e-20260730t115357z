export const cases = [
  ...['responses', 'messages'].flatMap(protocol => ['before', 'after'].flatMap(placement => ['client', 'revoke', 'expiry'].map(trigger => ({
    id: `cancel-${protocol}-${placement}-${trigger}`, stage: 'cancel', protocol, placement, trigger,
    red: 'Default Sub2 usage drain keeps the upstream socket active beyond the immediate-abort deadline; tiny buffered frames previously misattributed cancellation.' })))),
  ...['responses', 'messages'].flatMap(protocol => ['uncertain-before', 'uncertain-after', 'tool-accepted', 'pending'].map(mode => ({
    id: `uncertainty-${protocol}-${mode}`, stage: 'uncertainty', protocol, mode,
    red: 'An accepted/reset request is automatically retried, or a cooling account prevents the fault reaching upstream and is falsely green.' }))),
  ...['responses', 'messages'].flatMap(protocol => [8, 32, 64].flatMap(mib => [1, 5, 20].map(streams => ({
    id: `memory-${protocol}-${mib}-${streams}`, stage: 'memory', protocol, mib, streams,
    red: 'Engine buffers an entire slow-consumer stream, exceeds the measured RSS envelope, duplicates effects, or does not return to quiescence.' })))),
  ...['responses', 'messages'].map(protocol => ({ id: `soak-${protocol}`, stage: 'soak', protocol, streams: 5, count: 250,
    red: 'Bounded synthetic soak loses terminals, duplicates upstream effects, or leaves active sockets.' }))
];
export const budget = { max_actual_upstream_attempts: 2000, soak_total: 500, memory_requests: 156, max_batch_ms: 90000,
  note: 'Automatic create probes and explicit healthy preparation requests count against the same global mock ceiling. No request retries in the client.' };
