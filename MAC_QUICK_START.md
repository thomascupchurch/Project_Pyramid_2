# macOS Quick Start Guide

Fast reference for running the Sign Estimation Application on macOS.

---
## 1. Prerequisites

| Requirement | Recommended | Notes |
|-------------|-------------|-------|
| macOS       | 12+ (Monterey) | Works on Intel & Apple Silicon |
| Python      | 3.10 – 3.13  | Use `python3 --version` |
| Homebrew    | Latest       | For native cairo libs (SVG rendering) |
| OneDrive    | New client (`~/Library/CloudStorage/OneDrive-*`) | Auto-detected |

Install Homebrew (if missing):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

---
## 2. Get the Project
```bash
# Clone or copy into a (shared) OneDrive folder if you want team access
cd ~/Library/CloudStorage/OneDrive-<OrgName>/
# or any working directory
git clone <your-repo-url> Project_Pyramid_2
cd Project_Pyramid_2
```

---
## 3. First Launch (Creates Virtual Env Automatically)
```bash
chmod +x start_app.sh          # first time only
./start_app.sh
```
This will:
- Create `.venv` if absent
- Install/refresh dependencies if `requirements.txt` changed
- Start the Dash server on `http://127.0.0.1:8050`

Override host/port:
```bash
SIGN_APP_HOST=0.0.0.0 SIGN_APP_PORT=8060 ./start_app.sh
```

Auto-import a CSV (only if DB empty):
```bash
SIGN_APP_INITIAL_CSV=Book2.csv ./start_app.sh
```

---
## 4. Enabling SVG (Cairo) Rendering (Optional but Recommended)
SVG logos & sign images in PDF exports require native cairo + pango libs.
```bash
brew install cairo pango libffi pkg-config
pip install --force-reinstall cairosvg
```
If the libs are still not found (rare):
```bash
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH}"
```
Then re-run:
```bash
./start_app.sh
```

Disable SVG rasterization (fallback text/logo header only):
```bash
DISABLE_SVG_RENDER=1 ./start_app.sh
```

---
## 5. Verify Environment
```bash
python scripts/verify_env.py
```
Look for:
- `[OK] cairosvg functional render test` (SVG ready)
- Warnings provide remediation steps.

---
## 6. OneDrive Path Detection
If you do not set `ONEDRIVE_SYNC_DIR`, the app will attempt to locate OneDrive under:
- `~/Library/CloudStorage/OneDrive-*`
- `~/OneDrive` (legacy)

Manually override:
```bash
export ONEDRIVE_SYNC_DIR="/Users/you/Library/CloudStorage/OneDrive-OrgName/SignEstimationApp"
./start_app.sh
```

---
## 7. Deployment (Copy to Shared OneDrive)
From a development checkout:
```bash
python scripts/deploy.py --onedrive-path "~/Library/CloudStorage/OneDrive-OrgName/SignEstimationApp"
```
(Omit `--onedrive-path` to let auto-detect try; you will be prompted / config file created.)

Team members then just:
```bash
cd ~/Library/CloudStorage/OneDrive-OrgName/SignEstimationApp
./start_app.sh
```

---
## 8. Useful Environment Variables
| Variable | Purpose | Example |
|----------|---------|---------|
| SIGN_APP_DB | Alternate DB file | `SIGN_APP_DB=custom.db` |
| SIGN_APP_HOST | Bind interface | `0.0.0.0` |
| SIGN_APP_PORT | Port number | `8060` |
| SIGN_APP_INITIAL_CSV | One-time bootstrap import | `Book2.csv` |
| DISABLE_SVG_RENDER | Skip SVG rasterization | `1` |
| CAIROSVG_BACKEND | Force backend (e.g. pycairo) | `pycairo` |
| ONEDRIVE_SYNC_DIR | Explicit OneDrive root | `/Users/me/Library/CloudStorage/OneDrive-Org/App` |
| DYLD_FALLBACK_LIBRARY_PATH | Native lib lookup path | `/opt/homebrew/lib` |

---
## 9. Updating Dependencies
After editing `requirements.txt`, next run of `./start_app.sh` auto reinstalls. Force manual reinstall:
```bash
source .venv/bin/activate
pip install -r requirements.txt --upgrade
```

---
## 10. Troubleshooting
| Symptom | Cause | Fix |
|---------|-------|-----|
| `cairosvg` import error | Missing native cairo libs | Run brew install command above |
| PDF logo text fallback only | SVG raster disabled or libs missing | Install libs or unset `DISABLE_SVG_RENDER` |
| Port already in use | Another process using port | `SIGN_APP_PORT=8061 ./start_app.sh` |
| Slow first launch | Dependency build wheels | Subsequent launches are faster |
| No OneDrive path found | Non-standard install location | Set `ONEDRIVE_SYNC_DIR` manually |

Detailed diagnostics:
```bash
python scripts/verify_env.py
```

---
## 11. Clean Reset
```bash
rm -rf .venv
find . -name "__pycache__" -exec rm -rf {} +
./start_app.sh
```
(Does not delete your `sign_estimation.db`.)

---
## 12. Security & LAN Sharing
To allow coworkers on the same LAN to access your machine:
```bash
SIGN_APP_HOST=0.0.0.0 SIGN_APP_PORT=8050 ./start_app.sh
```
Share your Mac's LAN IP: `http://<your-ip>:8050`

(Optional) Add a reverse proxy + TLS (nginx / Caddy) for advanced deployments.

---
## 13. PDF Diagnostic Field
`svg_render_enabled` (in PDF diagnostics) indicates whether at least one SVG was successfully rasterized this session (logo or appendix image). Use it to confirm your cairo setup.

---
## 14. Quick Copy/Paste Recap
```bash
chmod +x start_app.sh
./start_app.sh
brew install cairo pango libffi pkg-config
pip install --force-reinstall cairosvg
./start_app.sh
python scripts/verify_env.py
```

---
**Happy estimating on macOS!**
