# Coordinator integration only (caller files unchanged)

Install/seal `granted-run.mjs` with the trusted harness modules. Import from the fixed installed path in the privileged harness; never execute a checkout-supplied module. Immediately after successful grant JSON parsing, before version/agent execution where applicable:

```js
import { bindGrantedRun } from './granted-run.mjs';
const granted = await grant.json();
const identity = bindGrantedRun(granted, {
  runID: runtime.run_id,
  attempt: runtime.run_attempt,
  workflowSHA: runtime.workflow_sha,
  provider, agent,
});
const { capability, model } = granted;
// Retain existing capability/model validation and private child environment setup.
// Any binding error aborts before launching the agent; never emit a success receipt.
```

Here `runtime` is the parsed normalized launcher input. The current workspace's older environment-based caller should map GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT/GITHUB_SHA to the same fields; do not silently coerce numbers or fill missing metadata from the grant. Agent/provider are the validated runtime selections, not values copied from the grant. Preserve existing native terminal, actual source/rules tool reads, numeric financial finding and independent reproduction assertions. After those assertions succeed, build the normalized receipt using only the returned identity for authorization fields:

```js
const receipt = {
  ...existingVerifiedFinancialEvidence,
  run_id: identity.runID, run_attempt: identity.attempt,
  workflow_sha: identity.workflowSHA, provider: identity.provider,
  transport: identity.protocol, agent,
};
// Retain existing positive evidence flags/version fields, never include granted,
// capability, OIDC, private keys, raw events or a fabricated answer.
```

Before uploading the receipt, workflow validation must compare with trusted job values (set via env, not shell interpolation of inputs):

```js
const expectedProtocol = process.env.SPIKE_AGENT === 'codex' ? 'responses'
  : process.env.SPIKE_AGENT === 'claude' && process.env.SPIKE_PROVIDER === 'mimo' ? 'messages' : undefined;
if (!expectedProtocol || !['mimo', 'openrouter'].includes(process.env.SPIKE_PROVIDER) ||
    receipt.run_id !== process.env.GITHUB_RUN_ID ||
    receipt.run_attempt !== process.env.GITHUB_RUN_ATTEMPT ||
    receipt.workflow_sha !== process.env.GITHUB_SHA ||
    receipt.provider !== process.env.SPIKE_PROVIDER ||
    receipt.agent !== process.env.SPIKE_AGENT ||
    receipt.transport !== expectedProtocol) throw Error('Receipt identity denied');
// Also retain all existing positive financial/native evidence assertions.
```

Do not authorize external E2E from unit results. Coordinator runs the full socket suite in its pinned Node24 disposable environment and owns caller/workflow integration and sealed manifest updates.
