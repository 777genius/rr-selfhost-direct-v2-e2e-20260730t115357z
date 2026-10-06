#!/usr/bin/env python3
"""Bounded offline evidence. No Go, services, network, Git, or real credentials.

SQLite checks execute extracted SQL after documented PostgreSQL dialect changes;
tuple/PAT checks are source-bound counterexamples, not Go execution. Lua checks
execute the literal source under local Lua 5.3 with a command-semantic store,
not Redis. None of these checks substitutes for coordinator service receipts.
"""
from pathlib import Path
import ctypes
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / '.spike-inputs'
OUT = ROOT / 'sub2api-oauth-review'
BACKEND = INPUT / 'patched/backend'
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def source(path):
    return (BACKEND / path).read_text()
def require(value, message):
    if not value:
        raise AssertionError(message)

manifest = json.loads((INPUT / 'oauth-fork-w2/manifest.json').read_text())
hashes = json.loads((INPUT / 'INPUT-HASHES.json').read_text())
require(all(digest(INPUT / p) == h for p, h in hashes.items()), 'frozen input hashes')
require(all(digest(INPUT / 'patched' / r['path']) == r['after_sha256']
            for r in manifest['production_files'] + manifest['test_overlay_files']), 'materialized bindings')
fingerprint = hashlib.sha256()
upstream = INPUT / 'upstream/backend'
upstream_files = sorted(p for p in upstream.rglob('*') if p.is_file() and not p.is_symlink())
for p in upstream_files:
    fingerprint.update(p.relative_to(upstream).as_posix().encode() + b'\0' + digest(p).encode() + b'\n')
require({'file_count': len(upstream_files), 'sha256': fingerprint.hexdigest()} == manifest['backend_fingerprint'], 'official archive fingerprint')

# Reconstruct only changed files; never duplicate the whole backend in reports.
with tempfile.TemporaryDirectory(prefix='patch-check-', dir=OUT) as temp:
    work = Path(temp)
    patch_chain = [INPUT / 'oauth-fork-w2/source.patch', ROOT / 'sub2api-oauth-lab/tests.patch', INPUT / 'oauth-fork-w2/tests-overlay.patch']
    before_paths = set()
    for patch in patch_chain:
        before_paths.update(re.findall(r'^--- a/(.+)$', patch.read_text(), re.M))
    for relative in before_paths:
        p = INPUT / 'upstream' / relative
        if p.exists():
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            target.chmod(0o600)
    for patch in patch_chain:
        result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(work), '-i', str(patch)], capture_output=True, text=True)
        require(result.returncode == 0, 'exact patch chain: ' + patch.name)
    require(all(digest(work / row['path']) == row['after_sha256'] for row in manifest['production_files'] + manifest['test_overlay_files']), 'reconstructed changed files')

execution = json.loads((INPUT / 'actual/execution.json').read_text())
receipts = json.loads((INPUT / 'actual/case-receipts-public.json').read_text())
require(execution['exit'] == 0 and not execution['compile_failed'] and not execution['failed_tests'] and not execution['skipped_tests'], 'coordinator success')
require(receipts['parsed_receipts'] == 23 and len(receipts['items']) == 23, '23 parsed receipts')
require(len({x['test'] for x in receipts['items']}) == 23, 'distinct cases')
inventory = json.loads((INPUT / 'oauth-fork-w2/case-inventory.json').read_text())
require({x['test'] for x in receipts['items']} == {x['case_id'] for x in inventory['cases']}, 'complete inventory coverage')
require(all(x['projection']['status'] == 'PASS' and x['test'] in execution['passed_tests'] for x in receipts['items']), 'receipt/test consistency')
require('TestOAuthForkSchedulerMetadataProjection' in execution['passed_tests'], 'metadata unit receipt')

repo = source('internal/repository/openai_oauth_durable.go')
service = source('internal/service/openai_oauth_durable.go')
claim_sql = re.search(r'ExecContext\(ctx, `(INSERT INTO account_oauth_refresh_attempts[\s\S]+?)`', repo).group(1)
load_sql = re.search(r'QueryContext\(ctx, `(SELECT EXISTS[\s\S]+?)`', repo).group(1)
def dialect(sql):
    return re.sub(r'::(?:bigint|jsonb|text)', '', sql).replace('now()', 'CURRENT_TIMESTAMP')
