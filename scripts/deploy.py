#!/usr/bin/env python3
"""
Deployment script for Sign Estimation Application.
Handles deployment to OneDrive shared folders.
"""

import sys
import os
import argparse
import platform
from pathlib import Path

# Add utils to path
sys.path.append(str(Path(__file__).parent.parent / "utils"))

from onedrive import OneDriveManager
from database import DatabaseManager

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
    parser.add_argument("--backup-db", action="store_true", help="Create timestamped backup of existing remote DB before overwrite")
    parser.add_argument("--backup-retention", type=int, default=10, help="Number of recent DB backups to retain (default 10, 0 disables pruning)")
    parser.add_argument("--collect-logs", action="store_true", help="Copy *.log files to OneDrive logs folder and record summary")
    parser.add_argument("--prune", action="store_true", help="Remove orphaned files in OneDrive app/ that are not in current source (uses previous manifest or current scan)")
    parser.add_argument("--archive", action="store_true", help="Before deploying, zip current OneDrive app/ folder to archives/app_YYYYmmdd_HHMMSS.zip")
    
    args = parser.parse_args()
    
    # Initialize managers
    project_root = Path(__file__).parent.parent
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
            print("✅ Bundle build/copy complete")
        except Exception as build_err:
            print(f"⚠️  Bundle build failed: {build_err}")

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
