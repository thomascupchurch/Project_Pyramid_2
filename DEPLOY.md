# Deployment & Distribution Guide

This document explains how to deploy and update the Sign Estimation Application to a shared OneDrive folder and how coworkers should launch it.

## Overview

Two distribution modes are supported:

1. Source Deployment (default): Copies Python source files + database to OneDrive. Coworkers need Python installed. Startup scripts auto-create a per-user virtual environment outside OneDrive.
2. Bundled Deployment (optional): Builds a PyInstaller bundle (`sign_estimator` or `sign_estimator_console`) and copies it to OneDrive. Coworkers can run without a Python installation.

You can use either or both simultaneously. Startup scripts will prefer a bundle if present.

---
## 1. Initial Deployment (Source Mode)

From your development checkout root:

```powershell
python scripts/deploy.py --onedrive-path "C:\\Users\\<you>\\OneDrive - Company\\SignEstimationApp"
```

If you omit `--onedrive-path` on Windows the script attempts to auto-detect the base OneDrive location and creates `SignEstimationApp`.

What this does:
- Creates required directories under the target: `app/`, `database/`, `assets/`, `logs/`
- Copies allowed application files (filters via include/exclude patterns)
- Copies `sign_estimation.db` (unless `--exclude-db` specified)
- Creates `deployment_info.json`, `file_hashes.json`
- Generates `start_app.bat` and `start_app.ps1`

Subsequent deployments only copy changed files using SHA256 hashes. Use `--force` to override.

### Useful Flags

| Flag | Purpose |
|------|---------|
| `--force` | Copy all tracked files regardless of hash/mtime |
| `--exclude-db` | Skip database copy (protect remote state) |
| `--no-hash` | Disable hash detection and fall back to mtime |
| `--setup-only` | Only set up path; do not copy files |
| `--bundle` | Build GUI PyInstaller bundle and copy to OneDrive |
| `--bundle-console` | Also build console variant |
| `--pyinstaller-extra ...` | Extra args passed through to PyInstaller |

Examples:
```powershell
# Code-only update, skip DB
python scripts/deploy.py --exclude-db

# Force everything, rebuild bundle, include console variant
action scripts/deploy.py --force --bundle --bundle-console

# Disable hash comparison (mtime only)
python scripts/deploy.py --no-hash
```

---
## 2. Bundled Deployment (Optional)

Build and copy bundle(s):
```powershell
python scripts/deploy.py --bundle
# or include console window build
action scripts/deploy.py --bundle --bundle-console
```

The bundles are copied under `bundle/` inside the OneDrive deployment root. Example structure:
```
SignEstimationApp/
  app/
  database/
  bundle/
    sign_estimator/
      sign_estimator.exe
    sign_estimator_console/
      sign_estimator_console.exe
```

Startup scripts auto-detect these and launch the GUI build first; if not present they fall back to source mode.

---
## 3. Coworker Instructions (Source or Bundle)

1. Open the shared OneDrive folder (e.g., `SignEstimationApp`).
2. Double-click `start_app.bat` (Windows) OR right-click `start_app.ps1` → Run with PowerShell.
3. First run (source mode): it creates a virtual environment in `%LOCALAPPDATA%\SignEstimator\venv` and installs dependencies if needed.
4. Browser: navigate to http://localhost:8050 (or whichever port shown). Bundle will open the same service internally.

### Requirements for Source Mode
- Windows 10/11
- Python 3.11+ on PATH
- OneDrive sync client running

### No Python? Use Bundle
If Python isn't installed, build a bundle so coworkers can launch without dependencies. They still share the same SQLite DB in `database/` unless you instruct otherwise.

---
## 4. Database Handling

- Default shared database path: `database/sign_estimation.db`
- To protect a production DB from accidental overwrite, deploy with `--exclude-db` once it's in place.
- To sync database only: `python scripts/sync_db.py` (run from your dev repo, not from inside the OneDrive folder).

### Conflict Scenarios
If two people run source mode and write simultaneously, SQLite WAL usually manages this. For heavy concurrent writes consider migrating to a server database later.

---
## 5. File Change Detection

A manifest `file_hashes.json` stores SHA256 hashes for each deployed file. On subsequent runs only files with changed hashes are recopied. Use `--force` to override or `--no-hash` to revert to modification time checks.

---
## 6. Environment Variables for Runtime

Set before launching (batch):
```bat
set SIGN_APP_PORT=8060
set SIGN_APP_DB=sign_estimation.db
start_app.bat
```
PowerShell:
```powershell
$env:SIGN_APP_PORT=8060
$env:SIGN_APP_DB='sign_estimation.db'
./start_app.ps1
```

For bundle builds you can still set these variables; they are read by the embedded Python runtime.

---
## 7. Troubleshooting

| Issue | Resolution |
|-------|------------|
| Startup script says Python not found | Install Python 3.11+ and re-run |
| Bundle doesn't launch | Verify `bundle/sign_estimator/sign_estimator.exe` exists; rebuild with `--bundle` |
| DB not updating | Ensure OneDrive fully synced; check file timestamps; run `scripts/sync_db.py` |
| Dependencies reinstall each launch | Hash file missing or cannot write to `%LOCALAPPDATA%`; check permissions |
| Port already in use | Set `SIGN_APP_PORT` to another unused port |

---
## 8. Future Enhancements (Ideas)
- Automatic backup rotation of database on each deployment
- Incremental diff report showing removed files
- Optional compression of previous deployments
- Remote log aggregation

---
## 9. Quick Reference Commands

```powershell
# Standard deploy
python scripts/deploy.py

# Deploy without copying DB
python scripts/deploy.py --exclude-db

# Force full redeploy & rebuild bundle
python scripts/deploy.py --force --bundle

# Add console variant too
python scripts/deploy.py --force --bundle --bundle-console

# Only set up folder
python scripts/deploy.py --setup-only
```

---
**Last Updated:** Auto-generated improvements added (hash-based detection, bundle deploy, enhanced startup scripts).
