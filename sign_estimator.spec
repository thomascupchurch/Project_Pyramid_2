# PyInstaller spec file for Sign Package Estimator
# Generated to bundle the Dash application into a distributable folder.
# Usage:
#   pyinstaller sign_estimator.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_all
import importlib.util

block_cipher = None

try:
    _spec_file = globals().get('__file__')  # may be missing in some invocation contexts
except Exception:
    _spec_file = None
project_root = Path(_spec_file).parent if _spec_file else Path.cwd()
app_script = str(project_root / 'app.py')

"""Spec hardening notes:
1. Previous builds intermittently omitted the dash_cytoscape data directory entirely.
2. We now: (a) collect_submodules; (b) collect_all to force data + dependencies; (c) explicitly add key files; (d) runtime hook creates a stub package.json if still absent.
"""

# Hidden imports (dynamic in Plotly / reportlab / cairosvg / dash_cytoscape)
hidden = set()
for mod in [
    'plotly.io._kaleido',
    'cairosvg',
    'reportlab.pdfgen',
    'reportlab.lib',
    'PIL',
    'dash_cytoscape'
]:
    try:
        hidden.add(mod)
    except Exception:
        pass

# Add pyodbc when building with MSSQL backend
import os as _os
if _os.getenv('SIGN_APP_DB_BACKEND','').lower() == 'mssql':
    hidden.add('pyodbc')

# Collect deeper dynamic modules for plotly to avoid missing runtime components
for pkg in ['plotly','dash_cytoscape']:
    try:
        for m in collect_submodules(pkg):
            hidden.add(m)
    except Exception:
        pass

# collect_all returns (datas, binaries, hiddenimports)
try:
    _cy_d, _cy_b, _cy_h = collect_all('dash_cytoscape')
    hidden.update(_cy_h)
except Exception as _e_collect_all:
    print(f"[spec][warn] collect_all dash_cytoscape failed: {_e_collect_all}")

assets_dir = project_root / 'assets'
logo_file = project_root / 'LSI_Logo.svg'
version_file = project_root / 'VERSION.txt'

datas = []
if assets_dir.exists():
    datas.append((str(assets_dir), 'assets'))
if logo_file.exists():
    datas.append((str(logo_file), '.'))
if version_file.exists():
    datas.append((str(version_file), '.'))

pkg_path = None  # no manual directory copy; rely on collect_all

# Merge collect_all datas after manual additions to avoid duplicates; PyInstaller tolerates duplicates.
try:
    for _src, _tgt in _cy_d:  # type: ignore
        datas.append((_src, _tgt))
except Exception:
    pass

# Force include specific cytoscape key files even if directory copy misbehaves
## Removed explicit dash_cytoscape file forcing; collect_all already supplies these

# ---------------- Deduplicate datas to avoid file/directory collision ----------------
_seen = set()
_deduped = []
for _src, _tgt in datas:
    key = (_src, _tgt)
    if key in _seen:
        continue
    _seen.add(key)
    _deduped.append((_src, _tgt))
datas = _deduped

# Add runtime hook to create stub package.json if still missing at startup
runtime_hook_dir = project_root / 'runtime_hooks'
stub_hook = runtime_hook_dir / 'cyto_stub.py'
if stub_hook.exists():
    _runtime_hooks = [str(stub_hook)]
else:
    _runtime_hooks = []
# Additional data: database left external intentionally; user sets SIGN_APP_DB.

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
    console=False,  # False -> no console window; set True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='sign_estimator'
)
