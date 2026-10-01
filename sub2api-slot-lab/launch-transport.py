"""Offline Docker create transport decoder; never invokes Docker or a container.
OCI image defaults are operator-reported public evidence, not live inspection.
"""
import json, sys

def decode(argv, image_config):
    assert argv[0] == 'create'
    flags = {'--pull=never', '--no-healthcheck', '--read-only'}
    values = {}; i = 1
    while i < len(argv) and argv[i].startswith('--'):
        key = argv[i]
        if key in flags:
            values.setdefault(key, []).append(True); i += 1
        else:
            values.setdefault(key, []).append(argv[i+1]); i += 2
    image = argv[i]; command = argv[i+1:]
    override = values.get('--entrypoint')
    entrypoint = override if override else image_config['Entrypoint']
    # Docker clears image Cmd when an explicit entrypoint is provided.
    cmd = command or ([] if override else image_config['Cmd'])
    process = entrypoint + cmd
    uid = values.get('--user', [image_config['User'] or '0'])[0].split(':')[0]
    selected = process
    # Reported image script delegates UID 0 to su-exec sub2api.
    if process[0] == '/app/docker-entrypoint.sh' and uid == '0':
        selected = ['su-exec', 'sub2api', *process[1:]]
    return {'image': image, 'options': values, 'process': process,
            'selected': selected, 'uid': uid,
            'requires_setuid_setgid': selected[0] == 'su-exec'}

if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(decode(request['argv'], request['image_config'])))
