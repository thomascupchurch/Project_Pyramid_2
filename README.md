# Sign Estimation Application

A modern Python web application for sign manufacturing cost estimation and project management, built specifically for sign manufacturing companies with teams working on Windows machines with Microsoft 365.

> macOS Support: The project now includes automatic OneDrive path detection on macOS (`~/Library/CloudStorage/OneDrive-*`) and a `start_app.sh` launcher with Homebrew guidance for enabling SVG/Cairo rendering.
> Runtime Health: The app exposes `/health` returning JSON (status, version, python, frozen, cytoscape asset presence).

> New Convenience Features (Oct 2025):
> - Auto‑opens your default browser after a successful startup (PowerShell launcher)
> - Optional `-NoBrowser` flag or `-Minimized` mode to suppress opening / output
> - Desktop & Start Menu shortcut generator (`scripts/create_shortcuts.ps1`)
> - Windows toast notification (if `win10toast` installed) showing the local URL
> - Icon generation utility (`scripts/generate_icon.py`) to build `LSI_Logo.ico` from SVG
- Admin one‑pager exporter to PDF (`scripts/export_admin_onepager_pdf.ps1`) and a two‑apps variant (`scripts/export_admin_twoapps_pdf.ps1`)
- Dual‑launch helper to start two app instances (`start_both_apps.ps1`)

## 🎯 Features

### Core Functionality

- **Project Management**: Create and manage sign installation projects
- **Building Organization**: Organize signs by buildings within projects
- **Sign Types**: Maintain master catalog of available sign types with pricing
- **Sign Groups**: Create reusable groups of signs for common configurations
- **Cost Calculation**: Multiple pricing methods:
  - Unit pricing per sign
  - Price per square foot based on material
  - Custom pricing overrides
- **Tree Visualization**: Visual project hierarchy showing projects → buildings → signs
- **Export Capabilities**: Generate estimates with company branding
- **Sign Type Images**: Attach an image (PNG/JPG/GIF/SVG) to each sign type; thumbnails surface in hover panels for static & interactive trees
   - Embedded in PDF (thumbnail column) and Excel (thumbnail column) exports when images are present

### Pricing Methods

1. **Unit Price**: Fixed price per sign
2. **Material-Based**: Calculate cost based on material type and square footage
3. **Dimensional**: Custom sizing with price per square foot
4. **Installation & Tax**: Optional installation costs and sales tax calculation

### OneDrive Integration

- **Shared Database**: SQLite database optimized for OneDrive sharing
- **Automatic Deployment**: Scripts to deploy app to shared OneDrive folders
- **Team Collaboration**: Multiple users can access the same data
- **Conflict Resolution**: Database synchronization tools

## 🚀 Quick Start

### Click‑to‑Run (OneDrive) for Coworkers

If this folder lives in OneDrive and you just want to open the app on your own machine (no special setup):

1. Open the shared OneDrive folder containing this project
2. Double‑click either of these:
   - start_app.ps1 (PowerShell) — preferred for best experience
   - start_app.bat (classic CMD)
3. Your default browser will open to http://localhost:8050

Notes:
- No admin rights needed
- No firewall changes are required for local use
- The first launch may take a bit longer while dependencies are prepared per‑user
- Optional: create Desktop/Start‑Menu shortcuts by running: powershell -ExecutionPolicy Bypass -File scripts/create_shortcuts.ps1

### macOS Quick Start (TL;DR)

```bash
# 1. Clone or unzip project into (optionally) your OneDrive synced folder
cd Project_Pyramid_2

# 2. Make launcher executable (first time only)
chmod +x start_app.sh

# 3. Launch (auto-creates .venv, installs deps if needed)
./start_app.sh

# 4. (Optional) Enable SVG/Cairo rendering if you need SVG logos/images in PDF
brew install cairo pango libffi pkg-config        # Homebrew install
pip install --force-reinstall cairosvg            # Rebuild Python binding after libs

# 5. Re-run launcher
./start_app.sh

# 6. Verify environment (shows any degraded capabilities)
python scripts/verify_env.py

# 7. Customize (examples)
SIGN_APP_PORT=8060 SIGN_APP_HOST=0.0.0.0 ./start_app.sh
DISABLE_SVG_RENDER=1 ./start_app.sh               # Skip SVG rasterization fallback
```

