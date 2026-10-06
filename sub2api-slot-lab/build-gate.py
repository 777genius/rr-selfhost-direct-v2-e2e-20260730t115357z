"""Small external root trust gate; does not claim private compilation occurred.
The root operator pins the reviewed producer ledger, final patch and build receipt
in a separately held mode-0600 configuration. Local file bytes are only bindings.
"""
import hashlib, json, re
from pathlib import Path

HEX = re.compile(r'[a-f0-9]{64}\Z')
def need(ok, code):
    if not ok: raise ValueError(code)
def digest(data): return hashlib.sha256(data).hexdigest()
def fingerprint(files): return digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
def hash_value(value): return isinstance(value, str) and HEX.fullmatch(value)
def file_map(value):
    need(isinstance(value, dict) and bool(value), 'NONEMPTY_FULL_SOURCE_MAP_REQUIRED')
    for name, value_hash in value.items():
        need(isinstance(name, str) and not Path(name).is_absolute() and '..' not in Path(name).parts and hash_value(value_hash), 'SOURCE_MAP_ENTRY')
    need('backend/go.mod' in value, 'FULL_SOURCE_LEDGER_REQUIRED')
def public_bytes(path):
    p = Path(path)
    need(p.is_absolute() and p.is_file() and not p.is_symlink(), 'PUBLIC_REGULAR_INPUT_REQUIRED')
    return p.read_bytes()  # Public patches/ledgers may have ordinary 0644 permissions.
def verify(c, pins, private_read):
    def pinned(key, private=False):
        need(key in c and hash_value(c.get(key+'_sha256')), 'EXTERNAL_ROOT_PIN_REQUIRED')
        data = private_read(c[key]) if private else public_bytes(c[key])
        need(digest(data) == c[key+'_sha256'], 'EXTERNAL_ROOT_BYTE_BINDING')
        return data
    m = json.loads(pinned('reviewed_merged_manifest'))
    patch = pinned('production_patch')
    b = json.loads(pinned('build_attestation', True))
    need(m.get('schema') == 'slot-reviewed-merged-source-v1' and m.get('review_status') == 'APPROVED' and m.get('inventory_scope') == 'full-build-context', 'REVIEWED_MERGED_PRODUCER_REQUIRED')
    need(m.get('upstream_commit') == pins['upstream_commit'], 'SOURCE_UPSTREAM')
    expected = {k: v['sha256'] for k,v in pins['components'].items()}
    need(m.get('component_provenance') == expected, 'REVIEWED_COMPONENT_PROVENANCE')
    need(b.get('schema') == 'slot-root-actual-image-build-v1' and b.get('status') == 'BUILT' and
         b.get('trust_model') == 'external-root-build-receipt' and isinstance(b.get('build_id'), str) and bool(b['build_id']), 'ACTUAL_ROOT_BUILD_RECEIPT_REQUIRED')
    components = b.get('components')
    need(isinstance(components, dict) and set(components) == set(expected), 'ALL_SOURCE_MERGES_REQUIRED')
    for name, entry in components.items():
        need(isinstance(entry, dict) and entry.get('sha256') == expected[name] and bool(expected[name]), 'REVIEWED_COMPONENT_PIN')
        data = public_bytes(entry['path'])
        need(bool(data) and digest(data) == expected[name], 'SOURCE_PATCH_BINDING')
    file_map(m.get('base_files')); file_map(m.get('merged_files'))
    changes = m.get('production_changes')
    need(isinstance(changes, dict) and bool(changes), 'NONEMPTY_PRODUCTION_CHANGE_MAP')
    base, merged = m['base_files'], m['merged_files']
    changed = {n for n in set(base) | set(merged) if base.get(n) != merged.get(n)}
    need(set(changes) == changed, 'EXACT_PRODUCTION_CHANGE_MAP')
    for name, row in changes.items():
        need(row == {'before_sha256': base.get(name), 'after_sha256': merged.get(name)}, 'PRODUCTION_LEDGER_BINDING')
    paths = re.findall(rb'^diff --git a/(\S+) b/(\S+)$', patch, re.M)
    need(bool(paths) and all(a == z for a,z in paths) and len(paths) == len(set(paths)) and
         {a.decode() for a,z in paths} == changed, 'DEDUPLICATED_FULL_PRODUCTION_PATCH')
    blocks = patch.split(b'diff --git ')[1:]
    need(all(re.search(rb'^@@ ', block, re.M) and re.search(rb'^--- ', block, re.M) and re.search(rb'^\+\+\+ ', block, re.M) for block in blocks), 'PRODUCTION_PATCH_HUNKS_REQUIRED')
    patch_sha = digest(patch); source_sha = fingerprint(merged)
    need(m.get('production_patch_sha256') == patch_sha and m.get('source_fingerprint_sha256') == source_sha, 'REVIEWED_EXACT_FINAL_SOURCE')
    need(b.get('upstream_commit') == pins['upstream_commit'] and b.get('component_provenance') == expected and
         b.get('source_manifest_sha256') == c['reviewed_merged_manifest_sha256'] and
         b.get('production_patch_sha256') == patch_sha and b.get('source_fingerprint_sha256') == source_sha and
         b.get('build_input_source_fingerprint_sha256') == source_sha, 'SAME_OBSERVED_BUILD_SOURCE_REQUIRED')
    need(b.get('image') == c.get('engine_image') and re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}', b.get('image','')),
         'NATIVE_BUILD_IDENTITY')
    need(hash_value(b.get('binary_sha256')) and hash_value(b.get('image_config_sha256')) and
         re.fullmatch(r'sha256:[a-f0-9]{64}', b.get('image_id','')), 'ACTUAL_BINARY_IMAGE_CONFIG_REQUIRED')
    need(b['binary_sha256'] != pins['supplied_native_probe_binary_sha256'] and
         b['image_id'] != pins['supplied_native_probe_image_id'] and
         b['image'].split('@')[1] != pins['supplied_native_probe_image_id'], 'HISTORICAL_NATIVE_BUILD_FORBIDDEN')
    need(b.get('api_key_slots') == 'stats-only' and b.get('trusted_cancel_flag') == 'native_api_key_cancel_on_disconnect', 'LEASE_OR_FLAG_SEMANTICS')
    return b
