# PyInstaller spec file for Sign Package Estimator
# Generated to bundle the Dash application into a distributable folder.
# Usage:
#   pyinstaller sign_estimator.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

try:
    _spec_file = globals().get('__file__')  # may be missing in some invocation contexts
except Exception:
    _spec_file = None
project_root = Path(_spec_file).parent if _spec_file else Path.cwd()
app_script = str(project_root / 'app.py')

# Hidden imports (dynamic in Plotly / reportlab / cairosvg)
hidden = set()
for mod in [
    'plotly.io._kaleido',
    'cairosvg',
    'reportlab.pdfgen',
    'reportlab.lib',
    'PIL'
]:
    try:
        hidden.add(mod)
    except Exception:
        pass

# Collect deeper dynamic modules for plotly to avoid missing runtime components
try:
    for m in collect_submodules('plotly'):  # may add many; ensures reliability
        hidden.add(m)
except Exception:
    pass

assets_dir = project_root / 'assets'
logo_file = project_root / 'LSI_Logo.svg'

datas = []
if assets_dir.exists():
    datas.append((str(assets_dir), 'assets'))
if logo_file.exists():
    datas.append((str(logo_file), '.'))

# Additional data: database left external intentionally; user sets SIGN_APP_DB.

a = Analysis(
    [app_script],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=list(hidden),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
