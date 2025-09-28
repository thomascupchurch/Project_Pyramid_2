#!/usr/bin/env python3
"""
Sync script for Sign Estimation Application database.
Keeps local and OneDrive databases synchronized.
"""

import sys
import os
import argparse
from pathlib import Path

# Add utils to path
sys.path.append(str(Path(__file__).parent.parent / "utils"))

try:
    from onedrive import OneDriveManager
except ImportError:
    print("Error: OneDrive utilities not found. Please check your installation.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Sync Sign Estimation App Database")
    parser.add_argument("--check-only", action="store_true",
                       help="Only check sync status without syncing")
    
    args = parser.parse_args()
    
    # Initialize manager
    project_root = Path(__file__).parent.parent
    onedrive_manager = OneDriveManager(local_path=project_root)
    
    print("🔄 Database Sync Tool")
    print("=" * 30)
    
    # Check status
    status = onedrive_manager.get_status()
    
    if status["status"] != "configured":
        print("❌ OneDrive not configured. Run deploy.py first.")
        return 1
    
    print(f"OneDrive Path: {status['path']}")
    print(f"Database Status: {status['database_status']}")
    
    if args.check_only:
        return 0
    
    # Perform sync
    success, message = onedrive_manager.sync_database()
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
