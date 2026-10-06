Before writing tests, these are the observable defects each contract will make red:

- A cryptographically invalid or wrongly scoped/time-bound GitHub JWT receives a grant or causes an admin POST. Signed mutations and a separate forgery key exercise the verifier boundary using injected JWKS/time; HTTP verifies denial before effects.
- A runner can reach admin, another protocol, model or caller-selected routing; or caller authorization overrides the scoped virtual key. Real HTTP servers inspect gateway requests and return different behavior for a wrong virtual key.
- Identical concurrent grants mint multiple keys; expiry, revoke or restart creates a fresh key for a consumed scope. Count actual admin HTTP effects and attempt inference after closure.
- A third simultaneous inference, a 33rd request or oversized body reaches inference. Hold real streams open, count dispatches, and reject at the HTTP boundary.
- Responses tool-call/failure and Messages tool-use SSE bytes are altered, error statuses become success, or truncation is silently accepted. Compare complete stream bytes/status and observe interrupted reads.
- Canceling the runner leaves upstream generation active. Observe upstream connection closure, without manually stopping the upstream until after the assertion.

These are boundary/transport contracts, not source snapshots or tests of mocked method calls. The intentionally defective wallet is review input, not a passing implementation.

Evidence normalization: a review claiming the finding without successful wallet-source tool output, an incomplete tool command, or a terminal error must fail. Safe evidence must contain only normalized fixed vocabulary, even if the transcript/review contains arbitrary sensitive-looking text. Synthetic client event records exercise the parser contract; they are not live agent proof.

Chunked body limit: an oversized JSON upload without Content-Length must be rejected before inference, not merely checked by its declared length. Startup must reject TTL > 15 minutes and provider credential fields before any network activity.

Continuation audit defects: grants with array-valued provider/protocol must fail before admin creation; separate capabilities for the same run/attempt must share the 32-request and two-concurrent limits. A blocked downstream write must close on expiry/timeout/revoke rather than permanently occupy a concurrency slot. After broker restart, previously observed runs deny even new scopes so aggregate counters cannot reset.