Key paths macOS auto-detects for OneDrive: `~/Library/CloudStorage/OneDrive-*` (new client) or legacy `~/OneDrive`. Override by setting `ONEDRIVE_SYNC_DIR` if needed.

If Cairo native libs remain undiscovered, ensure your lib path is exported:

```bash
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH}"
```

Then retry `python scripts/verify_env.py`.

### Prerequisites

- Python 3.8 or higher
- Windows 10/11 (for production deployment)
- Microsoft 365 with OneDrive access
- Access to shared OneDrive folder

### Installation

1. **Clone/Download** the project to your development machine
2. **Setup Python Environment**:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

## Windows / OneDrive Deployment (Team Use)

1. Place the whole project folder inside the shared OneDrive directory your coworkers can access.
2. Preferred: coworkers double‑click `scripts/launch_app.bat` (runs `scripts/setup_env.bat` behind the scenes). It creates a per‑user venv in `%LOCALAPPDATA%\SignEstimator` (keeps OneDrive clean) and installs/updates dependencies only when `requirements.txt` changes.
3. The app will start on `http://localhost:8050` by default. To allow another machine on the LAN to reach it change env vars:
   - `SIGN_APP_HOST=0.0.0.0`
   - Optionally set `SIGN_APP_PORT=8060` (or another free port)
     You can put these in a file named `.env` (future enhancement) or prefix when launching:
     `SIGN_APP_PORT=8060 python app.py`
4. Share the host machine's LAN IP (e.g. `http://192.168.1.25:8050`) with coworkers; they can bookmark it.

### Recommended Workflow

| Action                                | Person          | Notes                                      |
| ------------------------------------- | --------------- | ------------------------------------------ |
| Enter / modify sign types & materials | Estimating lead | Done once then occasional updates          |
| Create project & buildings            | PM / Estimator  | Keep names consistent, they drive grouping |
| Assign sign groups & direct signs     | PM / Estimator  | Use groups for recurring bundles           |
| Generate building or project estimate | PM / Sales      | Use new building filter to narrow scope    |
| Export to Excel                       | Sales           | File saved locally after browser download  |

### OneDrive / SQLite Tips

- Keep the database file `sign_estimation.db` in the shared folder; SQLite WAL mode (enabled in code) reduces file locking issues.
- Avoid opening the database simultaneously with external tools while app is running.
- Backups: run `python scripts/backup_db.py` periodically (or copy the file) – creates timestamped copies under `backups/`.
- Full deployment wrapper `scripts/deploy_full.bat` (or `deploy_full.ps1`) creates a rotating backup automatically and prunes older ones.

### Multi-User Concurrency & Locking

This application intentionally uses SQLite in WAL (Write-Ahead Logging) mode to support a small estimating team without needing a separate database server.

Key behaviors:
- Multiple readers never block each other or the writer.
- Only one writer transaction commits at a time; brief contention is auto‑handled by SQLite (the app layer retries briefly if needed).
- Last write wins on the same exact row; there is no field‑level merge.
- Normal viewing, filtering, exporting = read-only and never blocked.
- Expensive writes: CSV import, material price recalculation – run when others are idle.

Recommended workflow:
1. Assign a temporary "editor" for a project when performing large quantity or pricing changes.
2. Communicate before bulk recalculation or mass import.
3. Use the deploy full script to create daily backups; for ad‑hoc safety copy the DB file (include any `-wal` / `-shm` if present during live copy).
4. If corruption is suspected (rare), restore the newest backup or a previous OneDrive version.

Scaling note: If your team grows beyond ~10 concurrent users or write frequency becomes heavy, plan a future migration to Postgres or MySQL using the same schema concepts.

### Sign Type Images

Each sign type can store one associated image under `sign_images/` (auto-created). Use the "Sign Type Images" card on the Sign Types tab:

1. Select a sign type
2. Upload PNG/JPG/JPEG/GIF/SVG (SVG preserved; converted when needed)
3. Image immediately available in both tree hover panels

Re-upload replaces the existing image. Filenames are sanitized (`<signname>.<ext>`). Stored path recorded in `sign_types.image_path`.

