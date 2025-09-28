"""Central configuration for Sign Estimation Tool.

Allows easy tweaking when deploying for co-workers on Windows over LAN / OneDrive.
Environment variables override defaults so you can adapt without editing code.
"""
from __future__ import annotations
import os
from pathlib import Path

# Base directory (shared folder root)
BASE_DIR = Path(__file__).resolve().parent

# Database path (relative so it stays inside synced folder)
DB_FILENAME = os.getenv("SIGN_APP_DB_FILENAME", "sign_estimation.db")
DATABASE_PATH = str(BASE_DIR / DB_FILENAME)

# Network host/port (0.0.0.0 so others on LAN can reach it)
APP_HOST = os.getenv("SIGN_APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("SIGN_APP_PORT", "8050"))

# Enable/disable Dash debug (should be False for shared use)
DASH_DEBUG = os.getenv("SIGN_APP_DEBUG", "0").lower() in {"1","true","yes"}

# Optional: seconds between lightweight auto-backups (0 disables)
AUTO_BACKUP_INTERVAL_SEC = int(os.getenv("SIGN_APP_AUTO_BACKUP_SEC", "0"))
BACKUP_DIR = Path(os.getenv("SIGN_APP_BACKUP_DIR", str(BASE_DIR / "backups")))

def ensure_backup_dir():
    if AUTO_BACKUP_INTERVAL_SEC > 0:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