db = sqlite3.connect(':memory:')
db.executescript('''
CREATE TABLE account_oauth_refresh_attempts (
account_id INTEGER, revision INTEGER, owner TEXT UNIQUE, state TEXT,
expected_credentials TEXT, result_credentials TEXT, completion_revision INTEGER,
PRIMARY KEY(account_id, revision));
CREATE TABLE accounts (id INTEGER PRIMARY KEY, oauth_revision INTEGER,
credentials TEXT, deleted_at TEXT, platform TEXT, type TEXT, status TEXT,
schedulable BOOLEAN, auto_pause_on_expired BOOLEAN, expires_at TEXT);
''')
credentials = json.dumps({'refresh_token': 'fabricated-review-refresh', '_oauth_revision': '1'})
def claim(account_id, revision, owner):
    return db.execute(dialect(claim_sql), {'1': account_id, '2': revision, '3': owner, '4': credentials}).rowcount
require(claim(11, 1, 'owner-a') == 1, 'first owner inserted')
require(claim(11, 2, 'owner-b') == 0, 'same account replay blocked at new revision')
require(claim(12, 1, 'owner-c') == 1, 'same refresh token claim admitted on another account')
reproductions = [{'id': 'F2', 'kind': 'extracted SQL on in-memory SQLite', 'dialect_changes': 'remove bigint/jsonb/text casts; no PG row locking simulated',
    'same_account_second_claim_rows': 0, 'different_account_same_token_claim_rows': 1,
    'conclusion': 'Two durable pending owners can represent one refresh token across account IDs. Actual issuer replay not run.'}]

db.execute('DELETE FROM account_oauth_refresh_attempts')
db.execute('INSERT INTO accounts VALUES (13,1,?,NULL,\'openai\',\'oauth\',\'active\',0,0,NULL)', (credentials,))
require(db.execute(dialect(load_sql), {'1': 13, '2': '1', '3': credentials}).fetchone() is None, 'durable loader denies paused parent')
account = source('internal/service/account.go')
shadow_predicate = account.split('func (a *Account) IsCredentialUsableForShadow() bool {', 1)[1].split('\nfunc ', 1)[0]
require('!a.IsActive()' in shadow_predicate and '!a.Schedulable' not in shadow_predicate and 'RateLimitResetAt' not in shadow_predicate, 'independent upstream parent oracle')
require('parent,pending,err:=durable.LoadOAuthState(ctx,*current.ParentAccountID)' in service, 'actual parent call site')
require('account = credAccount' in source('internal/service/openai_gateway_service.go'), 'gateway resolves parent')
reproductions.append({'id': 'F3', 'kind': 'extracted SQL plus independent upstream predicate', 'parent_active': True,
    'parent_schedulable': False, 'upstream_credential_usable': True, 'fork_durable_loader_returns_row': False,
    'conclusion': 'Supported independently schedulable shadow is rejected because parent scheduling configuration is applied to credential admission.'})

gateway = source('internal/service/openai_gateway_service.go')
forward = source('internal/service/openai_gateway_forward.go')
headers = source('internal/service/openai_chatgpt_headers.go')
require('account=current' in gateway and 'token, _, err := s.GetAccessToken(ctx, account)' in forward, 'source-bound local account replacement')
require('s.buildUpstreamRequest(upstreamCtx, c, account, body, token' in forward and 'proxyURL = account.Proxy.URL()' in forward, 'caller retains routing snapshot')
require('headers.Set("chatgpt-account-id", chatgptAccountID)' in headers, 'identity header source')
selected = {'revision': '1', 'bearer_phase': 'old', 'identity_phase': 'old', 'proxy_phase': 'old'}
durable = {'revision': '2', 'bearer_phase': 'new', 'identity_phase': 'new', 'proxy_phase': 'new'}
wire = {**selected, 'bearer_phase': durable['bearer_phase']}
require(len({wire[k] for k in ('bearer_phase', 'identity_phase', 'proxy_phase')}) == 2, 'tuple coherence counterexample')
require(len({durable[k] for k in ('bearer_phase', 'identity_phase', 'proxy_phase')}) == 1, 'independent coherent oracle')
reproductions.append({'id': 'F1', 'kind': 'source-bound interleaving model, not Go/HTTP execution',
    'interleaving': ['select revision 1', 'commit reconnect/proxy change to revision 2', 'GetAccessToken loads revision 2 locally', 'Forward builds identity headers and selects proxy from revision 1'],
    'wire_phases': {k: wire[k] for k in ('bearer_phase', 'identity_phase', 'proxy_phase')},
    'conclusion': 'Fresh bearer is paired with stale identity/routing snapshot.'})

