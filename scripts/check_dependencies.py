"""Check module availability without importing the entire scientific stack."""
from importlib.util import find_spec
import sys
modules=['PySide6','numpy','scipy','PIL','colour','skimage','numba','pyfftw',
         'opt_einsum','OpenImageIO','rawpy','matplotlib','tifffile']
missing=[name for name in modules if find_spec(name) is None]
if missing:print('Missing dependencies: '+', '.join(missing))
sys.exit(bool(missing))
