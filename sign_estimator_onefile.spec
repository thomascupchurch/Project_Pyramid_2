"""
PyInstaller spec for single-file (onefile) Windows build with embedded icon.

Usage:
  pyinstaller sign_estimator_onefile.spec --noconfirm

This bundles the Dash app into a single EXE suitable for placing in OneDrive
and creating a Desktop shortcut that uses the LSI logo icon.
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_all

block_cipher = None

try:
    _spec_file = globals().get('__file__')
except Exception:
    _spec_file = None
project_root = Path(_spec_file).parent if _spec_file else Path.cwd()
app_script = str(project_root / 'app.py')

# Hidden imports for dynamic modules
hidden = set()
for mod in [
    'plotly.io._kaleido',
    'cairosvg',
    'reportlab.pdfgen', 'reportlab.lib',
    'PIL',
    'dash_cytoscape',
    # win32 shims to satisfy PyInstaller on Windows
    'win32ctypes',
    'win32ctypes.pywin32',
    'win32ctypes.pywin32.pywintypes',
    'pywintypes',
    'win32api'
]:
    hidden.add(mod)

# Include pyodbc when MSSQL backend requested at build time
import os as _os
if _os.getenv('SIGN_APP_DB_BACKEND','').lower() == 'mssql':
    hidden.add('pyodbc')

for pkg in ['plotly','dash_cytoscape']:
    try:
        for m in collect_submodules(pkg):
            hidden.add(m)
    except Exception:
        pass

_cy_d = []
try:
    _cy_d, _cy_b, _cy_h = collect_all('dash_cytoscape')
    hidden.update(_cy_h)
except Exception as _e_collect_all:
    print(f"[spec-onefile][warn] collect_all dash_cytoscape failed: {_e_collect_all}")

assets_dir = project_root / 'assets'
logo_file_root = project_root / 'LSI_Logo.svg'
version_file = project_root / 'VERSION.txt'

datas = []
if assets_dir.exists():
    datas.append((str(assets_dir), 'assets'))
if logo_file_root.exists():
    datas.append((str(logo_file_root), '.'))
if version_file.exists():
    datas.append((str(version_file), '.'))

for _src, _tgt in _cy_d or []:
    datas.append((_src, _tgt))

# Deduplicate
_seen = set()
_deduped = []
for _src, _tgt in datas:
    key = (_src, _tgt)
    if key in _seen:
        continue
    _seen.add(key)
    _deduped.append((_src, _tgt))
datas = _deduped

runtime_hook_dir = project_root / 'runtime_hooks'
stub_hook = runtime_hook_dir / 'cyto_stub.py'
_runtime_hooks = [str(stub_hook)] if stub_hook.exists() else []

# Optional icon (embedded into EXE if present)
ico_path = project_root / 'assets' / 'LSI_Logo.ico'
icon_arg = str(ico_path) if ico_path.exists() else None

a = Analysis(
    [app_script],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=list(hidden),
    hookspath=[str(project_root / 'pyinstaller_hooks')],
    hooksconfig={},
    runtime_hooks=_runtime_hooks,
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='sign_estimator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

# Note: No COLLECT section -> one-file EXE is produced.
