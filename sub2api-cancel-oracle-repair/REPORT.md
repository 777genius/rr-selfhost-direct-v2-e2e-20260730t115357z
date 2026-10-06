Cancellation oracle repair is ready as a three-module delta. All changes and evidence are confined to `sub2api-cancel-oracle-repair/`; no complete runtime is packaged.

The six reviewed R7b receipts on image `c656447c1b79706e67f71fe49ada0f0f840e26eba798597e6751917ddc691bd1`, binary `5e28306e531eac0abea49811f116dbbddb233c4e52ce3f7d63f9c71d949632fd`, actually contain **five FAIL and one PASS**. Every scenario has one effect, an incomplete physical close, and no upstream terminal/release/reset. The canonical response-close lower bound explains the five failures:

| Scenario | Recorded | Physical close minus broker response close (ms) | Downstream |
|---|---|---:|---|
| Responses before revoke | FAIL | -1.292 | 502, normal HTTP end, no SSE terminal |
| Messages before revoke | PASS | +0.134 | 502, normal HTTP end, no SSE terminal |
| Responses after revoke | FAIL | -2.803 | 200, aborted, no terminal |
| Messages after revoke | FAIL | -0.568 | 200, aborted, no terminal |
| Responses after expiry | FAIL | -2.021 | 200, aborted, no terminal |
| Messages after expiry | FAIL | -0.851 | 200, aborted, no terminal |

Expiry closes occur 2879.385/2941.371ms after setup action; setup cannot anchor expiry cancellation. Full numeric/source audit: `actual-row-audit.json`. Historical rows lack pre-abort observations and remain unchanged; none is promoted to PASS.

`broker.mjs` adds an optional monotonic observation immediately before the first actual controller abort, identifying protocol, dispatch, and cause. Both capability and request expiry timers are distinguished from timeout, downstream close, and cleanup. `run.mjs` records the events: revoke uses action-request time for the deadline, expiry uses its actual pre-abort trigger, and client uses its existing cancellation timestamp. Response-close remains independent of physical-close ordering. The source clock must reach the same 1250ms observation horizon, including when a timer returns early. The ten-second hold stays intact; cancellation performs no manual release/reset.

`receipts.mjs` requires physical incomplete close **after the causal pre-abort boundary and within 1250ms of real cancellation**, identical immediate/final close evidence, one dispatch/effect, bound identity and clock, healthy/early acknowledgments >4KiB, and unsent terminals. It rejects close before request/abort, late/missing/foreign close, terminal or completed output, manual/safety reset, release, and duplicate dispatch. The canonical predicate said 1200ms while its runner observed at 1250ms; the repaired predicate enforces the requested **1250ms**, without changing that deadline or adding grace.

Exact delta SHA-256: `3f19e308f6e1f3881a1534981893b420eadb3a06a694c44bf03ce380ae0eca59`. `source-ledger.json` records each canonical, policy-input, and output SHA, all preserved runtime pins, and the exact trusted boolean fixture-policy SHA `6a70040c047f3e72005f6c1cec6b8404457e4de23b9ca36a5231023ccec4dc8a`. Composition is canonical → exact fixture policy → repair delta. Preparation checks all 111 frozen inputs and generates only the three changed files into a new overlay directory:

```sh
python3 sub2api-cancel-oracle-repair/prepare.py --stage sub2api-cancel-oracle-repair/generated-overlay
PYTHONDONTWRITEBYTECODE=1 python3 sub2api-cancel-oracle-repair/verify.py
```

Identical focused tests: **old RED: 55 failures/90; new GREEN: 90/90**, zero skips/cancellations, Node v24.21.0. `verification.json` records matching test hashes; `evidence/old.tap` and `evidence/new.tap` retain results. Broker/runner tests execute exact source in virtual IO with native AbortController and controlled clocks/timers; no network, external identity/key/auth action, provider, Go, Docker, production-source, GC/RSS, or Git write occurs. Uncertainty, telemetry, load/main runner, wire/client/mock/plan/adapter remain preserved.

Offline handoff has no blocker. Root must rerun exact actual scenarios against the reviewed image; actual E2E is **NOT RUN** here. Physical socket-close evidence does **not** prove a Go Body.Close invocation. Missing historical causal timestamps cannot be reconstructed. STOP.
