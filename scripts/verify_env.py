#!/usr/bin/env python
"""
verify_env.py - Environment verification utility for the Sign Estimation app.

Checks for required modules, performs a cairosvg functional render test (if
installed), detects cross‑platform virtual environment mismatches, and can
emit a machine-readable JSON summary.
"""
import importlib, sys, platform, os, tempfile, textwrap
import json, argparse, hashlib, pathlib

REQUIRED_MODULES = [
    'flask', 'pandas', 'plotly', 'dash', 'dash_bootstrap_components', 'openpyxl', 'PIL', 'requests',
    'dash_cytoscape', 'cairosvg', 'reportlab', 'kaleido'
]

parser = argparse.ArgumentParser(description='Verify Sign Estimation environment')
parser.add_argument('--json', action='store_true', help='Emit JSON summary to stdout (machine readable)')
parser.add_argument('--out', help='Write JSON summary to file')
args, _unknown = parser.parse_known_args()

summary = {
    'python_version': sys.version,
    'platform': platform.platform(),
    'modules': {},
    'cairosvg_functional': None,
    'venv_mismatch': False,
    'venv_origin': None,
    'recommendations': []
}

print('Python', summary['python_version'])
print('Platform', summary['platform'])

missing = []
for mod in REQUIRED_MODULES:
    try:
        importlib.import_module(mod)
        summary['modules'][mod] = 'ok'
        print(f'[OK] {mod}')
    except Exception as e:  # noqa: BLE001 - we want to show any import error
        summary['modules'][mod] = f'missing: {e.__class__.__name__}: {e}'
        missing.append(mod)
        print(f'[MISSING] {mod}: {e}')
        if mod == 'cairosvg' and platform.system() == 'Darwin':
            print("    > macOS hint: install native libs then 'pip install cairosvg'")
            print("      brew install cairo pango libffi pkg-config")

"""cairosvg functional test (only if present)"""
if 'cairosvg' not in missing:
    functional = False
    error_msg = None
    try:
        import cairosvg  # type: ignore
        svg = "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='16'><rect width='32' height='16' fill='red'/></svg>"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            out_png = tmp.name
        try:
            cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=out_png)
            if os.path.exists(out_png) and os.path.getsize(out_png) > 0:
                functional = True
        except Exception as ce:  # noqa: BLE001
            error_msg = str(ce)
        finally:
            try:
                if os.path.exists(out_png):
                    os.remove(out_png)
            except Exception:  # noqa: BLE001
                pass
    except Exception as ie:  # noqa: BLE001
        error_msg = str(ie)
    if functional:
        summary['cairosvg_functional'] = True
        print('[OK] cairosvg functional render test')
    else:
        summary['cairosvg_functional'] = False
        print('[WARN] cairosvg import succeeds but render failed')
        if error_msg:
            print('       Error:', error_msg.split('\n')[0][:160])
        print('\nGuidance:')
        print(textwrap.dedent('''\
          - Cairo native DLLs not found. Options:
            1) Install GTK runtime (adds libcairo-2.dll).
            2) Install MSYS2 and add mingw64\\bin to PATH.
            3) Manually copy libcairo-2.dll and dependencies into a cairo_runtime/ folder and prepend PATH.
            4) Set DISABLE_SVG_RENDER=1 to skip SVG rasterization (fallback to text/PNG assets).
          - After installing, re-run: python scripts/verify_env.py
        '''))
        if platform.system() == 'Darwin':
            print(textwrap.dedent('''\
              macOS specific steps:
                - Install via Homebrew: brew install cairo pango libffi pkg-config
                - Ensure /opt/homebrew/lib (Apple Silicon) or /usr/local/lib (Intel) is in DYLD_FALLBACK_LIBRARY_PATH
                - Then: pip install --force-reinstall cairosvg
            '''))
else:
    summary['cairosvg_functional'] = None  # not installed so not evaluated

"""Virtual environment mismatch detection"""
try:
    venv_cfg = pathlib.Path(sys.prefix) / 'pyvenv.cfg'
    if venv_cfg.exists():
        cfg_text = venv_cfg.read_text(errors='ignore')
        lower = cfg_text.lower()
        if os.name == 'nt' and '\nhome = /users/' in lower:
            summary['venv_mismatch'] = True
            summary['venv_origin'] = 'macOS'
            msg = 'Detected macOS-origin virtualenv on Windows. Recreate venv locally.'
            print(f'[WARN] {msg}')
            summary['recommendations'].append(msg)
        if os.name != 'nt' and '\\python.exe' in lower:
            summary['venv_mismatch'] = True
            summary['venv_origin'] = 'Windows'
            msg = 'Detected Windows-origin virtualenv on non-Windows platform. Recreate venv locally.'
            print(f'[WARN] {msg}')
            summary['recommendations'].append(msg)
except Exception as me:  # noqa: BLE001
    print(f'[env-check][warn] mismatch detection failed: {me}')

"""Hash requirements.txt for quick diff reference"""
req_file = pathlib.Path('requirements.txt')
if req_file.exists():
    try:
        summary['requirements_sha256'] = hashlib.sha256(req_file.read_bytes()).hexdigest()
    except Exception:  # noqa: BLE001
        pass
exit_code = 0
if missing:
    print('\nMissing modules:', ', '.join(missing))
    exit_code = 1

if args.json:
    print(json.dumps(summary, indent=2))
if args.out:
    try:
        with open(args.out, 'w') as f:
            json.dump(summary, f, indent=2)
    except Exception as oe:  # noqa: BLE001
        print(f'[warn] failed writing summary file: {oe}')

degraded_note = ''
if 'cairosvg' not in missing and summary.get('cairosvg_functional') is False:
    degraded_note = ' (degraded: cairosvg render failed)'
print('\nEnvironment verification complete.' + degraded_note)
sys.exit(exit_code)