refresher = source('internal/service/token_refresher.go')
needs = refresher.split('func (r *OpenAITokenRefresher) NeedsRefresh', 1)[1].split('\nfunc ', 1)[0]
oauth = source('internal/service/openai_oauth_service.go')
require('if account.IsOpenAIPersonalAccessToken()' in needs and 'return false' in needs, 'PAT skip')
require('if !executor.NeedsRefresh(fresh, window)' in service, 'manual uses conditional helper')
require('return s.ValidateCodexPersonalAccessToken(ctx, accessToken, proxyURL)' in oauth, 'original PAT validation branch')
reproductions.append({'id': 'F4', 'kind': 'source-bound branch proof, not Go/provider execution', 'manual_helper_window': 'max duration',
    'PAT_needs_refresh': False, 'PAT_validator_reachable_via_manual_helper': False,
    'conclusion': 'Manual PAT refresh returns the durable row without invoking the existing validation/enrichment operation.'})

migration = source('migrations/241_openai_oauth_refresh_ownership.sql')
require("to_jsonb(NEW) - ARRAY['oauth_revision','credentials','updated_at','last_used_at','created_at']" in migration,
        'trigger compares Extra and all other nonexcluded fields')
require('NEW.oauth_revision := OLD.oauth_revision + 1;' in migration, 'trigger revision advance')
usage = source('internal/service/openai_gateway_usage.go')
require('updates["codex_usage_updated_at"]' in usage and 's.accountRepo.UpdateExtra(updateCtx, accountID, updates)' in usage,
        'real asynchronous usage publisher')
completion_sql = re.search(r'QueryContext\(ctx, `(UPDATE accounts a SET[\s\S]+?)`', repo).group(1)
for name, datatype in [('proxy_id', 'INTEGER'), ('error_message', 'TEXT'), ('updated_at', 'TEXT')]:
    db.execute('ALTER TABLE accounts ADD COLUMN ' + name + ' ' + datatype)
db.execute('DELETE FROM accounts')
db.execute('DELETE FROM account_oauth_refresh_attempts')
db.execute("INSERT INTO accounts(id,oauth_revision,credentials,platform,type,status,schedulable,auto_pause_on_expired) VALUES (14,1,?,'openai','oauth','active',1,0)", (credentials,))
require(claim(14, 1, 'owner-telemetry') == 1, 'claim before telemetry')
query = dialect(completion_sql).replace('UPDATE accounts a SET', 'UPDATE accounts AS a SET').replace('RETURNING a.oauth_revision,a.credentials', 'RETURNING oauth_revision,credentials')
arguments = {'1': 14, '2': '1', '3': credentials, '4': None,
    '5': json.dumps({'refresh_token': 'fabricated-review-successor', '_oauth_revision': '1'}), '6': False, '7': 'owner-telemetry'}
db.execute('SAVEPOINT control')
require(db.execute(query, arguments).fetchone() is not None, 'unchanged state completes: control')
db.execute('ROLLBACK TO control')
changed_credentials = json.dumps({'refresh_token': 'fabricated-review-refresh', '_oauth_revision': '2'})
# Model precisely the trigger's effect for an Extra-only write. No PG trigger
# engine is executed; actual completion/load predicates are executed below.
db.execute('UPDATE accounts SET oauth_revision=2,credentials=? WHERE id=14', (changed_credentials,))
require(db.execute(query, arguments).fetchone() is None, 'telemetry revision prevents completion')
pending = db.execute(dialect(load_sql), {'1': 14, '2': '2', '3': changed_credentials}).fetchone()
require(pending == (1,), 'unchanged refresh material remains protected indefinitely')
reproductions.append({'id': 'F5', 'kind': 'source-bound trigger effect model plus extracted completion/load SQL on SQLite',
    'control_completion_matches': True, 'telemetry_only_revision_change_completion_matches': False,
    'durable_pending_after_telemetry': True,
    'conclusion': 'An asynchronous usage Extra write fences successful rotation; unchanged consumed refresh material remains permanently pending.'})

# Execute literal source Lua offline. Redis command behavior is deliberately a
# small test harness; runtime Redis receipts remain the authority for services.
lua_source = source('internal/repository/oauth_cache_fence.go')
blocks = dict(re.findall(r'const (\w+) = (?:oauthRevisionFenceLua \+ )?`([\s\S]*?)`', lua_source))
lib = ctypes.CDLL('/usr/lib/x86_64-linux-gnu/liblua5.3.so.0')
lib.luaL_newstate.restype = ctypes.c_void_p
lib.luaL_openlibs.argtypes = [ctypes.c_void_p]
lib.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
lib.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
lib.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
lib.lua_tolstring.restype = ctypes.c_char_p
lib.lua_close.argtypes = [ctypes.c_void_p]
harness = '''
local store={}
redis={call=function(cmd,key,...)
 local a={...}
 if cmd=='HGET' then return store[key] and store[key][a[1]] end
 if cmd=='HSET' then store[key]=store[key] or {}; store[key][a[1]]=a[2]; return 1 end
 if cmd=='GET' then return store[key] end
 if cmd=='SET' then store[key]=a[1]; return 'OK' end
 if cmd=='DEL' then store[key]=nil; for _,k in ipairs(a) do store[k]=nil end; return 1 end
 error('unexpected command: '..cmd)
end}
'''
def lua_fn(name):
    body = blocks[name]
    if name != 'oauthTokenReadLua':
        body = blocks['oauthRevisionFenceLua'] + body
    return 'local ' + name + '=function(keys,args) KEYS=keys; ARGV=args; ' + body + '\nend\n'
