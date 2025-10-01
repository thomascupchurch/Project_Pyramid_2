"""Comprehensive environment & deployment health diagnostic for Sign Package Estimator.

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
from typing import List, Dict

# Attempt to reuse verify_env logic if available
def _load_verify_env_summary() -> dict | None:
    try:
        import runpy
        # Execute verify_env.py in isolated globals capturing summary by calling build_summary and replicating logic would be heavy;
        # simpler: run as module with --json via subprocess for isolation.
        import subprocess, shutil, json as _json
        pyexe = sys.executable
        script = pathlib.Path(__file__).parent / 'verify_env.py'
        if not script.exists():
            return None
        proc = subprocess.run([pyexe, str(script), '--json'], capture_output=True, text=True, timeout=30)
        if proc.returncode not in (0,1):  # 1 allowed if missing modules
            return None
        # Last JSON block should parse
        txt = proc.stdout.strip()
        # Find JSON object start
        brace = txt.rfind('{')
        if brace == -1:
            return None
        data = _json.loads(txt[brace:])
        return data
    except Exception:
        return None

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


def _scan_cairo_runtime() -> Dict[str, str]:
    """Scan PATH for cairo-related DLL / shared objects to help diagnose native availability.

    Returns mapping of filename -> resolved path for first match of each target.
    """
    targets = ['cairo.dll','libcairo-2.dll','libcairo.so','libcairo.so.2','libcairo.2.dylib']
    found = {}
    path_entries = os.environ.get('PATH','').split(os.pathsep)
    for t in targets:
        for p in path_entries:
            candidate = pathlib.Path(p) / t
            try:
                if candidate.exists():
                    found[t] = str(candidate)
                    break
            except Exception:
                continue
    return found


def main():
    ap = argparse.ArgumentParser(description='Environment & deployment doctor for Sign Package Estimator')
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
    verify_env_summary = _load_verify_env_summary()
    cairo_scan = _scan_cairo_runtime()

    cairosvg_runtime = None
    recommendations: List[str] = []
    if verify_env_summary:
        cairosvg_runtime = verify_env_summary.get('cairosvg_runtime')
        # If verify_env classified as unknown but module is missing, coerce to missing
        try:
            mod_info = verify_env_summary.get('modules', {}).get('cairosvg')
            if (cairosvg_runtime in (None, 'unknown')) and isinstance(mod_info, str) and mod_info.startswith('missing:'):
                cairosvg_runtime = 'missing'
        except Exception:
            pass
        # propagate refined recommendations including new runtime classification guidance
        recs = verify_env_summary.get('recommendations') or []
        if isinstance(recs, list):
            for r in recs:
                if r not in recommendations:
                    recommendations.append(str(r))
    # Fallback heuristic / correction if runtime still unknown
    if cairosvg_runtime in (None, 'unknown'):
        if 'cairosvg' in mod_status and not mod_status['cairosvg']:
            cairosvg_runtime = 'missing'
        elif svg_func_status.startswith('import_error'):
            cairosvg_runtime = 'missing'
        elif (svg_func is False) and not cairo_scan:
            # functional failed, no runtime libs detected in PATH scan
            cairosvg_runtime = 'missing'

    summary = {
        'python_version': sys.version,
        'platform': platform.platform(),
        'core_modules': mod_status,
        'cairosvg_functional': svg_func,
        'cairosvg_functional_status': svg_func_status,
        'cairosvg_runtime': cairosvg_runtime,
        'venv_mismatch': mism,
        'venv_origin': origin,
        'requirements_sha256': req_hash,
        'tables': tables,
        'install_marker_present': marker_ok,
        'install_marker_path': marker_path,
        'svg_probe_status': svg_probe,
        'cairo_runtime_scan': cairo_scan,
        'recommendations': recommendations,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print('Sign Package Estimator Doctor Report')
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
        if cairosvg_runtime:
            print('Cairo Runtime  :', cairosvg_runtime)
            if cairosvg_runtime == 'missing' and 'Install native Cairo' not in ' '.join(recommendations):
                recommendations.append('Install native Cairo (MSYS2 or gtk-runtime) to enable cairosvg rendering.')
        if cairo_scan:
            print('Cairo DLL Scan :', ', '.join(f'{k}->{os.path.basename(v)}' for k,v in cairo_scan.items()))
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
        if recommendations:
            print('\nRecommendations:')
            for r in recommendations:
                print(' -', r)

    if args.out:
        try:
            with open(args.out, 'w') as f:
                json.dump(summary, f, indent=2)
        except Exception as e:  # noqa: BLE001
            print(f'[warn] failed writing JSON report: {e}', file=sys.stderr)
    return 0 if all(mod_status.values()) else 1

if __name__ == '__main__':
    sys.exit(main())
