"""
OneDrive synchronization utilities for the Sign Estimation Application.
Handles deployment and updates to shared OneDrive folders.
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime
import subprocess

class OneDriveManager:
    def __init__(self, local_path=None, onedrive_path=None):
        self.local_path = Path(local_path) if local_path else Path.cwd()
        self.onedrive_path = Path(onedrive_path) if onedrive_path else None
        self.config_file = self.local_path / "onedrive_config.json"
        self.load_config()
    
    def load_config(self):
        """Load OneDrive configuration from config file."""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.onedrive_path = Path(config.get('onedrive_path', ''))
                self.deployment_settings = config.get('deployment_settings', {})
        else:
            self.deployment_settings = {
                'exclude_patterns': [
                    '__pycache__',
                    '*.pyc',
                    '.git',
                    '.vscode',
                    'node_modules',
                    '.env',
                    'development.db'
                ],
                'include_patterns': [
                    '*.py',
                    '*.html',
                    '*.css',
                    '*.js',
                    '*.svg',
                    '*.db',
                    '*.json',
                    '*.txt',
                    '*.md'
                ]
            }
    
    def save_config(self):
        """Save OneDrive configuration to config file."""
        config = {
            'onedrive_path': str(self.onedrive_path) if self.onedrive_path else '',
            'deployment_settings': self.deployment_settings,
            'last_sync': datetime.now().isoformat()
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setup_onedrive_path(self, onedrive_path):
        """Set up the OneDrive deployment path."""
        self.onedrive_path = Path(onedrive_path)
        
        # Create directory structure if it doesn't exist
        if not self.onedrive_path.exists():
            self.onedrive_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.onedrive_path / "app").mkdir(exist_ok=True)
        (self.onedrive_path / "database").mkdir(exist_ok=True)
        (self.onedrive_path / "assets").mkdir(exist_ok=True)
        (self.onedrive_path / "logs").mkdir(exist_ok=True)
        
        self.save_config()
        return True
    
    def should_include_file(self, file_path):
        """Check if a file should be included in deployment."""
        file_path = Path(file_path)
        
        # Check exclude patterns
        for pattern in self.deployment_settings['exclude_patterns']:
            if pattern in str(file_path):
                return False
        
        # Check include patterns
        for pattern in self.deployment_settings['include_patterns']:
            if file_path.suffix == pattern or file_path.name.endswith(pattern.replace('*', '')):
                return True
        
        return False
    
    def deploy_to_onedrive(self, force=False):
        """Deploy the application to OneDrive shared folder."""
        if not self.onedrive_path:
            return False, "OneDrive path not configured"
        
        if not self.onedrive_path.exists():
            return False, f"OneDrive path does not exist: {self.onedrive_path}"
        
        try:
            deployment_log = []
            
            # Copy application files
            for root, dirs, files in os.walk(self.local_path):
                # Skip certain directories
                dirs[:] = [d for d in dirs if not any(pattern in d for pattern in self.deployment_settings['exclude_patterns'])]
                
                for file in files:
                    source_file = Path(root) / file
                    relative_path = source_file.relative_to(self.local_path)
                    
                    if self.should_include_file(source_file):
                        target_file = self.onedrive_path / "app" / relative_path
                        
                        # Create target directory if it doesn't exist
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Copy file if it's new or modified
                        if force or not target_file.exists() or source_file.stat().st_mtime > target_file.stat().st_mtime:
                            shutil.copy2(source_file, target_file)
                            deployment_log.append(f"Copied: {relative_path}")
            
            # Copy database file
            db_source = self.local_path / "sign_estimation.db"
            if db_source.exists():
                db_target = self.onedrive_path / "database" / "sign_estimation.db"
                if force or not db_target.exists() or db_source.stat().st_mtime > db_target.stat().st_mtime:
                    shutil.copy2(db_source, db_target)
                    deployment_log.append("Copied: Database file")
            
            # Create deployment info file
            deployment_info = {
                'deployed_at': datetime.now().isoformat(),
                'deployed_from': str(self.local_path),
                'files_deployed': len(deployment_log),
                'deployment_log': deployment_log
            }
            
            with open(self.onedrive_path / "deployment_info.json", 'w') as f:
                json.dump(deployment_info, f, indent=2)
            
            self.save_config()
            return True, f"Deployed {len(deployment_log)} files to OneDrive"
            
        except Exception as e:
            return False, f"Deployment failed: {str(e)}"
    
    def create_startup_script(self):
        """Create a startup script for easy launching on Windows machines."""
        if not self.onedrive_path:
            return False, "OneDrive path not configured"
        
        # Windows batch file
        batch_content = f"""@echo off
