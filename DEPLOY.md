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

### Useful Flags (Core + Advanced)

| Flag | Purpose |
|------|---------|
| `--force` | Copy all tracked files regardless of hash/mtime |
| `--exclude-db` | Skip database copy (protect remote state) |
| `--no-hash` | Disable hash detection and fall back to mtime |
| `--setup-only` | Only set up path; do not copy files |
| `--bundle` | Build GUI PyInstaller bundle and copy to OneDrive |
| `--bundle-console` | Also build console variant |
| `--pyinstaller-extra ...` | Extra args passed through to PyInstaller |
| `--backup-db` | Create a timestamped database backup in `backups/` (inside deployment) |
| `--backup-retention N` | Keep only newest N backups (used with `--backup-db`) |
| `--collect-logs` | Copy `*.log` files into `logs/` with a summary entry |
| `--prune` | Remove orphaned files in target not present locally anymore |
| `--archive` | Zip the previous deployment state before overwriting (stored in `archives/`) |

Helper wrappers (recommended):
| Script | Behavior |
|--------|----------|
| `scripts/deploy_full.bat` | Runs full safe deploy (`--backup-db --backup-retention 7 --collect-logs --prune --archive`) |
| `scripts/deploy_full.ps1` | PowerShell equivalent of above |
| `scripts/deploy_fast.bat` | Minimal fast incremental deploy (only changed files; add flags manually) |

Examples:
```powershell
# Code-only update, skip DB
python scripts/deploy.py --exclude-db

# Force everything, rebuild bundle, include console variant
action scripts/deploy.py --force --bundle --bundle-console

# Disable hash comparison (mtime only)
python scripts/deploy.py --no-hash
 
# Full robust deploy with all protective features
python scripts/deploy.py --backup-db --backup-retention 7 --collect-logs --prune --archive

# Fast minimal deploy (wrapper)
scripts\deploy_fast.bat

# Full recommended deploy (wrapper)
scripts\deploy_full.bat
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

### Conflict Scenarios & Concurrency
SQLite WAL allows concurrent readers and a single writer. Brief write contention is retried automatically. Last-write-wins on the same row. For heavy simultaneous editing of identical projects coordinate manually. Use `--backup-db` (or the full deploy wrapper) for point-in-time recovery. Consider a server database if write contention becomes routine.

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
## 8. Features Added (Previously "Future")
- Backup rotation (`--backup-db` + `--backup-retention`)
- Optional pruning of removed files (`--prune`)
- Archival of prior deployment (`--archive`)
- Log aggregation (`--collect-logs`)

Future ideas:
- Deployment diff report (human-readable)
- Integrity verification pass (hash audit command)
- Optional encryption of backups

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
**Last Updated:** Added backup/retention, log aggregation, pruning, archiving, helper deploy scripts, and concurrency guidance.

---
## 10. Cross-Platform Virtual Environment Pitfalls (Important)

If you copy this repository (including the `.venv/` folder) between macOS and Windows, the virtual environment metadata will still point to the original OS interpreter. Symptoms:

- Running `pytest` or `python scripts/deploy.py --bundle` fails with a path like `/Users/Name/miniconda3/bin/python.exe` (mixed forward/back slashes) or `C:\...\python.exe` on mac.
- `pyvenv.cfg` inside `.venv/` shows a `home =` path for the other operating system.
- Exports / PyInstaller builds fail immediately before any app code runs.

### Detecting the Problem
1. Run: `python scripts/verify_env.py --json`
2. Look for: `"venv_mismatch": true` in the JSON output or a printed warning `Detected macOS-origin virtualenv on Windows` (or vice versa).
3. In the app UI, a yellow banner appears if a mismatch is detected at startup.

### Fix (Safe & Quick)
From the project root on the current machine:

Windows PowerShell:
```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux:
```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Re-run `python scripts/verify_env.py` to confirm `venv_mismatch` is false. Then rebuild bundles if needed.

Shortcut wrappers (invoke same logic, adds safety prompts):
```powershell
# Windows batch
scripts\rebuild_venv.bat --dry-run
scripts\rebuild_venv.bat --force --yes

# PowerShell wrapper
./scripts/rebuild_venv.ps1 -DryRun
./scripts/rebuild_venv.ps1 -Force -Yes

# Direct Python (JSON summary)
python scripts/rebuild_venv.py --force --yes --json --out rebuild_report.json
```

Smoke test (no deletion) first:
```powershell
scripts\rebuild_venv.bat --dry-run
```
If output looks correct, re-run without --dry-run.

### Why Not Share .venv Across OSes?
The venv folder hardcodes interpreter paths and sometimes compiled artifacts. Cross-platform reuse causes broken shebangs and launcher scripts.

### Preventative Tip
Add `.venv/` to your Git ignore (already present) and avoid zipping it for distribution. Always rebuild per machine.

---
