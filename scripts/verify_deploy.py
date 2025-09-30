#!/usr/bin/env python3
"""Quick verification script for a deployed OneDrive copy.
Run from either the project root (local) or inside the deployed OneDrive root.

Checks:
  - Presence of app/ directory (if running in OneDrive deployment root)
  - Presence of bundle/sign_estimator*/ executable (optional) or startup scripts
  - deployment_info.json freshness (<= 24h old) if present
  - Database file existence (database/sign_estimation.db or app/sign_estimation.db)
  - Reports versions.txt or VERSION.txt if present

Usage:
  python scripts/verify_deploy.py --path "C:/Users/Me/OneDrive/SignEstimationApp"
  python scripts/verify_deploy.py            (auto-detect if run inside path)
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path
from datetime import datetime, timedelta, timezone

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

def status(label: str, state: str, msg: str):
    print(f"[{state:<4}] {label}: {msg}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", help="OneDrive deployment root (parent of app/, bundle/, start_app.bat)")
    parser.add_argument("--json", action="store_true", help="Output JSON summary only")
    args = parser.parse_args()

    root = Path(args.path) if args.path else Path.cwd()
    # Detect if we're inside the app subdir, adjust up
    if (root / 'app').is_dir() is False and (root.parent / 'app').is_dir() and (root / 'app.py').is_file():
        # Running inside 'app'; real root is parent
        root = root.parent

    summary = {
        'root': str(root),
        'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
        'checks': {}
    }

    app_dir = root / 'app'
    bundle_dir = root / 'bundle'
    start_bat = root / 'start_app.bat'
    start_ps1 = root / 'start_app.ps1'
    deploy_info = root / 'deployment_info.json'

    # 1. Root structure
    if app_dir.is_dir():
        summary['checks']['app_dir'] = True
        if not args.json: status('app/', OK, 'found')
    else:
        summary['checks']['app_dir'] = False
        if not args.json: status('app/', FAIL, 'missing')

    # 2. Bundle presence (optional)
    bundle_variants = list(bundle_dir.glob('sign_estimator*')) if bundle_dir.is_dir() else []
    has_bundle = any((b / (b.name + '.exe')).exists() for b in bundle_variants)
    summary['checks']['bundle_present'] = has_bundle
    if not args.json:
        if has_bundle:
            status('bundle', OK, f"{len(bundle_variants)} variant(s) present")
        else:
            status('bundle', WARN, 'no bundle (will use source + venv)')

    # 3. Startup scripts
    scripts_ok = start_bat.exists() or start_ps1.exists()
    summary['checks']['startup_scripts'] = scripts_ok
    if not args.json:
        status('startup scripts', OK if scripts_ok else FAIL, 'present' if scripts_ok else 'missing start_app.bat/ps1')

    # 4. Deployment info freshness
    if deploy_info.exists():
        try:
            info = json.loads(deploy_info.read_text())
            ts = info.get('deployed_at')
            fresh = False
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace('Z',''))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    fresh = datetime.now(timezone.utc) - dt < timedelta(days=1)
                except Exception:
                    pass
            summary['checks']['deployment_info'] = {'exists': True, 'fresh': fresh}
            if not args.json:
                status('deployment_info.json', OK if fresh else WARN, 'fresh (<24h)' if fresh else 'stale/older than 24h')
        except Exception as e:
            summary['checks']['deployment_info'] = {'exists': True, 'error': str(e)}
            if not args.json: status('deployment_info.json', WARN, f'parse error: {e}')
    else:
        summary['checks']['deployment_info'] = {'exists': False}
        if not args.json: status('deployment_info.json', WARN, 'missing (will be created on next deploy)')

    # 5. Database presence
    db_candidates = [root / 'database' / 'sign_estimation.db', app_dir / 'sign_estimation.db']
    db_found = None
    for cand in db_candidates:
        if cand.exists():
            db_found = cand
            break
    summary['checks']['database'] = str(db_found) if db_found else None
    if not args.json:
        status('database', OK if db_found else FAIL, str(db_found) if db_found else 'not found')

    # 6. Version / hash markers (optional)
    version_files = [p for p in [root / 'VERSION.txt', root / 'version.txt'] if p.exists()]
    version = version_files[0].read_text().strip() if version_files else None
    summary['checks']['version'] = version
    if version and not args.json: status('version', OK, version)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print('\nSummary JSON:')
        print(json.dumps(summary, indent=2))

    # Exit code: fail if critical elements missing
    critical_missing = []
    if not app_dir.is_dir(): critical_missing.append('app_dir')
    if not scripts_ok: critical_missing.append('startup_scripts')
    if not db_found: critical_missing.append('database')
    return 1 if critical_missing else 0

if __name__ == '__main__':
    raise SystemExit(main())
