import os, sys, site, importlib, traceback
print('Python:', sys.version)
print('Executable:', sys.executable)
print('PYTHONNOUSERSITE=', os.environ.get('PYTHONNOUSERSITE'))
print('ENABLE_USER_SITE=', getattr(site, 'ENABLE_USER_SITE', None))
try:
    usersite = site.getusersitepackages()
except Exception as e:
    usersite = f'error: {e!r}'
print('usersite:', usersite)
print('sys.path:')
for p in sys.path:
    print(' -', p)
print('\nImport checks:')
for mod in ['win32ctypes', 'win32ctypes.pywin32', 'win32ctypes.pywin32.pywintypes', 'win32api', 'pywintypes']:
    try:
        m = importlib.import_module(mod)
        print(f'OK import {mod}:', getattr(m, "__file__", None))
    except Exception as e:
        print(f'FAIL import {mod}: {e.__class__.__name__}: {e}')
        traceback.print_exc()