Displayed in:
- Interactive Cytoscape tree hover card
- Static Plotly tree hover card
- PDF export (thumbnail column if any images exist)
- Excel export (thumbnail column inserted at A if images exist)
- PNG export (future enhancement to embed per-sign thumbnails if desired)

Planned (optional) future expansions: multiple images per sign, export embedding, automatic downscaling of large files.

### Performance & Stability

- Local LAN + small user count (<10) is fine with SQLite.
- If you observe locking (rare): ensure only one app instance writes at a time; readers are safe.
- Material price recalculation is manual (button) to keep UI responsive.

### Customization via Environment Variables

| Variable              | Purpose                                 | Default            |
| --------------------- | --------------------------------------- | ------------------ |
| SIGN_APP_DB           | Path to DB file                         | sign_estimation.db |
| SIGN_APP_PORT         | HTTP port                               | 8050               |
| SIGN_APP_HOST         | Bind address (0.0.0.0 for LAN)          | 127.0.0.1          |
| SIGN_APP_EXPECT_LAN   | Expect LAN access (warn if only localhost) | 0                  |
| SIGN_APP_DEBUG        | Dash debug mode (1/true to enable)      | 0                  |
| ONEDRIVE_SYNC_DIR     | Path to OneDrive sync folder (autosync) | (unset)            |
| ONEDRIVE_AUTOSYNC_SEC | Autosync interval seconds               | 300                |
| SIGN_APP_CACHE_DIR    | Alternate cache/temp path               | per-user cache     |
| CAIROSVG_BACKEND      | Force cairosvg backend (e.g. pycairo)    | (unset)            |
| DISABLE_SVG_RENDER    | Skip SVG rasterization (fallback header) | 0                  |

For local use via OneDrive, you can ignore network and firewall settings entirely. Advanced options for LAN access are supported but not required for personal/local operation.

### SVG Rendering (Cairo) on Windows & macOS

The PDF export attempts to rasterize SVG logos and sign images via `cairosvg`. On Windows this requires Cairo native DLLs. If they are missing you will see warnings in `scripts/verify_env.py` like:

```
[MISSING] cairosvg: no library called "cairo-2" was found
```

Options to enable SVG rendering (Windows):

1. Install pycairo (already in requirements or: `pip install pycairo`).  
2. Provide native Cairo DLLs via a GTK runtime or MSYS2 and add their `bin` directory to `PATH`.  
3. Drop required DLLs (e.g. `libcairo-2.dll`, `libpng16-16.dll`, `zlib1.dll`, `libpixman-1-0.dll`, `libfreetype-6.dll`) into a local `cairo_runtime/` folder at the project root; the PowerShell launcher `start_app.ps1` will prepend that folder to `PATH` automatically.

macOS enable steps:

1. Install native libs via Homebrew:
   ```bash
   brew install cairo pango libffi pkg-config
   ```
2. Reinstall cairosvg after libs present (if previously failing):
   ```bash
   pip install --force-reinstall cairosvg
   ```
3. Launch using `./start_app.sh` (creates venv if missing).
4. If libraries still not found (rare), set fallback path (Apple Silicon example):
   ```bash
   export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH}"
   ```

Environment helpers:

| Variable | Effect |
| -------- | ------ |
| `CAIROSVG_BACKEND=pycairo` | Prefer the pycairo backend; helps when cairocffi cannot locate DLLs. |
| `DISABLE_SVG_RENDER=1` | Bypass SVG → PNG conversion; PDF uses text fallback header and existing raster images only. |

Diagnostic script:

```
python scripts/verify_env.py
```

Will report either `[OK] cairosvg functional render test` or a warning plus remediation guidance. This allows deployments to proceed even if SVG rendering is degraded.


### Security Note

LAN deployment here is plain HTTP inside your internal network. Do not expose directly to the public Internet without adding auth / HTTPS reverse proxy.

3. **Run the Application (macOS/Linux)**:
   ```bash
   chmod +x start_app.sh
   ./start_app.sh
   # With overrides
   SIGN_APP_PORT=8060 SIGN_APP_INITIAL_CSV=Book2.csv ./start_app.sh
   ```
4. **Run the Application (Windows)**:
   ```bat
   rem Direct
   .venv\Scripts\python.exe app.py
   rem Or batch launcher
   SET SIGN_APP_INITIAL_CSV=Book2.csv
   SET SIGN_APP_PORT=8060
   run_app.bat
   rem Or PowerShell
   $env:SIGN_APP_INITIAL_CSV="Book2.csv"; $env:SIGN_APP_PORT=8060; ./start_app.ps1
   ```
