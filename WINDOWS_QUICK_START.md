# Windows Quick Start

> Fast guide to run the Sign Estimation Application from a synced OneDrive folder on any Windows 10/11 workstation.

---
## 1. Prerequisites

| Item | Minimum | Notes |
|------|---------|-------|
| Windows | 10 (21H2) or 11 | 64-bit recommended |
| Python | 3.11+ (x64) | Install from https://www.python.org/downloads/, check "Add Python to PATH" |
| OneDrive | Signed in & synced | Ensure the project folder is fully synced before launching |
| Disk Space | ~500 MB | First run caches virtual environment & packages |

### Verify Python
Open PowerShell:
```powershell
py -3 --version  # preferred
python --version # fallback
```
If neither command works, install Python 3.11+ before proceeding.

---
## 2. Folder Layout
You should have a repo folder similar to:
```
Project_Pyramid_2\
  app.py
  run_app.bat
  start_windows.bat
  start_app.ps1
  requirements.txt
  sign_estimation.db (created/updated automatically)
  assets\ ...
```
If you only have database and launcher scripts, re‑sync or clone the full repository.

---
## 3. First Launch (Fast Path)
From the project root (within OneDrive):
```powershell
./run_app.bat
```
What happens automatically:
1. Virtual environment `.venv` created if missing.
2. Dependencies installed (if Dash not yet present).
3. App starts on http://localhost:8050

> Keep the window open. Closing it stops the server.

### Alternate Launcher
Use the more verbose installer / launcher:
```powershell
./start_windows.bat
```
This also bootstraps the environment; choose whichever you prefer.

### PowerShell Per-User Venv Launcher
If you prefer a per-user (outside sync) env to reduce OneDrive churn:
```powershell
./start_app.ps1
```
This builds a venv under `%LOCALAPPDATA%\SignEstimator\venv` and reuses it across copies.

---
## 4. Environment Tweaks
You can override defaults before launching:
```powershell
$env:SIGN_APP_PORT=8060
$env:SIGN_APP_DB="shared_signs.db"
./run_app.bat
```
Common variables:
- `SIGN_APP_PORT` : Port (default 8050)
- `SIGN_APP_DB`   : SQLite file name or path
- `SIGN_APP_INITIAL_CSV` : Auto-import a CSV on first run
- `SIGN_APP_HIDE_ENV_NOTICE=1` : Suppress environment banner

Batch equivalent:
```cmd
SET SIGN_APP_PORT=8060
SET SIGN_APP_DB=shared_signs.db
run_app.bat
```

To hide the environment banner via flag:
```powershell
./run_app.bat /HIDEENV
./start_windows.bat /HIDEENV
./start_app.ps1 -HideEnvNotice
```

---
## 5. Upgrading / Reinstalling
If dependencies change (after pulling new code):
```powershell
# Simple: remove venv then relaunch
Remove-Item -Recurse -Force .venv
./run_app.bat
```
Or force reinstall via PowerShell launcher:
```powershell
./start_app.ps1 -ForceReinstall
```

---
## 6. Troubleshooting
| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `Python was not found` | Python not installed / PATH missing | Install Python 3.11+, re-open shell |
| Stuck on old path: `/Users/.../miniconda3` warning | Stale interpreter hint from prior OS | Ignored automatically; just continue |
| Port already in use | Another instance running | Set `SIGN_APP_PORT` to a free port |
| App starts then exits quickly | Dependency install failed | Re-run, inspect first error block; maybe delete `.venv` |
| Slow first launch | One-time dependency wheel build | Subsequent launches are fast |
| DB locked errors | Two instances writing same DB | Close one or use separate DB file |

Show installed version list:
```powershell
"Python: $(py -3 --version)"; Get-ChildItem .venv\Lib\site-packages | Select-Object -First 5
```

---
## 7. Multi-Machine (OneDrive) Tips
- Let OneDrive finish syncing before launching on a second machine.
- Avoid running the app on two machines simultaneously against the same DB if you perform writes.
- Consider using a distinct DB per active user (`SIGN_APP_DB=thomas_local.db`) and merging later.

---
## 8. Clean Reset
To completely reset the environment (keeping data):
```powershell
Stop-Process -Name python -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
Remove-Item -Force requirements_cache.txt -ErrorAction SilentlyContinue
./run_app.bat
```
If you also want to start with a fresh DB:
```powershell
Remove-Item sign_estimation.db -ErrorAction SilentlyContinue
./run_app.bat
```