lua_program = harness + ''.join(lua_fn(n) for n in ('oauthSchedulerWriteLua', 'oauthTokenWriteLua', 'oauthDeleteLua', 'oauthTokenReadLua')) + '''
local sk={'f','full','meta','token'}
assert(oauthSchedulerWriteLua(sk,{'9007199254740993','new-full','new-meta'})==1)
assert(oauthSchedulerWriteLua(sk,{'9007199254740992','old-full','old-meta'})==0)
assert(store.full=='new-full' and store.meta=='new-meta')
assert(oauthTokenWriteLua({'f','token','full','meta'},{'9007199254740993','fabricated',1000})==1)
assert(oauthTokenReadLua({'f','token'},{'9007199254740993'})=='fabricated')
assert(oauthTokenReadLua({'f','token'},{'9007199254740992'})=='')
assert(oauthDeleteLua({'f','full','meta','last','token'},{'9007199254740994','account'})==1)
assert(oauthSchedulerWriteLua(sk,{'9007199254740994','late-full','late-meta'})==0)
assert(oauthTokenWriteLua({'f','token','full','meta'},{'9007199254740993','fabricated',1000})==0)
assert(store.full==nil and store.meta==nil and store.token==nil)
assert(store.f.revision=='9007199254740994' and store.f.deleted=='1')
assert(oauthSchedulerWriteLua(sk,{'9007199254740995','reconnect-full','reconnect-meta'})==1)
assert(store.f.deleted=='0' and store.full=='reconnect-full')
'''
state = lib.luaL_newstate()
require(bool(state), 'local Lua state')
try:
    lib.luaL_openlibs(state)
    status = lib.luaL_loadstring(state, lua_program.encode())
    if status == 0:
        status = lib.lua_pcallk(state, 0, 0, 0, 0, None)
    require(status == 0, 'source Lua assertion: ' + str(lib.lua_tolstring(state, -1, None) if status else ''))
finally:
    lib.lua_close(state)

result = {'schema': 'oauth-independent-review-evidence/v1', 'input_hash_entries_verified': len(hashes),
    'backend_fingerprint': manifest['backend_fingerprint'], 'source_pin': manifest['source_pin'],
    'patches': manifest['patches'], 'canonical_tests_patch': manifest['canonical_tests_patch'],
    'changed_files_exact_patch_reconstruction': len(manifest['production_files']) + len(manifest['test_overlay_files']),
    'coordinator': {'execution_sha256': digest(INPUT / 'actual/execution.json'), 'public_receipts_sha256': digest(INPUT / 'actual/case-receipts-public.json'),
        'gofmt_list_sha256': digest(INPUT / 'actual/gofmt-list.json'), 'service_cases': 23, 'metadata_unit_pass': True,
        'public_projection_limitation': 'Only status and field names are supplied. Raw counters, PID values, timing, durable state, service versions and event values cannot be independently audited.',
        'receipt_count_field': execution['receipt_count'], 'receipt_count_interpretation': 'Execution metadata says 3; public file explicitly parses 23 case items. No raw capture provided to reconcile aggregation.'},
    'reproductions': reproductions, 'offline_lua': {'result': 'PASS', 'engine': 'local liblua 5.3', 'store': 'in-memory command-semantic harness',
        'assertions': ['adjacent integers above 2^53', 'full/meta atomic source script', 'matching token revision', 'stale token read denied', 'tombstone retained', 'equal/older write denied after deletion', 'newer revision may republish'],
        'limitations': 'Not Redis service execution; TTL/eviction/restart/cluster not measured.'},
    'reviewer_go_tests': 'NOT RUN: prohibited root toolchain/services', 'live_provider': 'NOT RUN: prohibited',
    'bindings': {r['path']: {'before_sha256': r['before_sha256'], 'after_sha256': r['after_sha256']} for r in manifest['production_files'] + manifest['test_overlay_files']}}
(OUT / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'result': 'PASS', 'verified_input_hashes': len(hashes), 'reconstructed_files': result['changed_files_exact_patch_reconstruction'],
    'coordinator_cases': 23, 'counterexamples': len(reproductions), 'offline_lua': 'PASS'}))