5. **Access the Application**:
   Open your web browser and go to `http://localhost:8050`

### Deployment to OneDrive (Windows & macOS)

1. **Deploy to OneDrive** (Windows path optional; mac auto-detects `~/Library/CloudStorage/OneDrive-*` when unset):

   ```bash
   python scripts/deploy.py --onedrive-path "C:\\Users\\Username\\OneDrive\\Shared\\SignEstimation"
   # or attempt autodetect (Windows only)
   python scripts/deploy.py
   ```

2. **On Windows Machines**: Run `start_app.bat` or `start_app.ps1`
3. **On macOS Machines**: Run `./start_app.sh` (first time: `chmod +x start_app.sh`)

### Windows Automated Setup & Cleanup

For a fresh local developer (or power‑user) setup you can use the scripted bootstrap instead of manual venv creation:

PowerShell (from project root):
```
./scripts/setup_windows.ps1
```
Options:
- `-Force`           Reinstall dependencies even if requirement hash matches
- `-RebuildVenv`     Delete and recreate the virtual environment from scratch
- `-SkipVerify`      Skip the post‑install environment diagnostic

Example (force dependency refresh):
```
./scripts/setup_windows.ps1 -Force
```

To validate only (no server) with the classic batch launcher:
```
run_app.bat /CHECK
```

When you need to wipe local artifacts (venv, DB, backups, exports) without touching source code use the cleanup helper:
```
./cleanup_windows.ps1 -DryRun
```
Then rerun with desired flags:
- `-RemoveVenv`        Delete `.venv` (or per‑user venv if script targeted it)
- `-RemoveDb`          Delete `sign_estimation.db`
- `-PurgeBackups`      Delete everything under `backups/`
- `-PurgeExports`      Delete generated export files (tree images, estimate PDFs/XLSX)
- `-Force`             Perform actions without interactive confirmation
- `-DryRun`            Show what would be removed (safety first)

Full reset example (keep source only):
```
./cleanup_windows.ps1 -RemoveVenv -RemoveDb -PurgeBackups -PurgeExports -Force
```

Use cases:
- Reclaim disk space after many export/backups
- Start from a pristine state before a demo
- Replace a corrupted local DB after restoring a backup copy

Tip: Always run once with `-DryRun` to confirm scope. The script never deletes unless an explicit flag is provided.


### One-Step Build + Deploy (Developer)

Use the new helper script to build a fresh PyInstaller GUI bundle and perform a full deploy (backups, prune, archive, logs):

```
scripts\deploy_and_bundle.bat
```

It will:
1. Rebuild the GUI bundle from `sign_estimator.spec` (cleaning `dist/` and `build/` first)
2. Run `deploy.py` with `--bundle --backup-db --backup-retention 7 --collect-logs --prune --archive`
3. Produce / update `start_app.bat` & `start_app.ps1` in the OneDrive root

Optional extra PyInstaller args can be appended, e.g.:

```
scripts\deploy_and_bundle.bat --pyinstaller-extra --clean
```

### Coworker Quick Start (No Python Installed)

1. Open the shared OneDrive folder (e.g. `SignEstimationApp`)
2. Double‑click `start_app.bat`
   - If a bundled executable exists under `bundle/`, it launches immediately
   - Otherwise it silently creates a per‑user venv in `%LOCALAPPDATA%\SignEstimator\venv` and installs dependencies (only on first run or when requirements change)
3. After a short moment your browser opens at `http://localhost:8050`

If SmartScreen warns about the executable: choose “More info” → “Run anyway” (internal trusted tool).

#### Auto Browser Launch & Flags (Windows PowerShell Launcher)

The PowerShell launcher `start_app.ps1` now attempts to open your default browser once the `/health` endpoint returns 200.

Flags / switches:

| Switch        | Effect |
| ------------- | ------ |
| `-NoBrowser`  | Do not auto‑open the browser |
| `-Minimized`  | Suppress most console output; server runs in a background PowerShell Job |
| `-ForceReinstall` | Rebuild per‑user venv & reinstall dependencies |