cd /d "{self.onedrive_path / 'app'}"
echo Starting Sign Estimation Application...
python app.py
pause
"""
        
        batch_file = self.onedrive_path / "start_app.bat"
        with open(batch_file, 'w') as f:
            f.write(batch_content)
        
        # PowerShell script
        ps1_content = f"""# Sign Estimation Application Launcher
Set-Location -Path "{self.onedrive_path / 'app'}"
Write-Host "Starting Sign Estimation Application..." -ForegroundColor Green
python app.py
Read-Host "Press Enter to close"
"""
        
        ps1_file = self.onedrive_path / "start_app.ps1"
        with open(ps1_file, 'w') as f:
            f.write(ps1_content)
        
        return True
    
    def sync_database(self):
        """Sync database changes between local and OneDrive."""
        if not self.onedrive_path:
            return False, "OneDrive path not configured"
        
        local_db = self.local_path / "sign_estimation.db"
        remote_db = self.onedrive_path / "database" / "sign_estimation.db"
        
        try:
            # Check which is newer
            if local_db.exists() and remote_db.exists():
                local_time = local_db.stat().st_mtime
                remote_time = remote_db.stat().st_mtime
                
                if local_time > remote_time:
                    # Local is newer, copy to remote
                    shutil.copy2(local_db, remote_db)
                    return True, "Database synced: Local -> OneDrive"
                elif remote_time > local_time:
                    # Remote is newer, copy to local
                    shutil.copy2(remote_db, local_db)
                    return True, "Database synced: OneDrive -> Local"
                else:
                    return True, "Database already in sync"
            elif local_db.exists():
                # Only local exists
                shutil.copy2(local_db, remote_db)
                return True, "Database copied: Local -> OneDrive"
            elif remote_db.exists():
                # Only remote exists
                shutil.copy2(remote_db, local_db)
                return True, "Database copied: OneDrive -> Local"
            else:
                return False, "No database found in either location"
                
        except Exception as e:
            return False, f"Database sync failed: {str(e)}"
    
    def get_status(self):
        """Get current OneDrive sync status."""
        if not self.onedrive_path:
            return {"status": "not_configured"}
        
        if not self.onedrive_path.exists():
            return {"status": "path_not_found", "path": str(self.onedrive_path)}
        
        # Check deployment info
        deployment_info_file = self.onedrive_path / "deployment_info.json"
        if deployment_info_file.exists():
            with open(deployment_info_file, 'r') as f:
                deployment_info = json.load(f)
        else:
            deployment_info = {"deployed_at": "Never"}
        
        # Check database status
        local_db = self.local_path / "sign_estimation.db"
        remote_db = self.onedrive_path / "database" / "sign_estimation.db"
        
        db_status = "no_database"
        if local_db.exists() and remote_db.exists():
            local_time = local_db.stat().st_mtime
            remote_time = remote_db.stat().st_mtime
            if abs(local_time - remote_time) < 2:  # Within 2 seconds
                db_status = "synchronized"
            elif local_time > remote_time:
                db_status = "local_newer"
            else:
                db_status = "remote_newer"
        elif local_db.exists():
            db_status = "local_only"
        elif remote_db.exists():
            db_status = "remote_only"
        
        return {
            "status": "configured",
            "path": str(self.onedrive_path),
            "last_deployment": deployment_info.get("deployed_at", "Never"),
            "database_status": db_status,
            "files_deployed": deployment_info.get("files_deployed", 0)
        }
