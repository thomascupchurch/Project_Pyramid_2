"""Comprehensive environment & deployment health diagnostic for Sign Estimation App.

Checks performed:
  - Python version & platform
  - Core module availability (dash, pandas, plotly, dash_bootstrap_components, reportlab, kaleido, cairosvg)
  - Optional cairosvg functional render test (lightweight)
  - Virtual environment mismatch heuristic (cross-OS venv)
  - Database presence & table listing with row counts (if requested)
  - requirements.txt hash + install marker file state
  - SVG probe environment flag (SIGN_APP_SVG_STATUS)

Usage:
  python scripts/doctor.py                 # human-readable summary
  python scripts/doctor.py --json          # JSON summary only
  python scripts/doctor.py --tables        # include table rows counts
  python scripts/doctor.py --no-cairosvg   # skip cairosvg functional test
  python scripts/doctor.py --out report.json
"""
from __future__ import annotations
import sys, os, argparse, json, hashlib, sqlite3, tempfile, platform, importlib.util, pathlib

CORE_MODULES = [
    'dash', 'pandas', 'plotly', 'dash_bootstrap_components', 'reportlab', 'kaleido', 'cairosvg'
]


def hash_requirements(path: str):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None

def check_modules():
    status = {}
    for m in CORE_MODULES:
        spec = importlib.util.find_spec(m)
        status[m] = bool(spec)
    return status

def cairosvg_functional(skip: bool):
    if skip:
        return None, 'skipped'
    if not importlib.util.find_spec('cairosvg'):
        return None, 'missing'
    try:
        import cairosvg  # type: ignore
        svg = "<svg xmlns='http://www.w3.org/2000/svg' width='40' height='20'><rect width='40' height='20' fill='orange'/></svg>"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            outp = tmp.name
        try:
            cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=outp)
            ok = os.path.exists(outp) and os.path.getsize(outp) > 0
            return bool(ok), 'ok' if ok else 'empty_output'
        except Exception as e:  # noqa: BLE001
            return False, f'error:{e.__class__.__name__}'
        finally:
            try:
                if os.path.exists(outp):
                    os.remove(outp)
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        return False, f'import_error:{e.__class__.__name__}'


def detect_venv_mismatch():
    try:
        venv_cfg = pathlib.Path(sys.prefix) / 'pyvenv.cfg'
        if venv_cfg.exists():
            txt = venv_cfg.read_text(errors='ignore').lower()
            if os.name == 'nt' and '\nhome = /users/' in txt:
                return True, 'macOS'
            if os.name != 'nt' and '\\python.exe' in txt:
                return True, 'Windows'
    except Exception:
        return False, None
    return False, None


def list_tables(db_path: str, counts: bool):
    if not os.path.exists(db_path):
        return {'error': 'missing', 'tables': []}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        result = {'tables': tables}
        if counts:
            row_counts = {}
            for t in tables:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM {t}')
                    row_counts[t] = cur.fetchone()[0]
                except Exception as e:  # noqa: BLE001
                    row_counts[t] = f'error:{e.__class__.__name__}'
            result['row_counts'] = row_counts
        conn.close()
        return result
    except Exception as e:  # noqa: BLE001
        return {'error': f'query_error:{e.__class__.__name__}', 'tables': []}


def load_install_marker():
    # Heuristic for per-user marker (Windows & mac/Linux) used by startup scripts
    candidates = []
    if os.name == 'nt':
        local = os.environ.get('LOCALAPPDATA')
        if local:
            candidates.append(pathlib.Path(local)/'SignEstimator'/'install_complete.marker')
    # mac/Linux
    home = pathlib.Path.home()
    candidates.append(home/'.local'/'share'/'SignEstimator'/'install_complete.marker')
    candidates.append(home/'Library'/'Application Support'/'SignEstimator'/'install_complete.marker')
    for c in candidates:
        if c.exists():
            return True, str(c)
    return False, None


def main():
    ap = argparse.ArgumentParser(description='Environment & deployment doctor for Sign Estimation App')
    ap.add_argument('--json', action='store_true', help='Emit JSON only')
    ap.add_argument('--tables', action='store_true', help='Include table list & counts')
    ap.add_argument('--no-cairosvg', action='store_true', help='Skip cairosvg functional test')
    ap.add_argument('--db', default='sign_estimation.db', help='Database path (default sign_estimation.db)')
    ap.add_argument('--out', help='Write JSON to file')
    args = ap.parse_args()

    mod_status = check_modules()
    svg_func, svg_func_status = cairosvg_functional(args.no_cairosvg)
    mism, origin = detect_venv_mismatch()
    req_hash = hash_requirements('requirements.txt')
    tables = list_tables(args.db, args.tables)
    marker_ok, marker_path = load_install_marker()
    svg_probe = os.environ.get('SIGN_APP_SVG_STATUS')

    summary = {
        'python_version': sys.version,
        'platform': platform.platform(),
        'core_modules': mod_status,
        'cairosvg_functional': svg_func,
        'cairosvg_functional_status': svg_func_status,
        'venv_mismatch': mism,
        'venv_origin': origin,
        'requirements_sha256': req_hash,
        'tables': tables,
        'install_marker_present': marker_ok,
        'install_marker_path': marker_path,
        'svg_probe_status': svg_probe,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print('Sign Estimation App Doctor Report')
        print('--------------------------------')
        print('Python         :', summary['python_version'].split()[0])
        print('Platform       :', summary['platform'])
        print('Core Modules   :', ', '.join(f"{m}{'' if ok else ' (missing)'}" for m, ok in mod_status.items()))
        print('Venv Mismatch  :', 'YES ('+origin+')' if mism else 'no')
        print('Req Hash       :', req_hash or 'n/a')
        print('Install Marker :', 'present' if marker_ok else 'missing')
        if svg_probe and svg_probe != 'ok':
            print('SVG Probe      :', svg_probe)
        print('CairoSVG Test  :', svg_func_status)
        if args.tables:
            if 'error' in tables and tables['error']:
                print('Tables         : error -', tables['error'])
            else:
                print('Tables         :', ', '.join(tables['tables']) or '(none)')
                if 'row_counts' in tables:
                    for t, c in tables['row_counts'].items():
                        print(f'  - {t}: {c}')
        if mism:
            print('\nRecommendation: Recreate the virtual environment locally (see DEPLOY.md section 10).')
        missing = [m for m, ok in mod_status.items() if not ok]
        if missing:
            print('Missing modules detected — run: pip install -r requirements.txt')
        if not marker_ok:
            print('Install marker missing — a reinstall may be triggered on next launcher run.')

    if args.out:
        try:
            with open(args.out, 'w') as f:
                json.dump(summary, f, indent=2)
        except Exception as e:  # noqa: BLE001
            print(f'[warn] failed writing JSON report: {e}', file=sys.stderr)
    return 0 if all(mod_status.values()) else 1

if __name__ == '__main__':
    sys.exit(main())
