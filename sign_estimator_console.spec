# Console-enabled PyInstaller spec for debugging
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_all
import importlib.util

block_cipher = None
try:
    _spec_file = globals().get('__file__')
except Exception:
    _spec_file = None
project_root = Path(_spec_file).parent if _spec_file else Path.cwd()
app_script = str(project_root / 'app.py')

hidden = set()
for mod in [
    'plotly.io._kaleido','cairosvg','reportlab.pdfgen','reportlab.lib','PIL','dash_cytoscape'
]:
    hidden.add(mod)
for pkg in ['plotly','dash_cytoscape']:
    try:
        for m in collect_submodules(pkg):
            hidden.add(m)
    except Exception:
        pass
try:
    _cy_d, _cy_b, _cy_h = collect_all('dash_cytoscape')
    hidden.update(_cy_h)
except Exception as _e_collect_all:
    print(f"[spec-console][warn] collect_all dash_cytoscape failed: {_e_collect_all}")

assets_dir = project_root / 'assets'
logo_file = project_root / 'LSI_Logo.svg'

datas = []
if assets_dir.exists():
    datas.append((str(assets_dir), 'assets'))
if logo_file.exists():
    datas.append((str(logo_file), '.'))

pkg_path = None
try:
    spec_dash_c = importlib.util.find_spec('dash_cytoscape')
    if spec_dash_c and spec_dash_c.origin:
        import pathlib
        pkg_path = pathlib.Path(spec_dash_c.origin).parent
        datas.append((str(pkg_path), 'dash_cytoscape'))
except Exception as _e_pkg:
    print(f"[spec-console][warn] locating dash_cytoscape failed: {_e_pkg}")

try:
    for _src, _tgt in _cy_d:  # type: ignore
        datas.append((_src, _tgt))
except Exception:
    pass

if pkg_path:
    for _fn in ['package.json','metadata.json','dash_cytoscape.min.js','dash_cytoscape.dev.js','dash_cytoscape_extra.min.js','dash_cytoscape_extra.dev.js']:
        try:
            _fpath = pkg_path / _fn
            if _fpath.exists():
                datas.append((str(_fpath), f'dash_cytoscape/{_fn}'))
        except Exception:
            pass

runtime_hook_dir = project_root / 'runtime_hooks'
stub_hook = runtime_hook_dir / 'cyto_stub.py'
if stub_hook.exists():
    _runtime_hooks = [str(stub_hook)]
else:
    _runtime_hooks = []

a = Analysis([
    app_script
], pathex=[str(project_root)], binaries=[], datas=datas, hiddenimports=list(hidden),
    hookspath=[str(project_root / 'pyinstaller_hooks')], hooksconfig={}, runtime_hooks=_runtime_hooks, excludes=[], noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
          name='sign_estimator_console', debug=False, console=True,
          strip=False, upx=True, upx_exclude=[], bootloader_ignore_signals=False,
          disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
          codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=True, upx_exclude=[], name='sign_estimator_console')
