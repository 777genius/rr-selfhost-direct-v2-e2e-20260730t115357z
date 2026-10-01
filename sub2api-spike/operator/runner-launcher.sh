#!/bin/sh
# Root-owned, fixed no-argument sudo entry. Never run workflow-supplied commands.
set -eu
[ "$#" -eq 0 ]
[ "$(/usr/bin/id -u)" -eq 0 ]
[ "${SUDO_UID:-}" = 1001 ]
cd /opt/rr-sub2-harness
/usr/bin/sha256sum --status --check harness.sha256
exec /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 /usr/local/bin/node /opt/rr-sub2-harness/sub2api-spike/run-client.mjs
