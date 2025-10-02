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

datas = []
if assets_dir.exists():
    datas.append((str(assets_dir), 'assets'))
if logo_file.exists():
    datas.append((str(logo_file), '.'))

pkg_path = None
try:
    # Include full dash_cytoscape package to guarantee resource availability
    spec_dash_c = importlib.util.find_spec('dash_cytoscape')
    if spec_dash_c and spec_dash_c.origin:
        import pathlib
        pkg_path = pathlib.Path(spec_dash_c.origin).parent
        datas.append((str(pkg_path), 'dash_cytoscape'))
except Exception as _e_pkg:
    print(f"[spec][warn] locating dash_cytoscape failed: {_e_pkg}")

# Merge collect_all datas after manual additions to avoid duplicates; PyInstaller tolerates duplicates.
try:
    for _src, _tgt in _cy_d:  # type: ignore
        # Normalise single file vs directory entries
        datas.append((_src, _tgt))
except Exception:
    pass

# Force include specific cytoscape key files even if directory copy misbehaves
if pkg_path:
    for _fn in ['package.json', 'metadata.json', 'dash_cytoscape.min.js',
                'dash_cytoscape.dev.js', 'dash_cytoscape_extra.min.js',
                'dash_cytoscape_extra.dev.js']:
        try:
            _fpath = pkg_path / _fn
            if _fpath.exists():
                datas.append((str(_fpath), f'dash_cytoscape/{_fn}'))
        except Exception:
            pass

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
