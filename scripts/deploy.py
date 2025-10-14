#!/usr/bin/env python3
"""
Deployment script for Sign Estimation Application.
Handles deployment to OneDrive shared folders.
"""

import sys
import os
import argparse
import platform
import datetime
from pathlib import Path

# We'll import project modules lazily after dependency preflight to avoid immediate failures.

def _dependency_preflight(require_bundle: bool, allow_degraded: bool):
    """Check that dependencies are present.

    Core (always required): pandas, dash, plotly, dash_cytoscape.
    Extended (export/render): reportlab, cairosvg.

    If allow_degraded True, missing extended deps become warnings not fatal.
    Returns (ok, problems_list, warnings_list)
    """
    core = ['pandas','dash','plotly','dash_cytoscape']
    extended = ['reportlab','cairosvg']
    problems = []
    warnings = []
    for mod in core:
        try:
            __import__(mod)
        except Exception as e:
            problems.append(f"{mod} (import failed: {e}")
    for mod in extended:
        try:
            __import__(mod)
        except Exception as e:
            if allow_degraded:
                warnings.append(f"{mod} (degraded: {e}")
            else:
                problems.append(f"{mod} (import failed: {e}")
    if require_bundle:
        try:
            import PyInstaller  # noqa: F401
        except Exception:
            problems.append('PyInstaller (module not found)')
    return (len(problems) == 0, problems, warnings)

