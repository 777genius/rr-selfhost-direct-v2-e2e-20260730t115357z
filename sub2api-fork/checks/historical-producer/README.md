# Native compatible Responses reasoning

This bounded patch adds the trusted account boolean
`extra.openai_preserve_compatible_reasoning=true`. It is effective only for
`platform=openai`, `type=apikey`, with a native Responses upstream route.
Missing, false, or non-boolean values retain the original behavior. OAuth and
setup-token accounts ignore it. A caller's body or headers cannot enable it.
Do not enable it on ordinary OpenAI accounts; configure only compatible
providers that require their own reasoning history.

For an existing compatible account, merge this field into its existing admin
Extra metadata (do not replace other fields):

```json
{"openai_preserve_compatible_reasoning": true}
```

The patch preserves native reasoning items, content, IDs, references and opaque
extensions for both HTTP and WS request preparation. Encrypted reasoning is
also passed through intact as provider-owned opaque history: no ciphertext
conversion, OpenAI ID removal, or synthetic summary insertion on this policy.
Other input items retain the original ID/call-ID sanitation and tool pairing.
Malformed JSON and non-object opt-in replay requests are rejected. Provider
validation of semantic item shapes remains authoritative. Native response
stream handling is unchanged.

`SOURCE.json` records the requested v0.2.11 revision, original touched-file
hashes, patched hashes and patch hash. The staged source has no Git provenance;
its server VERSION file says `0.2.10`. The coordinator must verify the recorded
original checksums against `96f4c115c9749078f90cbf210a01d39baf3f53b6`
before building the immutable image. The patch contains four production files
and one focused backend test file, 325 changed lines, with repo-relative headers.
Editable source stays under the inherited ignored `build-source/` rule, without
a nested `.git`.

Apply from an exact, disposable upstream checkout:

```sh
patch --batch --fuzz=0 -p1 < /absolute/path/sub2api-fork/patches/native-reasoning.patch
```

Offline test commands in this workspace:

```sh
./sub2api-fork/checks/run-backend-tests.py --baseline
./sub2api-fork/checks/run-backend-tests.py
```

The baseline command uses untouched staged production files with the new tests;
it succeeds only on observed behavioral failures. The patched command runs new
HTTP forwarding/WS preparation contracts plus existing normalizer and sanitizer
coverage. Both prohibit dependency/toolchain downloads and return 77 for missing
Go/dependencies. Go and gofmt are unavailable here: behavioral red/green and
formatting checks are **NOT RUN**. Zero-fuzz application, exact hashes and reverse
application passed; see `checks/artifact-verification.json`.

Rollback: set the Extra boolean to false or remove it to restore legacy request
normalization. To remove the patch, restore the original immutable engine image,
or reverse it with `patch --batch --fuzz=0 -R -p1` on an exact disposable tree.
Start a fresh conversation after changing the policy so already altered history
is not reused. No libraries, credentials, provider impersonation or model
switches were added. Genuine thinking-enabled E2E, image build, independent review
and live regression runs remain coordinator checks.