Environment overrides still work (e.g. `$env:SIGN_APP_PORT=8061; ./start_app.ps1`).

Example minimized launch without browser:
```
./start_app.ps1 -NoBrowser -Minimized
```

#### Desktop / Start Menu Shortcuts

Generate shortcuts (Desktop + Start Menu folder) pointing to the PowerShell launcher:
```
pwsh -ExecutionPolicy Bypass -File scripts/create_shortcuts.ps1
```
Options:
```
scripts/create_shortcuts.ps1 -Force       # recreate even if exists
scripts/create_shortcuts.ps1 -NoBrowser   # embed -NoBrowser flag in shortcut
scripts/create_shortcuts.ps1 -Minimized   # embed -Minimized flag in shortcut
```
Shortcuts use `assets/LSI_Logo.ico` if present (create with icon generator below).

#### Icon Generation

To convert the existing SVG logo to a multi‑resolution Windows icon:
```
python scripts/generate_icon.py
```
Outputs: `assets/LSI_Logo.ico` (sizes 16..256). Requires `cairosvg` + `Pillow` (both already in requirements).

#### Windows Toast Notification

If you add `win10toast` to `requirements.txt` (or pip install manually), a small toast will appear on successful startup:
```
pip install win10toast
```
Disable per run:
```
SET SIGN_APP_NO_TOAST=1 & start_app.bat
```
or in PowerShell:
```
$env:SIGN_APP_NO_TOAST=1; ./start_app.ps1
```

Toast is purely informational; absence of the package does not affect startup.

### Verifying a Deployment

Run the lightweight validator locally or from inside the OneDrive deployment root:

```
python scripts/verify_deploy.py --path "C:\Users\You\OneDrive\SignEstimationApp" 
```

Outputs status of bundle, startup scripts, database presence, and deployment timestamp freshness. Use `--json` for machine-readable output.

### Version Marker (Optional)

Add a `VERSION.txt` file in the project root before running the deploy script; it will be carried to OneDrive and surfaced by `verify_deploy.py`.

---

### Enhanced Deployment Options

The project now supports:
- Hash-based change detection (faster incremental deploys)
- Optional exclusion of database with `--exclude-db`
- PyInstaller bundle build & deploy (`--bundle`, `--bundle-console`)
- Smarter startup scripts that auto-create a per-user virtual environment or prefer a bundled executable if present

See `DEPLOY.md` for full details and advanced usage.
### Optional / Recommended Packages

Install these for full-feature export fidelity:

| Package   | Feature Enabled                                   |
|-----------|----------------------------------------------------|
| reportlab | PDF estimate export                                |
| kaleido   | High quality static Plotly image (tree) export     |
| cairosvg  | SVG logo & SVG sign image rasterization for exports|
| Pillow    | Image composition & PNG post-processing            |
| openpyxl  | Excel export (already required)                    |

Deployment Degraded Mode:

If your deployment environment lacks native Cairo libraries (common on fresh Windows hosts), you can still deploy by passing `--allow-degraded` to `scripts/deploy.py` (or setting `SIGN_APP_ALLOW_DEGRADED=1`). In this mode:
* Missing `cairosvg` or `reportlab` are treated as warnings.
* PDF export or SVG rasterization features will be skipped / reduced.
* Core application functionality remains unaffected.

Example:
```
python scripts/deploy.py --bundle --allow-degraded
```

## 🛠 TROUBLESHOOTING

### Native Cairo / SVG Rendering Issues

Symptoms:
* `cairosvg` import errors mentioning: `no library called "cairo-2" was found` or `libcairo-2.dll` missing.
* PDF export works (reportlab) but embedded SVG logos/sign images are blank or replaced by fallback text.

Why it happens:
`cairosvg` relies on native Cairo graphics libraries. On a fresh Windows system those DLLs are not present. The Python wheel alone cannot rasterize SVG without them.

Resolution Options (Windows):
1. Provide a `cairo_runtime/` folder at project root containing required DLLs (common minimal set):
   - `libcairo-2.dll`
   - `libpng16-16.dll`
   - `zlib1.dll`
   - `libpixman-1-0.dll`
   - `libfreetype-6.dll`
   - (sometimes) `libfontconfig-1.dll`, `libexpat-1.dll`
   The PowerShell launcher automatically prepends this folder to `PATH`.