def main():
    parser = argparse.ArgumentParser(description="Deploy Sign Estimation App to OneDrive")
    parser.add_argument("--onedrive-path", required=False,
                       help="Path to OneDrive shared folder (autodetect if omitted)")
    parser.add_argument("--force", action="store_true", 
                       help="Force deployment of all files (ignore cached hashes)")
    parser.add_argument("--setup-only", action="store_true",
                       help="Only setup OneDrive path without deploying")
    parser.add_argument("--exclude-db", action="store_true",
                       help="Skip copying database file during deployment")
    parser.add_argument("--no-hash", action="store_true",
                       help="Disable hash-based change detection (fallback to mtime)")
    parser.add_argument("--bundle", action="store_true",
                       help="Build PyInstaller GUI bundle (sign_estimator.spec) and copy to OneDrive 'bundle' folder")
    parser.add_argument("--bundle-console", action="store_true",
                       help="Build PyInstaller console bundle (sign_estimator_console.spec) as well")
    parser.add_argument("--pyinstaller-extra", nargs=argparse.REMAINDER,
                       help="Extra args passed to pyinstaller after spec (advanced)")
    parser.add_argument("--strict-bundle", action="store_true",
                       help="Fail deployment if cytoscape assets still missing after auto-repair (prevents distributing broken bundle)")
    parser.add_argument("--allow-degraded", action="store_true",
                       help="Allow deployment to proceed even if optional export libs (cairosvg/reportlab) missing; features will be degraded")
    parser.add_argument("--backup-db", action="store_true", help="Create timestamped backup of existing remote DB before overwrite")
    parser.add_argument("--backup-retention", type=int, default=10, help="Number of recent DB backups to retain (default 10, 0 disables pruning)")
    parser.add_argument("--collect-logs", action="store_true", help="Copy *.log files to OneDrive logs folder and record summary")
    parser.add_argument("--prune", action="store_true", help="Remove orphaned files in OneDrive app/ that are not in current source (uses previous manifest or current scan)")
    parser.add_argument("--archive", action="store_true", help="Before deploying, zip current OneDrive app/ folder to archives/app_YYYYmmdd_HHMMSS.zip")
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent

    # Dependency preflight
    need_bundle = bool(args.bundle or args.bundle_console)
    allow_degraded = bool(args.allow_degraded or os.environ.get('SIGN_APP_ALLOW_DEGRADED'))
    ok, probs, warns = _dependency_preflight(require_bundle=need_bundle, allow_degraded=allow_degraded)
    if probs:
        print('❌ Missing or broken dependencies:')
        for p in probs:
            print('   -', p)
        print('\nRemediation (PowerShell):')
        print('  python -m pip install --upgrade pip wheel setuptools')
        if need_bundle:
            print('  python -m pip install -r requirements-dev.txt')
        else:
            print('  python -m pip install -r requirements.txt')
        if allow_degraded:
            print('(Degraded allowed, but core failures prevent deploy.)')
        return 3
    if warns:
        print('⚠️  Proceeding in degraded mode (some export features disabled):')
        for w in warns:
            print('   -', w)

    # Safe to import now
    sys.path.append(str(project_root / "utils"))
    from onedrive import OneDriveManager  # type: ignore
    from database import DatabaseManager  # type: ignore

    onedrive_manager = OneDriveManager(local_path=project_root)
    db_manager = DatabaseManager(str(project_root / "sign_estimation.db"))
    
    print("🚀 Sign Estimation App Deployment")
    print("=" * 40)
    
    # Setup OneDrive path
    # Auto-detect OneDrive path if not provided (Windows heuristic)
    target_path = args.onedrive_path
    if not target_path:
        if platform.system().lower() == 'windows':
            # Common OneDrive base env var names
            env_candidates = [
                os.environ.get('OneDriveCommercial'),
                os.environ.get('OneDriveConsumer'),
                os.environ.get('OneDrive'),
            ]
            userprofile = os.environ.get('USERPROFILE')
            if not any(env_candidates) and userprofile:
                # Fallback guess
                guess = Path(userprofile) / 'OneDrive'
                if guess.exists():
                    env_candidates.append(str(guess))
            base = next((p for p in env_candidates if p and Path(p).exists()), None)
            if base:
                target_path = str(Path(base) / 'SignEstimationApp')
                print(f"🔍 Auto-detected OneDrive base: {base}")
            else:
                print("⚠️  Could not auto-detect OneDrive path. Please supply --onedrive-path.")
        if not target_path:
            return 1

    print(f"Setting up OneDrive path: {target_path}")
    success = onedrive_manager.setup_onedrive_path(target_path)
    
    if not success:
        print("❌ Failed to setup OneDrive path")
        return 1
    
    print("✅ OneDrive path configured successfully")
    
    if args.setup_only:
        print("Setup complete. Use --deploy to deploy files.")
        return 0
    
    # Optimize database for OneDrive
    print("Optimizing database for OneDrive...")
    db_manager.optimize_for_onedrive()
    print("✅ Database optimized")
    
    # Deploy application
    print("Deploying application files...")
    success, message = onedrive_manager.deploy_to_onedrive(
        force=args.force,
        exclude_db=args.exclude_db,
        use_hash=not args.no_hash,
        backup_db=args.backup_db,
        backup_retention=args.backup_retention,
        collect_logs=args.collect_logs,
        prune_orphans=args.prune,
        archive_previous=args.archive
    )
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
        return 1
    
    # Optionally build PyInstaller bundles
    if args.bundle or args.bundle_console:
        print("Building PyInstaller bundle(s)...")
        import shutil as _shutil
        import subprocess as _subprocess
        dist_dir = project_root / 'dist'
        bundle_target_root = Path(onedrive_manager.onedrive_path) / 'bundle'
        bundle_target_root.mkdir(exist_ok=True)
        def _run_build(spec_file):
            cmd = [sys.executable, '-m', 'PyInstaller', spec_file]
            if args.pyinstaller_extra:
                cmd.extend(args.pyinstaller_extra)
            print("Running:", ' '.join(cmd))
            result = _subprocess.run(cmd, cwd=project_root)
            if result.returncode != 0:
                raise RuntimeError(f"PyInstaller build failed for {spec_file}")
        try:
            if args.bundle:
                _run_build('sign_estimator.spec')
            if args.bundle_console:
                _run_build('sign_estimator_console.spec')
            # Copy resulting folders
            if dist_dir.exists():
                for d in dist_dir.iterdir():
                    if d.is_dir() and (d.name.startswith('sign_estimator')):
                        target_dir = bundle_target_root / d.name
                        if target_dir.exists():
                            _shutil.rmtree(target_dir)
                        _shutil.copytree(d, target_dir)
                        print(f"Copied bundle: {d.name} -> {target_dir}")
            # Post-copy verification: dash_cytoscape/package.json presence
            def _verify_dash_c(target_root: Path):
                pkg = target_root / 'dash_cytoscape' / 'package.json'
                return pkg.exists()
            problems = []
            for variant in ['sign_estimator','sign_estimator_console']:
                bdir = bundle_target_root / variant
                if bdir.exists():
                    if _verify_dash_c(bdir):
                        print(f"✅ cytoscape resources ok in {variant}")
                    else:
                        # Attempt auto-repair by copying from site-packages if available
                        try:
                            import importlib.util as _ilu, pathlib as _pl
                            spec_dc = _ilu.find_spec('dash_cytoscape')
                            if spec_dc and spec_dc.origin:
                                src_dir = _pl.Path(spec_dc.origin).parent
                                dst_dir = bdir / 'dash_cytoscape'
                                dst_dir.mkdir(exist_ok=True)
                                for fname in ['package.json','metadata.json']:
                                    s = src_dir / fname
                                    if s.exists():
                                        _shutil.copy2(s, dst_dir / fname)
                                # copy core js assets if missing
                                for fname in ['dash_cytoscape.min.js','dash_cytoscape.dev.js','dash_cytoscape_extra.min.js','dash_cytoscape_extra.dev.js']:
                                    s = src_dir / fname
                                    if s.exists() and not (dst_dir / fname).exists():
                                        _shutil.copy2(s, dst_dir / fname)
                        except Exception as _fixerr:
                            print(f"⚠️  Auto-repair attempt failed for {variant}: {_fixerr}")
                        if _verify_dash_c(bdir):
                            print(f"🛠️  Auto-repaired cytoscape resources in {variant}")
                        else:
                            problems.append(variant)
            if problems:
                print("❌ Missing dash_cytoscape/package.json in: " + ', '.join(problems))
                print("   Remediation steps:")
                print("     1) Close any running sign_estimator*.exe processes")
                print("     2) Delete build/ and dist/ folders")
                print("     3) (Optional) python -m pip install --upgrade dash-cytoscape")
                print("     4) Re-run deploy with --bundle")
                if args.strict_bundle:
                    print("🚫 --strict-bundle enabled: aborting deployment due to incomplete bundle")
                    return 2
                else:
                    print("   (Continuing without abort; affected bundles may degrade or stub metadata at runtime.)")
            # Also copy one-file EXE if present in dist (convenience for click-to-run)
            try:
                onefile_src = dist_dir / 'sign_estimator.exe'
                if onefile_src.exists():
                    onefile_dst = bundle_target_root / 'sign_estimator_onefile.exe'
                    _shutil.copy2(onefile_src, onefile_dst)
                    print(f"Copied one-file EXE -> {onefile_dst}")
            except Exception as _onefile_err:
                print(f"⚠️  Could not copy one-file EXE: {_onefile_err}")

            print("✅ Bundle build/copy complete")
            # Post-build export capability summary
            print("\n📦 Export Capability Summary:")
            def _probe(name, import_name=None, extra_check=None):
                mod = import_name or name
                try:
                    __import__(mod)
                    if extra_check:
                        return extra_check()
                    return True, None
                except Exception as e:  # noqa: BLE001
                    return False, str(e)
            capabilities = []
            report_items = [
                ("PDF Export (reportlab)", "reportlab"),
                ("SVG Rasterization (cairosvg)", "cairosvg"),
                ("Static Plotly Image (kaleido)", "kaleido"),
                ("Image Processing (Pillow)", "PIL"),
                ("Excel Export (openpyxl)", "openpyxl"),
            ]
            for label, mod in report_items:
                ok, err = _probe(mod)
                status = "OK" if ok else "MISSING"
                capabilities.append((label, status, err))
            width = max(len(c[0]) for c in capabilities) + 2
            for label, status, err in capabilities:
                if status == "OK":
                    print(f"  - {label.ljust(width)}: ✅ {status}")
                else:
                    short = (err or "").split('\n')[0][:80]
                    print(f"  - {label.ljust(width)}: ❌ {status} ({short})")
            degraded = [c for c in capabilities if c[1] != 'OK']
            if degraded:
                print("\n⚠️  One or more export features unavailable. Core estimating still functions.")
                print("   To enable all features install missing libs and re-run deploy:")
                print("   python -m pip install reportlab cairosvg kaleido pillow openpyxl")
                print("   (Cairo native DLLs may be required for cairosvg on Windows.)")
        except Exception as build_err:
            print(f"⚠️  Bundle build failed: {build_err}")

    # Create / update deployment info with version stamp
    try:
        version_file = project_root / 'VERSION.txt'
        version = version_file.read_text().strip() if version_file.exists() else '0.0.0'
    except Exception:
        version = '0.0.0'
    # Augment deployment_info.json after deploy
    try:
        info_path = Path(onedrive_manager.onedrive_path) / 'deployment_info.json'
        deployment_info = {}
        if info_path.exists():
            import json as _json
            try:
                deployment_info = _json.loads(info_path.read_text())
            except Exception:
                deployment_info = {}
        deployment_info['version'] = version
        deployment_info['deployed_at'] = datetime.datetime.utcnow().isoformat()+'Z'
        deployment_info['platform'] = platform.system()
        import json as _json
        info_path.write_text(_json.dumps(deployment_info, indent=2))
        print(f"📄 Deployment info updated (version {version})")
    except Exception as _e:
        print(f"⚠️  Could not write deployment info: {_e}")

    # Create startup scripts (enhanced version will detect bundle)
    print("Creating startup scripts...")
    startup_success = onedrive_manager.create_startup_script()
    
    if startup_success:
        print("✅ Startup scripts created")
    else:
        print("⚠️  Failed to create startup scripts")
    
    # Show deployment status
    status = onedrive_manager.get_status()
    print("\n📊 Deployment Status:")
    print(f"   OneDrive Path: {status['path']}")
    print(f"   Last Deployment: {status['last_deployment']}")
    print(f"   Files Deployed: {status['files_deployed']}")
    print(f"   Database Status: {status['database_status']}")
    
    print("\n🎉 Deployment completed successfully!")
    print("\nNext steps:")
    print(f"1. Navigate to: {target_path}")
    print("2. Run 'start_app.bat' or 'start_app.ps1' to launch the application")
    print("3. Share the OneDrive folder with your team members")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
