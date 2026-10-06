import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, readFile, access, rm, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createBroker } from '../sub2api-spike/broker.mjs';
import { stop } from '../sub2api-spike/util.mjs';

// SR1: failed initialization must release its own lock so repaired disk state
// can restart. These are actual filesystem failures; no listener is opened.
for (const kind of ['malformed JSON', 'invalid schema', 'read EISDIR', 'persist failure']) {
  test(`SR1 constructor recovers after ${kind}`, async t => {
    const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-sr1-'));
    t.after(() => rm(dir, { recursive: true, force: true }));
    const ledgerPath = join(dir, 'ledger.json');
    const config = { ledgerPath, scopes: {} };
    let error;
    if (kind === 'malformed JSON') { await writeFile(ledgerPath, '{'); error = SyntaxError; }
    if (kind === 'invalid schema') { await writeFile(ledgerPath, '{"schema":0,"runs":{}}'); error = /Invalid ledger/; }
    if (kind === 'read EISDIR') { await mkdir(ledgerPath); error = { code: 'EISDIR' }; }
    if (kind === 'persist failure') { await mkdir(ledgerPath + '.new'); error = { code: 'ledger_unavailable' }; }
    await assert.rejects(createBroker(config), error);
    await assert.rejects(access(ledgerPath + '.lock'), { code: 'ENOENT' });

    if (kind === 'read EISDIR') await rm(ledgerPath, { recursive: true });
    if (kind === 'persist failure') await rm(ledgerPath + '.new', { recursive: true });
    const repaired = { schema: 1, runs: { '123': { attempt: '1', workspace: 'a', state: 'issued' } } };
    await writeFile(ledgerPath, JSON.stringify(repaired));
    const server = await createBroker(config);
    t.after(() => stop(server));
    await access(ledgerPath + '.lock');
    assert.deepEqual(JSON.parse(await readFile(ledgerPath, 'utf8')), repaired);
    await stop(server);
    await assert.rejects(access(ledgerPath + '.lock'), { code: 'ENOENT' });
  });
}

// EEXIST may represent another owner or a crashed broker. Never remove it or
// touch the ledger when exclusive acquisition fails.
test('SR1 constructor preserves an existing foreign or crash lock', async t => {
  const dir = await mkdtemp(join(tmpdir(), 'rr-sub2-sr1-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const ledgerPath = join(dir, 'ledger.json');
  await writeFile(ledgerPath, '{');
  await writeFile(ledgerPath + '.lock', 'foreign-or-crashed-owner');
  const before = await stat(ledgerPath + '.lock');
  await assert.rejects(createBroker({ ledgerPath, scopes: {} }), { code: 'EEXIST' });
  assert.equal(await readFile(ledgerPath + '.lock', 'utf8'), 'foreign-or-crashed-owner');
  assert.equal((await stat(ledgerPath + '.lock')).ino, before.ino);
  assert.equal(await readFile(ledgerPath, 'utf8'), '{');
});
