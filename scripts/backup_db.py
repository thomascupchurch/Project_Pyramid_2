"""Manual / scheduled backup helper.

Usage (Windows PowerShell):
  python scripts/backup_db.py
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import shutil
import sys

BASE = Path(__file__).resolve().parent.parent
DB = BASE / 'sign_estimation.db'
BACKUPS = BASE / 'backups'
BACKUPS.mkdir(exist_ok=True)

def main():
    if not DB.exists():
        print('Database not found:', DB)
        return 1
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    target = BACKUPS / f'sign_estimation_{ts}.db'
    shutil.copy2(DB, target)
    print('Backup created:', target)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