2. Install a GTK or MSYS2 runtime and add its `bin` directory to `PATH`.
3. If SVG rasterization is not critical, deploy with:
   ```
   python scripts/deploy.py --bundle --allow-degraded
   ```
   and skip installing Cairo for now.

macOS:
```
brew install cairo pango libffi pkg-config
pip install --force-reinstall cairosvg
```
If still failing, ensure:
```
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH}"
```

### Verifying Bundle Integrity

After a build/deploy you can inspect cytoscape assets:
```
python scripts/verify_bundle.py
python scripts/verify_bundle.py --json
```
Critical files (must exist): `dash_cytoscape/package.json` and the js assets.

### Export Capability Summary

`scripts/deploy.py` now prints a summary after bundling. Example statuses:
| Feature | Meaning |
| ------- | ------- |
| ✅ OK | Feature fully enabled |
| ❌ MISSING | Library missing; feature disabled |

Enable everything:
```
python -m pip install reportlab cairosvg kaleido pillow openpyxl
```

### Common Deployment Pitfalls
| Issue | Cause | Fix |
|-------|------|-----|
| Missing `dash_cytoscape/package.json` in bundle | PyInstaller data omission | Rebuild; use current spec (collect_all) or run auto-repair block in deploy script |
| Browser not opening | `-NoBrowser` flag or minimized mode | Re-run without `-NoBrowser` |
| Toast not showing | `win10toast` not installed | `pip install win10toast` or ignore |
| PDF missing SVG graphics | Cairo libs absent | Provide DLLs or brew install cairo (mac), or accept degraded mode |

### When to Use Strict Mode
Use `--strict-bundle` to prevent distributing a bundle missing Cytoscape resources; deployment aborts if validation fails.

### Degraded Mode Indicator
If deployed with `--allow-degraded`, the post-build summary will list missing components. You can redeploy later after installing the libraries; no cleanup required beyond re-running the deploy command.

If missing, a dismissible yellow banner lists them; core app still functions with graceful fallbacks.

#### Suppressing / Customizing Environment Banner

Set `SIGN_APP_HIDE_ENV_NOTICE=1` to hide the yellow environment notice entirely if you are comfortable running without certain optional packages.

PowerShell (current session only):
```
$env:SIGN_APP_HIDE_ENV_NOTICE=1; python app.py
```
macOS / Linux:
```
SIGN_APP_HIDE_ENV_NOTICE=1 ./start_app.sh
```

To ignore only specific missing modules (still show others), set:
```
SIGN_APP_IGNORE_MISSING=cairosvg,kaleido ./start_app.sh
```
The banner will then suppress those names from the missing list.

Launcher shortcuts:

| Platform | Suppress Once |
|----------|---------------|
| PowerShell | `./start_app.ps1 -HideEnvNotice` |
| Windows CMD (venv launcher) | `run_app.bat /HIDEENV` |
| Windows simple launcher | `start_windows.bat /HIDEENV` |
| macOS/Linux | `./run_app.sh --hide-env-notice` |

These wrappers set `SIGN_APP_HIDE_ENV_NOTICE=1` for that session.
## 📊 Usage Guide

### Environment Variables

You can influence runtime behavior with:

- `SIGN_APP_DB` – alternate SQLite filename
- `SIGN_APP_INITIAL_CSV` – CSV auto-import (only if `sign_types` table empty)
- `SIGN_APP_PORT` – preferred port (auto-falls forward if busy)

### 1. Import Initial Data

- Go to the "Import Data" tab
- Upload your CSV file with sign types and pricing
- The system will automatically process and import the data

### 2. Create a Project

- Navigate to the "Projects" tab
- Click "Create Project"
- Enter project details including sales tax rate and installation settings

### 3. Add Buildings

- Select a project from the tree visualization
- Add buildings to organize your signs

### 4. Assign Signs

- **Individual Signs**: Add specific sign types with quantities to buildings
- **Sign Groups**: Create reusable sign packages and assign them to buildings

### 5. Generate Estimates

- Go to the "Estimates" tab
- Select your project
- Choose options for installation and sales tax
- Export to Excel with company branding

## 🏗️ Project Structure

