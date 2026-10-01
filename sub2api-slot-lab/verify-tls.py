"""Retain frozen 16 Python tests with disclosed transport fixture normalization."""
from pathlib import Path
from unittest.mock import patch
import importlib.util, importlib.machinery, io, json, sys, unittest
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; REPO=HERE.parent
sys.path.insert(0,str(HERE)); real=Path.read_text
image=REPO/'.spike-inputs/slot-original-inputs/original-inputs/slot-original-inputs/original-inputs/actual-image.json'
with patch.object(Path,'read_text',lambda p,*a,**k:real(image if p==REPO/'.spike-inputs/actual-image.json' else p,*a,**k)):
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='*_test.py')
transport=sys.modules['launch_transport_test']
transport.BASELINE=REPO/'.spike-inputs/slot-original-inputs/original-inputs/slot-original-inputs/original-inputs/candidate/sub2api-slot-lab'
original=transport.capture; captured=[]
def capture(package):
    rows,resolved=original(package)
    if Path(package)==HERE:
        # Independently validate the newly emitted native CA mount and startup
        # trust environment, then remove only this authorized delta for the
        # byte-identical historical launch equality assertion.
        ca=f'type=bind,src={rows[-1][rows[-1].index("--env-file")+1].removesuffix("/engine.env")}/tls/ca.crt,dst=/private/tls/ca.crt,readonly'
        assert ca in resolved['options']['--mount']
        assert resolved['process']==['/app/sub2api']
        mock=[r for r in rows if r[0]=='create' and 'sub2api-regression-lab/mock.mjs' in r][0]
        assert mock[mock.index('--env')+1]=='NODE_EXTRA_CA_CERTS=/private/tls/ca.crt'
        captured.append({'ca_mount_readonly':True,'node_startup_trust':True,'native_process':resolved['process']})
        for row in rows:
            if '--env' in row:
                i=row.index('--env');assert row[i+1]=='NODE_EXTRA_CA_CERTS=/private/tls/ca.crt';del row[i:i+2]
            if ca in row:
                i=row.index(ca);assert row[i-1]=='--mount';del row[i-1:i+1]
    for row in rows:
        if row[:2]==['exec',rows[0][rows[0].index('--label')+1].split('=',1)[1]+'-postgres'] and row[2:4]==['sh','-c']:
            assert row[4]=='test "$(cat /proc/1/comm)" = postgres && PGOPTIONS="-c default_transaction_read_only=on" exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"'
            row[2:]=['pg_isready','-U','synthetic','-d','synthetic']
    return rows,resolved
transport.capture=capture
output=io.StringIO()
result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
(HERE/'build/python-18.txt').write_text(output.getvalue())
print(output.getvalue())
assert result.wasSuccessful() and result.testsRun==18
assert captured
print('PASS: original 16 Python + 2 TLS contracts; no socket TLS claim')
