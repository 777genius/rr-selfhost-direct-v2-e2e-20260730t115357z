// TRUSTED OPERATOR ONLY: creates synthetic private setup files. Never run in worker.
import { randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, basename, join } from 'node:path';
const dir = resolve(process.argv[2] ?? '');
if (!basename(dir).startsWith('rr-sub2-spike-20260930-') || !process.argv[2]) throw Error('Owned disposable private directory required');
await mkdir(dir, { mode: 0o700 }); // Refuse existing directories; never overwrite old custody state.
const pg = `synthetic-${randomBytes(24).toString('hex')}`, admin = `synthetic-${randomBytes(24).toString('hex')}`;
await writeFile(join(dir, 'postgres.env'), `POSTGRES_USER=rrsub2\nPOSTGRES_DB=rrsub2\nPOSTGRES_PASSWORD=${pg}\n`, { mode: 0o600 });
await writeFile(join(dir, 'sub2api.env'), `AUTO_SETUP=true\nSERVER_HOST=0.0.0.0\nSERVER_PORT=8080\nRUN_MODE=simple\nSIMPLE_MODE_AUTO_CREATE_DEFAULT_GROUPS=false\nDATABASE_HOST=postgres\nDATABASE_PORT=5432\nDATABASE_USER=rrsub2\nDATABASE_DBNAME=rrsub2\nDATABASE_PASSWORD=${pg}\nDATABASE_SSLMODE=disable\nREDIS_HOST=redis\nREDIS_PORT=6379\nADMIN_EMAIL=rr-sub2-spike-20260930@example.invalid\nADMIN_PASSWORD=${admin}\nJWT_SECRET=${randomBytes(32).toString('hex')}\nTOTP_ENCRYPTION_KEY=${randomBytes(32).toString('hex')}\nTZ=UTC\n`, { mode: 0o600 });
await writeFile(join(dir, 'login.json'), JSON.stringify({ email: 'rr-sub2-spike-20260930@example.invalid', password: admin }), { mode: 0o600 });
console.log('Created owned private synthetic initialization files; no credentials printed.');
