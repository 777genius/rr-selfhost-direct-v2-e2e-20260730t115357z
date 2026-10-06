// Independent review regressions: classify strings only; never execute them.
import test from 'node:test';
import assert from 'node:assert/strict';
import { codexNumericEvidence } from '../../sub2api-spike/evidence.mjs';
const example = { initial_balance: 100, amount: -10, final_balance: 110 };
const admit = command => codexNumericEvidence({ type: 'item.completed', item: {
  type: 'command_execution', status: 'completed', exit_code: 0, command,
  aggregated_output: JSON.stringify(example)
} }, example);
test('R8 independent double-outer-quote breakout must fail', () => {
  assert.equal(admit(`/usr/bin/bash -lc "node -e 'withdraw wallet.mjs "; echo injected; "'"`), false);
});
test('R8 independent single-outer-quote breakout must fail', () => {
  assert.equal(admit(`/usr/bin/bash -lc 'node -e "withdraw wallet.mjs '; echo injected; '"'`), false);
});
