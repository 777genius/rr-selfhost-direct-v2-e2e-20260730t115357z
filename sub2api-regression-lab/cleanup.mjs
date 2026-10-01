import { jsonFile, loadConfig, mono, must } from './common.mjs';
import { cleanup } from './run.mjs';
import { cases } from './plan.mjs';
try {
  const c = await loadConfig(), id = process.argv[2];
  must(cases.some(s => s.id === id), 'CASE_REQUIRED'); c.deadline = mono() + 85000;
  const path = `/private/${c.run_id}.${id}.resources.json`, owned = await jsonFile(path);
  must(owned.path === path && Array.isArray(owned.resources) && owned.resources.every(r =>
    ['keys', 'users', 'accounts', 'groups'].includes(r.kind) && Number.isSafeInteger(r.id) && r.id > 0), 'OWNED_MANIFEST_REQUIRED');
  const result = await cleanup(c, owned);
  process.stdout.write(JSON.stringify(result) + '\n');
  if (result.failures || result.ambiguous_intent) process.exitCode = 1;
} catch { process.stderr.write('SCOPED_CLEANUP_FAILED\n'); process.exitCode = 1; }
