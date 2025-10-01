#!/usr/bin/env python
"""
verify_env.py - Environment verification utility for the Sign Package Estimator.

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

parser = argparse.ArgumentParser(description='Verify Sign Package Estimator environment')
parser.add_argument('--json', action='store_true', help='Emit JSON summary to stdout (machine readable)')
parser.add_argument('--out', help='Write JSON summary to file')
args, _unknown = parser.parse_known_args()

def build_summary():
    return {
        'python_version': sys.version,
        'platform': platform.platform(),
        'modules': {},
        'cairosvg_functional': None,
        'cairosvg_runtime': None,  # present|missing|unknown
        'cairosvg_error': None,
        'venv_mismatch': False,
        'venv_origin': None,
        'recommendations': []
    }

def classify_cairosvg_runtime(error_msg: str | None, module_missing: bool, functional: bool | None) -> str:
    """Classify cairosvg runtime state.

    Rules:
      - If module missing entirely -> missing (can't be used) unless we cannot distinguish cause.
      - If error message references missing cairo libs / no library called cairo* / cannot load libcairo variants -> missing.
      - If functional test passed -> present.
      - If import succeeded but functional test failed with *not an error about missing libs* -> present (logic issue / other error).
      - Else unknown.
    """
    if module_missing:
        # If we have an error message referencing cairo libs, treat as native runtime missing; else still missing (module not available)
        if error_msg:
            lower = error_msg.lower()
            if any(k in lower for k in ['no library called "cairo', 'libcairo-2.dll', 'libcairo.so', 'libcairo.2.dylib', 'cannot load library']):
                return 'missing'
        return 'missing'
    if functional:
        return 'present'
    if error_msg:
        lower = error_msg.lower()
        if any(k in lower for k in ['no library called "cairo', 'libcairo-2.dll', 'libcairo.so', 'libcairo.2.dylib', 'cannot load library']):
            return 'missing'
    # If we reached here module imported but either functional False with non-missing libs error, or we lack signal
    if functional is False:
        return 'present'  # libs likely present but render failed for another reason
    return 'unknown'

summary = build_summary()

print('Python', summary['python_version'])
print('Platform', summary['platform'])

missing = []
cairosvg_native_hint = None
cairosvg_import_error = None
error_msg = None  # ensure defined for classification when cairosvg missing
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
        if mod == 'cairosvg' and platform.system() == 'Windows':
            cairosvg_native_hint = str(e)
            cairosvg_import_error = str(e)

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
    # We'll classify later after functional section
    if functional:
        summary['cairosvg_functional'] = True
        print('[OK] cairosvg functional render test')
    else:
        summary['cairosvg_functional'] = False
        print('[WARN] cairosvg import succeeds but render failed')
        if error_msg:
            print('       Error:', error_msg.split('\n')[0][:160])
        # Guidance may differ depending on runtime classification later
else:
    summary['cairosvg_functional'] = None  # not installed so not evaluated
    if cairosvg_native_hint and ('no library called' in cairosvg_native_hint.lower() or 'cairo' in cairosvg_native_hint.lower()):
        summary['recommendations'].append('Install native Cairo (Windows: MSYS2 pacman -S mingw-w64-ucrt-x86_64-cairo OR choco install gtk-runtime).')
        summary['recommendations'].append('Alternative: drop required cairo-related DLLs into a folder and add it to PATH early.')
        summary['recommendations'].append('If not needed, suppress with SIGN_APP_IGNORE_MISSING=cairosvg or DISABLE_SVG_RENDER=1.')

# Final classification (works for both branches)
summary['cairosvg_error'] = error_msg or cairosvg_import_error
summary['cairosvg_runtime'] = classify_cairosvg_runtime(
    summary.get('cairosvg_error'),
    module_missing=('cairosvg' in missing),
    functional=summary.get('cairosvg_functional')
)

# Add guidance block only if runtime genuinely missing
if summary['cairosvg_runtime'] == 'missing':
    if 'Install native Cairo' not in ' '.join(summary['recommendations']):
        summary['recommendations'].append('Install native Cairo (MSYS2 or gtk-runtime) to enable cairosvg rendering.')
    if os.name == 'nt':
        summary['recommendations'].append('Ensure C:/msys64/ucrt64/bin (or gtk-runtime bin) precedes conflicting paths in PATH.')
    summary['recommendations'].append('Set DISABLE_SVG_RENDER=1 to bypass SVG rasterization if not required.')
    if platform.system() == 'Darwin':
        summary['recommendations'].append('Homebrew: brew install cairo pango libffi pkg-config; then pip install --force-reinstall cairosvg')
    # Only print guidance once in human mode (avoid duplication after JSON)
    if not args.json:
        print('\nGuidance:')
        print(textwrap.dedent('''\
          - Native Cairo runtime not detected. Options:
            1) MSYS2 (preferred Windows):
               * Install https://www.msys2.org/
               * Run: pacman -Syu   (close shell when prompted, reopen MSYS2 UCRT64 shell)
               * Run: pacman -S mingw-w64-ucrt-x86_64-cairo mingw-w64-ucrt-x86_64-libpng
               * Add C:\\msys64\\ucrt64\\bin to the front of PATH (System Properties > Environment Variables)
            2) GTK Runtime (Chocolatey): choco install gtk-runtime
            3) Manual DLLs: Place cairo, pixman, freetype, fontconfig, libpng, zlib in a folder and add to PATH early.
            4) Bypass: set DISABLE_SVG_RENDER=1 (or SIGN_APP_IGNORE_MISSING=cairosvg) to skip PNG rasterization.
          - After installing, re-run: python scripts/verify_env.py --json
        '''))

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
if summary.get('cairosvg_runtime') == 'missing' and 'cairosvg' in missing:
    degraded_note += ' (cairosvg & native cairo missing)'
print('\nEnvironment verification complete.' + degraded_note)
sys.exit(exit_code)
