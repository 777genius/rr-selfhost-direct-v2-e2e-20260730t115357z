"""Controller-installed packaging entry point; historical version is retained."""
from pathlib import Path
import runpy, sys
package = Path(__file__).resolve().parent
helper = package.parent / 'sub2api-transport-packaging' / 'prepare-standalone.py'
sys.argv[1:1] = ['--package-root', str(package)]
if '--output' not in sys.argv: sys.argv += ['--output', str(package/'runtime')]
runpy.run_path(str(helper), run_name='__main__')
