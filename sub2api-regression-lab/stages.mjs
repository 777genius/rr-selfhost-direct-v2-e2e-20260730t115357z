import { spawn } from 'node:child_process';
import { jsonFile, mono } from './common.mjs';
import { cases } from './plan.mjs';
const stage = process.argv[2];
if (!['cancel', 'uncertainty', 'memory', 'soak'].includes(stage)) {
  process.stderr.write('STAGE_REQUIRED\n'); process.exitCode = 1;
} else {
  let failed = false;
  for (const spec of cases.filter(x => x.stage === stage)) {
    const launched = mono();
    const exitCode = await new Promise(resolve => {
      const child = spawn(process.execPath, [new URL('./run.mjs', import.meta.url).pathname, '--case', spec.id], { stdio: 'inherit' });
      let forced = false;
      const deadline = setTimeout(() => { forced = true; child.kill('SIGTERM'); }, 88000);
      const hardStop = setTimeout(() => child.kill('SIGKILL'), 90000);
      child.once('error', () => resolve(1)); child.once('close', code => { clearTimeout(deadline); clearTimeout(hardStop); resolve(forced ? 1 : code); });
    });
    failed ||= exitCode !== 0;
    let row; try { row = await jsonFile(`/evidence/${spec.id}.json`); } catch { break; }
    if (row.started_ms < launched) break;
    // Expected immediate-abort FAIL is retained; distinct fresh cancellation scenarios can run.
    // Never continue after duplicate/unknown effects, ambiguity, missing health, or unsafe teardown.
    if (!row.healthy_control || row.unknown_identity || row.active_at_boundary > 0 || row.cleanup_status === 'FAIL' ||
      !row.engine_protocol_verified || row.upstream.length !== (spec.count ?? spec.streams ?? 1) || row.safety_stop ||
      row.shutdown_requested_ms || row.safety_deadline_ms) break;
    if (stage !== 'cancel' && row.status === 'FAIL') break;
  }
  if (failed) process.exitCode = 1;
}
