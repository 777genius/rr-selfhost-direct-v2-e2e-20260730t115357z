"""Controller-installed packaging entry point; historical version is retained."""
from pathlib import Path
import runpy, sys
package = Path(__file__).resolve().parent
helper = package.parent / 'sub2api-transport-packaging' / 'audit.py'
sys.argv[1:1] = ['--package-root', str(package)]
runpy.run_path(str(helper), run_name='__main__')
