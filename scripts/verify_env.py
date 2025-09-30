#!/usr/bin/env python
import importlib, sys, platform, os, tempfile, textwrap
mods = [
    'flask','pandas','plotly','dash','dash_bootstrap_components','openpyxl','PIL','requests',
    'dash_cytoscape','cairosvg','reportlab','kaleido'
]
print('Python', sys.version)
print('Platform', platform.platform())
missing = []
for m in mods:
    try:
        importlib.import_module(m)
        print(f'[OK] {m}')
    except Exception as e:
        print(f'[MISSING] {m}: {e}')
        missing.append(m)
        if m == 'cairosvg' and platform.system() == 'Darwin':
            print("    > macOS hint: install native libs then 'pip install cairosvg'")
            print("      brew install cairo pango libffi pkg-config")

# Enhanced cairosvg functional check
if 'cairosvg' not in missing:
    functional = False
    error_msg = None
    try:
        import cairosvg
        svg = "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='16'><rect width='32' height='16' fill='red'/></svg>"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            outp = tmp.name
        try:
            cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=outp)
            if os.path.exists(outp) and os.path.getsize(outp) > 0:
                functional = True
        except Exception as ce:
            error_msg = str(ce)
        finally:
            try:
                if os.path.exists(outp):
                    os.remove(outp)
            except Exception:
                pass
    except Exception as ie:
        error_msg = str(ie)
    if functional:
        print('[OK] cairosvg functional render test')
    else:
        print('[WARN] cairosvg import succeeds but render failed')
        if error_msg:
            print('       Error:', error_msg.split('\n')[0][:160])
        print('\nGuidance:')
        print(textwrap.dedent('''\
          - Cairo native DLLs not found. Options:
            1) Install GTK runtime (adds libcairo-2.dll).
            2) Install MSYS2 and add mingw64\bin to PATH.
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
        # Do not mark module missing (still importable) but treat as degraded
exit_code = 0
if missing:
    print('\nMissing modules:', ', '.join(missing))
    exit_code = 1
print('\nEnvironment verification complete.' + (' (degraded: cairosvg render failed)' if 'cairosvg' not in missing and 'functional' in locals() and not functional else ''))
sys.exit(exit_code)
