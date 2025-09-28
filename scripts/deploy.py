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
                       help="Force deployment of all files")
    parser.add_argument("--setup-only", action="store_true",
                       help="Only setup OneDrive path without deploying")
    
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
    success, message = onedrive_manager.deploy_to_onedrive(force=args.force)
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
        return 1
    
    # Create startup scripts
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