```
Project_Pyramid_2/
├── app.py                 # Main Dash application
├── requirements.txt       # Python dependencies
├── assets/
│   └── LSI_Logo.svg      # Company logo
├── utils/
│   ├── database.py       # Database operations
│   ├── calculations.py   # Cost calculation logic
│   └── onedrive.py      # OneDrive integration
├── scripts/
│   ├── deploy.py        # Deployment script
│   └── sync_db.py       # Database sync script
└── README.md            # This file
```

## 💾 Database Schema

### Tables

- **projects**: Project information and settings
- **buildings**: Buildings within projects
- **sign_types**: Master catalog of available signs
- **sign_groups**: Reusable sign packages
- **sign_group_members**: Signs within each group
- **building_signs**: Individual signs assigned to buildings
- **building_sign_groups**: Sign groups assigned to buildings
- **material_pricing**: Material-based pricing rates

## 🔧 Configuration

### OneDrive Setup

The application creates configuration files automatically:

- `onedrive_config.json`: OneDrive path and sync settings
- `deployment_info.json`: Deployment status and history

### Database Optimization

The SQLite database is automatically optimized for OneDrive:

- WAL mode for better concurrent access
- Full synchronous mode for data integrity
- Optimized cache settings

## 🛠️ Development

### Adding New Features

1. **Database Changes**: Update `utils/database.py` with new table schemas
2. **Cost Calculations**: Extend `utils/calculations.py` for new pricing methods
3. **UI Components**: Add new tabs and components in `app.py`

### Testing

```bash
# Run the application in development mode
python app.py
**Version**: 1.1.0
# Test database functions
python -c "from utils.database import DatabaseManager; db = DatabaseManager(); print('Database OK')"

# Test OneDrive integration
python scripts/deploy.py --setup-only --onedrive-path "./test_onedrive"
```

## 📋 CSV Import Format

Your CSV should include the following columns (column names are flexible):

- **name**: Sign type name
- **description**: Sign description
- **price/unit_price**: Cost per sign
- **material**: Material type
- **width**: Sign width (for area calculations)
- **height**: Sign height (for area calculations)

Example CSV:

```csv
name,description,price,material,width,height
"ADA Room Sign","Standard ADA compliant room identification",45.00,"Brushed Aluminum",8,2
"Wayfinding Arrow","Directional wayfinding signage",65.00,"Acrylic",12,4
"Building Directory","Multi-tenant directory board",350.00,"Aluminum Frame",36,48
```

## 🤝 Team Collaboration

### For Administrators

1. Set up the OneDrive shared folder
2. Deploy the application using the deployment script
3. Share the OneDrive folder with team members
4. Provide training on the application interface

### For Team Members

1. Access the shared OneDrive folder
2. Run the startup script (`start_app.bat`)
3. Use the web interface to create estimates
4. Database changes sync automatically through OneDrive

## 🔒 Data Security & Backup

- **Automatic Backups**: Database changes are synced to OneDrive
- **Version Control**: OneDrive maintains file version history
- **Access Control**: Managed through OneDrive sharing permissions
- **Data Integrity**: SQLite ACID compliance ensures data consistency

## 📞 Support

For technical issues:

1. Check the deployment logs in the OneDrive folder
2. Verify Python installation and dependencies
3. Ensure OneDrive sync is working properly
4. Contact your IT administrator for OneDrive access issues

## 📄 License

This application is proprietary software developed for internal use by the sign manufacturing company.

---

**Last Updated**: September 2025  
**Version**: 1.1.0  
**Compatibility**: Windows 10/11, Python 3.8+, Microsoft 365

---

## 🔄 CRUD Workflows (Quick Reference)

### Sign Types

1. Go to the "Sign Types" tab
2. Edit cells directly (Name is required and acts as a unique key)
3. Add a new blank row with "Add New Sign Type"
4. Any edit triggers automatic persistence (ON CONFLICT upsert)

Auto-calculation: If you later recalc material pricing, unit_price is overwritten for rows with width/height > 0.

### Material Pricing

1. In "Sign Types" tab, use Material Pricing card
2. Add or edit material rows (material name is unique, case-insensitive)
3. Click "Save Materials" to persist
4. Click "Recalculate Sign Prices" to update sign_types.unit_price and price_per_sq_ft

### Sign Groups