---
## 9. Optional: Portable Zip Distribution
1. Prepare on a primary machine: ensure `.venv` is built and app runs.
2. (Optional) Delete large cache dirs you don't need (e.g., `__pycache__`).
3. Zip the folder (excluding `.venv\Scripts\pip.exe.cache` if present).
4. On target machine, unzip, delete `.venv` (path differences), then run `run_app.bat` to recreate.

---
## 10. Support Checklist (When Asking for Help)
Include:
- Output of `py -3 --version`
- Which launcher used (`run_app.bat`, `start_windows.bat`, `start_app.ps1`)
- Last 30 lines of console output
- Any recent edits (schema, requirements)

---
## 11. IT Deployment (Managed Rollout)
This section is for IT / administrators preparing the app for a larger internal audience.

### Deployment Models
| Model | When to Use | Pros | Cons |
|-------|-------------|------|------|
| Shared OneDrive Folder (current) | Small team, low concurrency | Simple, no server infra | File locking risk, manual updates |
| Central Network Share (SMB) | Multiple users on LAN | Faster sync than cloud round‑trip | Still SQLite locking constraints |
| Local Copy Per User + Sync DB | Users need speed + shared pricing | Low read contention | Harder to merge divergent DB writes |
| Future: Central Service (Flask/Gunicorn) | >10 concurrent users | Centralized control, backups | Requires Windows service / server |

### Recommended Baseline
1. Designate a "golden" workstation for updating code.
2. After testing, commit/push (or sync) updates to the shared folder.
3. Notify users to relaunch (auto-venv logic will reconcile dependencies).
4. Schedule nightly DB backup.

### Pre-Provisioning Script (Optional)
IT can warm the environment so first user launch is instant:
```powershell
cd "<SharedPath>\Project_Pyramid_2"
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
py -3 -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```
Then set the folder to Read/Write for the team (avoid locking `sign_estimation.db` while provisioning).

### Central Database Option
You may relocate the SQLite DB to a central path:
```powershell
$env:SIGN_APP_DB="\\fileserver01\SignEstimating\sign_estimation.db"
./run_app.bat
```
Considerations:
- Enable regular backups (copy while app idle; SQLite is a single-file DB).
- Avoid hosting DB on high-latency cloud path if many writes occur.
- Monitor file size growth; archive old snapshots/estimates if needed.

### Backup Strategy
Minimal PowerShell scheduled task (daily 11:55 PM):
```powershell
$src = "\\fileserver01\SignEstimating\sign_estimation.db"
$dst = "D:\Backups\SignEstimating"
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Copy-Item $src (Join-Path $dst ("sign_estimation_" + (Get-Date -Format 'yyyyMMdd_HHmm') + ".db"))
```
Retain last N copies (add pruning logic if desired).

### Environment Variables via System Scope
Set org-wide defaults (System Properties > Environment Variables) or through Group Policy Preferences:
- `SIGN_APP_PORT=8050`
- `SIGN_APP_HIDE_ENV_NOTICE=1`
- `SIGN_APP_DB=\\fileserver01\SignEstimating\sign_estimation.db`

### Hardening Ideas (Future)
- Move to PostgreSQL for multi-user write concurrency.
- Wrap with Windows Service hosting (NSSM or `python -m waitress`).
- Add authentication (reverse proxy with IIS or nginx).
- Central log collection (write logs to `logs/` with rotation).

### Change Management Checklist
| Step | Owner | Complete |
|------|-------|----------|
| Pull latest code to golden machine | Dev Lead |  |
| Run smoke tests (`pytest -k basic`) | Dev Lead |  |
| Launch app & verify logo/export | QA |  |
| Backup production DB | IT |  |
| Publish updated folder | IT |  |
| Notify users (changelog) | Dev Lead |  |

---
Happy estimating!

---
## 12. Automated Cleanup / Uninstall
Use the provided PowerShell cleanup script for safe removal of local environment artifacts.

Dry run (shows what would be deleted):
```powershell
powershell -ExecutionPolicy Bypass -File cleanup_windows.ps1 -DryRun
```
Remove only the virtual environment:
```powershell
powershell -File cleanup_windows.ps1
```
Remove venv + database + backups (prompted):
```powershell
powershell -File cleanup_windows.ps1 -RemoveDb -PurgeBackups
```
Full purge (no prompts):
```powershell
powershell -File cleanup_windows.ps1 -RemoveDb -PurgeBackups -PurgeExports -Force
```
Flags:
- `-RemoveDb`       Delete current database (respects SIGN_APP_DB)
- `-PurgeBackups`   Delete sign_estimation.backup*.db files
- `-PurgeExports`   Delete files under exports/ (report outputs)
- `-Force`          Skip confirmation prompt
- `-DryRun`         Preview actions only

Always run with `-DryRun` first in shared or critical folders.
