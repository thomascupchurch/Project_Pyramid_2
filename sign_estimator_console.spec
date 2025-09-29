# Console-enabled PyInstaller spec for debugging
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
try:
    _spec_file = globals().get('__file__')
except Exception:
    _spec_file = None
project_root = Path(_spec_file).parent if _spec_file else Path.cwd()
app_script = str(project_root / 'app.py')

hidden = set()
for mod in [
    'plotly.io._kaleido','cairosvg','reportlab.pdfgen','reportlab.lib','PIL'
]:
    hidden.add(mod)
try:
    for m in collect_submodules('plotly'):
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

a = Analysis([
    app_script
], pathex=[str(project_root)], binaries=[], datas=datas, hiddenimports=list(hidden),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
          name='sign_estimator_console', debug=False, console=True,
          strip=False, upx=True, upx_exclude=[], bootloader_ignore_signals=False,
          disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
          codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=True, upx_exclude=[], name='sign_estimator_console')
