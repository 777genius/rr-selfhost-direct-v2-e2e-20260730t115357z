// Grant is a trusted broker response; runtime is the launcher selection/metadata.
// Call immediately after parsing the grant, before any agent execution.
export function bindGrantedRun(grant, runtime) {
  const valid = x => x && typeof x.runID === 'string' && /^[1-9]\d*$/.test(x.runID) &&
    typeof x.attempt === 'string' && /^[1-9]\d*$/.test(x.attempt) &&
    typeof x.workflowSHA === 'string' && /^[a-f0-9]{40}$/.test(x.workflowSHA);
  if (!valid(grant) || !valid(runtime)) throw Error('Granted run identity denied');
  const protocol = runtime.agent === 'codex' ? 'responses' : runtime.agent === 'claude' && runtime.provider === 'mimo' ? 'messages' : undefined;
  if (!protocol || !['mimo', 'openrouter'].includes(runtime.provider) || grant.protocol !== protocol ||
    ['runID', 'attempt', 'workflowSHA', 'provider'].some(k => grant[k] !== runtime[k])) throw Error('Granted run identity denied');
  return Object.freeze({ runID: grant.runID, attempt: grant.attempt, workflowSHA: grant.workflowSHA, provider: grant.provider, protocol: grant.protocol });
}