1. Go to "Sign Groups" tab
2. Create or edit a group (name unique). Saving performs upsert on description
3. Select a group to manage its members
4. Add sign memberships with quantity; save member changes

### Assign Groups to Buildings

1. Choose a project and then a building
2. Select a group and quantity; add/assign
3. Adjust quantities inline and Save Group Quantities

### Buildings & Individual Signs

1. In "Projects" tab assign project, create buildings
2. Add sign types with quantity to selected building
3. Adjust quantities inline then "Save Quantity Changes"

### Estimates & Export

1. In "Estimates" tab choose a project
2. Generate Estimate (enables Export button automatically)
3. Export builds an Excel file (with logo if CairoSVG installed)
4. On export failure an error workbook is returned with cause noted

## 🧪 Health / Export Test (Example)
Check runtime health (shows version after deployment):
```bash
curl -s http://127.0.0.1:8050/health | jq
```

Add a pytest similar to:

```python
def test_export_basic(tmp_path):
   from utils.database import DatabaseManager
   import pandas as pd, sqlite3, os
   db = tmp_path / 'test.db'
   dm = DatabaseManager(str(db))
   # Insert minimal project + building + sign
   conn = sqlite3.connect(db)
   cur = conn.cursor()
   cur.execute("INSERT INTO projects (name) VALUES ('TestProj')")
   project_id = cur.lastrowid
   cur.execute("INSERT INTO buildings (project_id, name) VALUES (?, 'B1')", (project_id,))
   cur.execute("INSERT INTO sign_types (name, unit_price) VALUES ('SignA', 10.0)")
   cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (1,1,2)")
   conn.commit(); conn.close()
   est = dm.get_project_estimate(project_id)
   assert est and est[0]['Item'] == 'SignA'
```

## 🛠️ CLI Utilities

Price Recalculation without UI:

```bash
python scripts/recalc_prices.py --db sign_estimation.db
```

## 🔍 Diagnostics Banner

At the top of the UI a yellow banner may appear listing missing optional packages (`reportlab`, `kaleido`, `cairosvg`, `PIL`). These enhance export quality. Use:

```bash
python scripts/verify_env.py
```

to see a full status. The application still runs with graceful fallbacks.

## 📦 PyInstaller Bundle (Optional Distribution)

To create a single-folder bundled version (still serves via Python embedded runtime):

1. Install PyInstaller (not pinned in requirements by default):
   ```bash
   pip install pyinstaller
   ```
2. Build (basic example):
   ```bash
   pyinstaller --name sign_estimator --add-data "assets:assets" --add-data "LSI_Logo.svg:." --hidden-import plotly.io._kaleido app.py
   ```
3. After build finishes, distribute the `dist/sign_estimator/` folder. Place `sign_estimation.db` (or a copy) beside the executable if you want a portable, non-shared run; otherwise point to the shared DB via `SIGN_APP_DB` env var.
4. Run:
   ```bash
   dist/sign_estimator/sign_estimator.exe
   ```

Recommended extra flags (windowed build):

```bash
pyinstaller app.py \
  --name sign_estimator \
  --noconfirm \
  --clean \
  --add-data "assets{}assets" \
  --add-data "LSI_Logo.svg{}." \
  --hidden-import plotly.io._kaleido \
  --hidden-import cairo \
  --hidden-import cairosvg \
  --hidden-import reportlab.pdfgen
```

Replace `{}` with `;` on Windows, `:` on macOS/Linux.

### Console Build Variant

Use the console spec for debugging (shows stdout/stderr in a terminal window):

```bash
pyinstaller sign_estimator_console.spec --noconfirm
```

Or via helper scripts:

Windows:

```bat
scripts\build_bundle.bat --console
```

macOS/Linux:

```bash
bash scripts/build_bundle.sh --console
```

Notes:

- Keep the database outside the bundled directory if multiple users share it.
- Rebuild the bundle after updating `requirements.txt`.
- Large assets (fonts) can be added similarly with `--add-data`.

## 🧊 Wheelhouse Optimization (Optional)

Create a local wheel cache to speed first-time setup for multiple users:

```bash
pip download -r requirements.txt -d wheelhouse
```

Bootstrap scripts automatically use it if present.

```

This updates unit_price for all sign_types whose material matches material_pricing and width/height > 0.
```
