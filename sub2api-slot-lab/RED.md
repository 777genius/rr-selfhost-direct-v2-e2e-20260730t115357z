# Red contract (written before harness implementation)

These are intended failures, not observed product failures. No product changes are owned by this package.

* Pending second request reaches the real user or account wait counter, then cancellation leaves that counter nonzero, loses the active first request's lease, retains the pending user/API-key lease, or dispatches the pending request to the provider.
* Accepted first request with trusted persisted account Extra `native_api_key_cancel_on_disconnect: true` keeps the provider response body open or real Redis request leases after downstream disconnect beyond 1250 ms, including all observation overhead.
* Healthy third request cannot recover through the same native endpoint and custodied API key, fails its SSE protocol terminal, or dispatches/effects more than once.
* A canceled request produces a late dispatch/effect, a safety reset masquerades as body closure, or final owned user/account/API-key slots or wait counters are nonzero.

The default negative control omits the trusted opt-in. It must keep the accepted provider stream open through a 1250 ms observation interval and drain normally after explicit release. It has no 1250 ms body/lease release requirement. Failure to enter the requested real handler queue is a failed admission gate, never a passing test or a transport-slot substitute.
