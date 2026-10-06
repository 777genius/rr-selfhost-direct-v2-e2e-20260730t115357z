# Trusted HTTPS slot lab handoff

ROOTGATES PENDING. Worker performed offline Node/Python verification only. No Docker, Go, root driver, OpenSSL, network, provider credentials, Git writes, or certificate/key reads were performed.

Exact W5 candidate copied from `.spike-inputs/candidate/sub2api-slot-lab/`; only existing `prepare.py`, `root-driver.py`, and `run.mjs` changed. Historical shared mock, canonical helper, build pins, and original 34 Node / 16 Python tests remain byte-identical. The owned preparation delta makes the generated existing mock use native Node HTTPS with its same handler and existing request socket observer. There is one server, no proxy or sidecar. Engine incoming URL stays HTTP. Provider and control URL is exactly `https://mock:8099`.

Root main now generates one disposable CA and server certificate between preparation and launch. Commands are frozen in `w6-evidence/certificate-commands.json`; server extensions are in `tls-server.ext`. Root runtime requires installed OpenSSL. CA constraints, DNS:mock SAN, serverAuth, and CA:FALSE server constraints are explicit. Root-owned TLS directory is 0700; umask 077 and final file modes 0600. Generated material never enters evidence or hashes. Mock reads server key/cert from `/private/tls/`; Go receives only a readonly CA certificate file mount with SSL_CERT_FILE. Node mock/operator startup receives NODE_EXTRA_CA_CERTS for the same CA using unchanged private mounts.

Enabled upstream host allowlist remains exactly ['mock']; sandbox private hosts stay enabled; allow_insecure_http is false. W5 stdout=true/file=false, Docker logs none, 2 MiB body/text caps, final PG postmaster plus target DB readiness, native entrypoint, root UID, ALL capability drop, custody checks and native binary pins are retained.

Verification: 35 Node tests (original 34 plus an injected HTTPS factory/handler contract), 18 Python tests (original 16 plus private generation and emitted HTTPS policy contracts). Transport fixtures relocate frozen input paths and retain the previous readiness stub. New readonly CA mount and Node startup trust are independently asserted before normalization for the original launch equality test. No offline test proves a real TLS handshake. Exact patch, public input/output hashes, frozen generated payload, and test transcripts accompany this report.

## Controller root gates required before completion

1. Use the same pinned native image c656447c… and binary 5e28306e…; retain all native/source/config binding checks. Run certificate commands only in the new root-owned private run. Do not export certificate/key values or hashes.
2. Before the accepted matrix, run an isolated wrong-CA native dispatch negative gate. Record actual TLS trust failure with zero provider requests/effects and zero Redis leases; preserve failure evidence before cleanup. A second unrelated CA may be used only for this negative trust gate, never as the disposable lab provider CA. Do not weaken hostname, allowlist or TLS verification.
3. Start correct-CA native execution using the same image. No extra accepted health/probe/provider call: prove correct TLS trust through the existing first matrix row. Prove no HTTP fallback and actual request socket closure under native HTTPS cancellation.
4. Execute all 84 rows (80 opt-in, 4 default), exactly 168 effects and 248 provider requests, 1250 ms cancellation/release limits, strict native SSE, authenticated Redis observer, recovery/failure evidence before cleanup, final-zero and owned cleanup gates. Retain enabled allowlist. No public ports, real provider keys, product source changes, auth-home mounts, extra effects, or transport bypasses.

All four root gates are pending. The broader goal remains active; the worker stops here for controller integration and actual verification.
