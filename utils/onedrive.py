"""
OneDrive synchronization utilities for the Sign Estimation Application.
Handles deployment and updates to shared OneDrive folders.
"""

import os
import shutil
import json
import hashlib
from pathlib import Path
from datetime import datetime
import subprocess

class OneDriveManager:
    def __init__(self, local_path=None, onedrive_path=None):
        self.local_path = Path(local_path) if local_path else Path.cwd()
        self.onedrive_path = Path(onedrive_path) if onedrive_path else None
        self.config_file = self.local_path / "onedrive_config.json"
        self.load_config()
        # Auto-detect OneDrive path on macOS if not provided
        if self.onedrive_path is None:
            autodetected = self._autodetect_onedrive_root()
            if autodetected:
                self.onedrive_path = autodetected
    
    def load_config(self):
        """Load OneDrive configuration from config file."""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.onedrive_path = Path(config.get('onedrive_path', ''))
                self.deployment_settings = config.get('deployment_settings', {})
                # Merge in any newly recommended exclude patterns without removing user's existing customizations
                required_excludes = [
                    '__pycache__', '*.pyc', '.git', '.vscode', 'node_modules', '.env', 'development.db',
                    'activate', 'venv', '.venv', 'dist', 'build', 'bundle'
                ]
                existing_excl = set(self.deployment_settings.get('exclude_patterns', []))
                changed = False
                for pat in required_excludes:
                    if pat not in existing_excl:
                        existing_excl.add(pat); changed = True
                if changed:
                    self.deployment_settings['exclude_patterns'] = list(existing_excl)
        else:
            self.deployment_settings = {
                'exclude_patterns': [
                    '__pycache__', '*.pyc', '.git', '.vscode', 'node_modules', '.env', 'development.db',
                    'activate', 'venv', '.venv', 'dist', 'build', 'bundle'
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
    
    def _hash_manifest_path(self):
        return self.onedrive_path / "file_hashes.json" if self.onedrive_path else None

    def _load_hash_manifest(self):
        path = self._hash_manifest_path()
        if path and path.exists():
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_hash_manifest(self, manifest: dict):
        path = self._hash_manifest_path()
        if path:
            try:
                with open(path, 'w') as f:
                    json.dump(manifest, f, indent=2)
            except Exception:
                pass

    # -------------------- Platform helpers --------------------
    @staticmethod
    def _autodetect_onedrive_root():
        """Attempt to detect a user's OneDrive root (supports Windows & macOS).

        macOS patterns (depending on client and business vs personal):
          ~/Library/CloudStorage/OneDrive-<OrgName>
          ~/Library/CloudStorage/OneDrive-Personal
          ~/OneDrive  (legacy / symlink)
        Windows relies on environment vars (not handled here since usually configured already).
        Returns Path or None.
        """
        try:
            home = Path.home()
            candidates = [
                home / 'Library' / 'CloudStorage',  # will enumerate below
                home / 'OneDrive'
            ]
            roots = []
            for base in candidates:
                if base.exists():
                    # If base is CloudStorage, look for OneDrive-* subfolders
                    if base.name == 'CloudStorage':
                        for child in base.iterdir():
                            if child.is_dir() and child.name.startswith('OneDrive'):
                                roots.append(child)
                    else:
                        roots.append(base)
            # Heuristic: pick first with an 'Documents' or 'Shared' directory
            for r in roots:
                if (r / 'Documents').exists() or (r / 'Shared').exists():
                    return r
            return roots[0] if roots else None
        except Exception:
            return None

    @staticmethod
    def _file_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()

    def deploy_to_onedrive(self, force: bool = False, exclude_db: bool = False, use_hash: bool = True,
                            backup_db: bool = False, backup_retention: int = 10,
                            collect_logs: bool = False,
                            prune_orphans: bool = False,
                            archive_previous: bool = False):
        """Deploy the application to OneDrive shared folder.

        Enhancements:
          - Optional hash-based change detection (sha256) to avoid copying unchanged files.
          - Optional exclusion of database file.
        """
        if not self.onedrive_path:
            return False, "OneDrive path not configured"
        if not self.onedrive_path.exists():
            return False, f"OneDrive path does not exist: {self.onedrive_path}"

        try:
            deployment_log = []
            skipped = 0
            manifest_prev = self._load_hash_manifest() if use_hash else {}
            manifest_new = {}
            processed = 0
            print(f"[deploy] Walking project directory: {self.local_path}")

            # Optionally archive current app folder before changes
            archive_path = None
            if archive_previous:
                try:
                    app_dir = self.onedrive_path / 'app'
                    if app_dir.exists():
                        archives_dir = self.onedrive_path / 'archives'
                        archives_dir.mkdir(exist_ok=True)
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        archive_path = archives_dir / f'app_{ts}.zip'
                        import zipfile
                        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                            for root, _dirs, files in os.walk(app_dir):
                                for f in files:
                                    full = Path(root) / f
                                    rel = full.relative_to(app_dir)
                                    zf.write(full, rel.as_posix())
                        deployment_log.append(f"[archive] created {archive_path.relative_to(self.onedrive_path)}")
                except Exception as ae:
                    deployment_log.append(f"[warn] archive failed: {ae}")

            for root, dirs, files in os.walk(self.local_path):
                # Fast exclude of large/irrelevant directories
                dirs[:] = [d for d in dirs if not any(pattern in d for pattern in self.deployment_settings['exclude_patterns'])]
                for file in files:
                    source_file = Path(root) / file
                    relative_path = source_file.relative_to(self.local_path)
                    if not self.should_include_file(source_file):
                        continue
                    target_file = self.onedrive_path / "app" / relative_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    copy_reason = None
                    if force or not target_file.exists():
                        copy_reason = 'new' if not target_file.exists() else 'force'
                    elif use_hash:
                        new_hash = self._file_sha256(source_file)
                        old_hash = manifest_prev.get(str(relative_path))
                        if new_hash != old_hash:
                            copy_reason = 'hash_changed'
                        manifest_new[str(relative_path)] = new_hash
                    else:
                        # mtime fallback
                        if source_file.stat().st_mtime > target_file.stat().st_mtime:
                            copy_reason = 'mtime_newer'

                    # Compute hash if we haven't yet and we need to copy & using hash
                    if use_hash and str(relative_path) not in manifest_new:
                        manifest_new[str(relative_path)] = self._file_sha256(source_file)

                    if copy_reason:
                        shutil.copy2(source_file, target_file)
                        deployment_log.append(f"{relative_path} -> {copy_reason}")
                    else:
                        skipped += 1
                    processed += 1
                    if processed % 200 == 0:
                        print(f"[deploy] Processed {processed} files... (deployed {len(deployment_log)}, skipped {skipped})")

            db_backup_created = False
            db_backup_path = None

            # Copy database file unless excluded
            if not exclude_db:
                db_source = self.local_path / "sign_estimation.db"
                if db_source.exists():
                    db_target = self.onedrive_path / "database" / "sign_estimation.db"
                    db_target.parent.mkdir(parents=True, exist_ok=True)

                    # Backup existing remote DB before overwriting (if requested)
                    try:
                        if backup_db and db_target.exists():
                            backups_dir = self.onedrive_path / "database" / "backups"
                            backups_dir.mkdir(exist_ok=True)
                            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                            backup_file = backups_dir / f"sign_estimation_{ts}.db"
                            shutil.copy2(db_target, backup_file)
                            db_backup_created = True
                            db_backup_path = str(backup_file.relative_to(self.onedrive_path))
                            # Enforce retention
                            if backup_retention > 0:
                                existing = sorted([p for p in backups_dir.glob('sign_estimation_*.db')], key=lambda p: p.stat().st_mtime)
                                while len(existing) > backup_retention:
                                    old = existing.pop(0)
                                    try:
                                        old.unlink()
                                    except Exception:
                                        pass
                    except Exception as be:
                        deployment_log.append(f"[warn] db backup failed: {be}")
                    copy_db = False
                    reason = None
                    if force or not db_target.exists():
                        copy_db = True
                        reason = 'new_db' if not db_target.exists() else 'force'
                    elif use_hash:
                        new_hash = self._file_sha256(db_source)
                        old_hash = manifest_prev.get('DATABASE::sign_estimation.db')
                        if new_hash != old_hash:
                            copy_db = True
                            reason = 'hash_changed'
                        manifest_new['DATABASE::sign_estimation.db'] = new_hash
                    else:
                        if db_source.stat().st_mtime > db_target.stat().st_mtime:
                            copy_db = True
                            reason = 'mtime_newer'
                    if use_hash and 'DATABASE::sign_estimation.db' not in manifest_new:
                        manifest_new['DATABASE::sign_estimation.db'] = self._file_sha256(db_source)
                    if copy_db:
                        shutil.copy2(db_source, db_target)
                        deployment_log.append(f"database/sign_estimation.db -> {reason}")

            if use_hash:
                self._save_hash_manifest(manifest_new)

            log_summary = []
            if collect_logs:
                try:
                    logs_target = self.onedrive_path / 'logs'
                    logs_target.mkdir(exist_ok=True)
                    for log_file in self.local_path.glob('*.log'):
                        try:
                            shutil.copy2(log_file, logs_target / log_file.name)
                            size_kb = round(log_file.stat().st_size / 1024, 2)
                            log_summary.append({'name': log_file.name, 'size_kb': size_kb})
                        except Exception as le:
                            deployment_log.append(f"[warn] log copy failed {log_file.name}: {le}")
                except Exception as le_outer:
                    deployment_log.append(f"[warn] log aggregation failed: {le_outer}")

            orphaned = []
            if prune_orphans:
                try:
                    app_dir = self.onedrive_path / 'app'
                    current_rel = set(manifest_new.keys()) if use_hash else set()
                    # If hash disabled, build current_rel from local walk used above
                    if not use_hash:
                        for root, dirs, files in os.walk(self.local_path):
                            dirs[:] = [d for d in dirs if not any(pattern in d for pattern in self.deployment_settings['exclude_patterns'])]
                            for f in files:
                                source_file = Path(root) / f
                                if not self.should_include_file(source_file):
                                    continue
                                rel = source_file.relative_to(self.local_path)
                                current_rel.add(str(rel))
                    # Traverse remote app dir
                    for root, _dirs, files in os.walk(app_dir):
                        for f in files:
                            full = Path(root) / f
                            rel = full.relative_to(app_dir)
                            # Skip special files
                            if rel.as_posix() in ('file_hashes.json',):
                                continue
                            if str(rel) not in current_rel:
                                try:
                                    full.unlink()
                                    orphaned.append(rel.as_posix())
                                except Exception as pe:
                                    deployment_log.append(f"[warn] prune failed {rel}: {pe}")
                except Exception as pr_e:
                    deployment_log.append(f"[warn] prune phase error: {pr_e}")

            deployment_info = {
                'deployed_at': datetime.now().isoformat(),
                'deployed_from': str(self.local_path),
                'files_deployed': len(deployment_log),
                'files_skipped': skipped,
                'hash_mode': use_hash,
                'force': force,
                'excluded_db': exclude_db,
                'db_backup_enabled': backup_db,
                'db_backup_created': db_backup_created,
                'db_backup_path': db_backup_path,
                'db_backup_retention': backup_retention,
                'deployment_log': deployment_log,
                'log_aggregation_enabled': collect_logs,
                'logs_copied': len(log_summary),
                'log_files': log_summary,
                'archived_previous': archive_previous,
                'archive_path': str(archive_path.relative_to(self.onedrive_path)) if archive_previous and archive_path else None,
                'prune_orphans': prune_orphans,
                'orphans_removed': orphaned
            }
            with open(self.onedrive_path / "deployment_info.json", 'w') as f:
                json.dump(deployment_info, f, indent=2)
            self.save_config()
            return True, f"Deployed {len(deployment_log)} files (skipped {skipped})"
        except Exception as e:
            return False, f"Deployment failed: {str(e)}"
    
    def create_startup_script(self):
        """Create startup scripts for launching the app or bundled executable.

        Behavior:
          - If a PyInstaller bundle exists under bundle/sign_estimator, prefer launching it.
          - Otherwise bootstrap a per-user venv (outside OneDrive) using scripts/setup_env.bat logic if present in app/.
          - Fall back to system python if venv creation fails.
        """
        if not self.onedrive_path:
            return False, "OneDrive path not configured"

        app_dir = self.onedrive_path / 'app'
        bundle_dir = self.onedrive_path / 'bundle'
        # Candidate executables
        bundle_exe = bundle_dir / 'sign_estimator' / 'sign_estimator.exe'
        bundle_console_exe = bundle_dir / 'sign_estimator_console' / 'sign_estimator_console.exe'

        batch_lines = [
            '@echo off',
            'setlocal',
            'echo ============================================',
            'echo  Sign Estimation Application Launcher',
            'echo ============================================',
            f'set APP_DIR="{app_dir}"',
            f'set BUNDLE_DIR="{bundle_dir}"',
            'set PREFERRED_EXE=',
            f'if exist "{bundle_exe}" set PREFERRED_EXE="{bundle_exe}"',
            f'if exist "{bundle_console_exe}" if not defined PREFERRED_EXE set PREFERRED_EXE="{bundle_console_exe}"',
            'if defined PREFERRED_EXE (',
            '  echo Launching bundled executable %PREFERRED_EXE%',
            '  pushd %~dp0',
            '  start "SignEstimator" %PREFERRED_EXE%',
            '  goto :EOF',
            ')',
            'echo No bundle found, using Python source launch...',
            f'cd /d "{app_dir}"',
            'set APP_NAME=SignEstimator',
            'set BASE_DIR=%LOCALAPPDATA%\%APP_NAME%',
            'set VENV_DIR=%BASE_DIR%\venv',
            'if not exist "%BASE_DIR%" mkdir "%BASE_DIR%" >nul 2>&1',
            'if not exist "%VENV_DIR%" (',
            '  echo Creating per-user virtual environment (first run)...',
            '  python -m venv "%VENV_DIR%" || (echo Failed to create venv & goto RUN_FALLBACK)',
            ')',
            'call "%VENV_DIR%\Scripts\activate.bat" || (echo Could not activate venv & goto RUN_FALLBACK)',
            'if exist requirements.txt (',
            '  set MARKER_FILE=%BASE_DIR%\install_complete.marker',
            '  if not exist "%BASE_DIR%\requirements.sha256" (set NEED_INSTALL=1) else set NEED_INSTALL=0',
            '  for /f "tokens=*" %%i in ("powershell -NoProfile -Command (Get-FileHash requirements.txt -Algorithm SHA256).Hash") do set CUR_HASH=%%i',
            '  if exist "%BASE_DIR%\requirements.sha256" (',
            '    set /p OLD_HASH=<"%BASE_DIR%\requirements.sha256"',
            '    if /i "!OLD_HASH!"=="!CUR_HASH!" (',
            '       if exist "!MARKER_FILE!" (set NEED_INSTALL=0) else (echo Marker missing -> reinstall & set NEED_INSTALL=1)',
            '    ) else set NEED_INSTALL=1',
            '  )',
            '  if "!NEED_INSTALL!"=="1" (',
            '     echo Installing/Updating dependencies...',
            '     python -m pip install --upgrade pip >nul 2>&1',
            '     pip install -r requirements.txt || echo Warning: dependency install issues',
            '     echo !CUR_HASH!>"%BASE_DIR%\requirements.sha256"',
            '     echo ok>"!MARKER_FILE!"',
            '  ) else echo Dependencies up-to-date.',
            ')',
            ':: Core module sanity check (dash, pandas, plotly, dash_bootstrap_components, reportlab, kaleido).',
            'for /f "usebackq delims=" %%M in (`"%VENV_DIR%\Scripts\python.exe" -c "import importlib,sys;mods=[''dash'',''pandas'',''plotly'',''dash_bootstrap_components'',''reportlab'',''kaleido''];missing=[m for m in mods if importlib.util.find_spec(m) is None];print(','.join(missing))"`) do set CORE_MISSING=%%M',
            'if defined CORE_MISSING if NOT "%CORE_MISSING%"=="" (',
            '  echo Core modules missing (%CORE_MISSING%) - forcing dependency reinstall...',
            '  pip install -r requirements.txt || echo Warning: forced reinstall issues',
            '  echo ok>"%BASE_DIR%\install_complete.marker"',
            ')',
            ':RUN_APP',
            'echo Starting application with virtual environment...',
            'python app.py',
            'goto :EOF',
            ':RUN_FALLBACK',
            'echo Falling back to system python...',
            'python app.py',
            'endlocal'
        ]
        batch_file = self.onedrive_path / 'start_app.bat'
        with open(batch_file, 'w') as f:
            f.write("\n".join(batch_lines))

        ps_lines = [
            '# PowerShell launcher for Sign Estimation Application',
            f'$AppDir = "{app_dir}"',
            f'$BundleDir = "{bundle_dir}"',
            f'$BundleExe = Join-Path $BundleDir "sign_estimator/sign_estimator.exe"',
            f'$BundleConsoleExe = Join-Path $BundleDir "sign_estimator_console/sign_estimator_console.exe"',
            'Write-Host "============================================" -ForegroundColor Cyan',
            'Write-Host " Sign Estimation Application Launcher" -ForegroundColor Green',
            'Write-Host "============================================" -ForegroundColor Cyan',
            'if (Test-Path $BundleExe) { $Preferred = $BundleExe } elseif (Test-Path $BundleConsoleExe) { $Preferred = $BundleConsoleExe }',
            'if ($Preferred) {',
            '  Write-Host "Launching bundled executable: $Preferred" -ForegroundColor Green',
            '  Start-Process -FilePath $Preferred',
            '  exit 0',
            '}',
            'Write-Host "No bundle found; launching from source." -ForegroundColor Yellow',
            'Set-Location $AppDir',
            '$AppName = "SignEstimator"',
            '$BaseDir = Join-Path $env:LOCALAPPDATA $AppName',
            '$VenvDir = Join-Path $BaseDir "venv"',
            'if (-not (Test-Path $BaseDir)) { New-Item -ItemType Directory -Path $BaseDir | Out-Null }',
            'if (-not (Test-Path $VenvDir)) {',
            '  Write-Host "Creating virtual environment..." -ForegroundColor Yellow',
            '  python -m venv $VenvDir',
            '}',
            '$Activate = Join-Path $VenvDir "Scripts/Activate.ps1"',
            'if (Test-Path $Activate) { . $Activate } else { Write-Host "Could not activate venv, using system python" -ForegroundColor Red }',
            '$ReqFile = Join-Path $AppDir "requirements.txt"',
            'if (Test-Path $ReqFile) {',
            '  $HashFile = Join-Path $BaseDir "requirements.sha256"',
            '  $CurHash = (Get-FileHash $ReqFile -Algorithm SHA256).Hash',
            '  $NeedInstall = $true',
            '  if (Test-Path $HashFile) { $OldHash = Get-Content $HashFile; if ($OldHash -eq $CurHash) { $NeedInstall = $false } }',
            '  if ($NeedInstall) {',
            '     Write-Host "Installing/Updating dependencies..." -ForegroundColor Yellow',
            '     python -m pip install --upgrade pip | Out-Null',
            '     pip install -r $ReqFile',
            '     $CurHash | Out-File $HashFile -Encoding ASCII',
            '  } else { Write-Host "Dependencies up-to-date." -ForegroundColor DarkGreen }',
            '}',
            '# Core module sanity check (dash & pandas) to guard against partial installs',
            '$coreMissing = & python -c "import importlib,sys;mods=[\'dash\',\'pandas\',\'plotly\',\'dash_bootstrap_components\',\'reportlab\',\'kaleido\'];print(\",\".join([m for m in mods if importlib.util.find_spec(m) is None]))"',
            'if ($coreMissing) {',
            '  Write-Host "Core modules missing ($coreMissing) - forcing reinstall..." -ForegroundColor Yellow',
            '  pip install -r $ReqFile',
            '  "ok" | Out-File (Join-Path $BaseDir "install_complete.marker") -Encoding ASCII',
            '}',
            'Write-Host "Starting application..." -ForegroundColor Green',
            'python app.py'
        ]
        ps_file = self.onedrive_path / 'start_app.ps1'
        with open(ps_file, 'w') as f:
            f.write("\n".join(ps_lines))

        # --- POSIX (macOS/Linux) shell launcher ---
        sh_lines = [
            '#!/usr/bin/env bash',
            'set -e',
            'echo "============================================"',
            'echo "  Sign Estimation Application Launcher"',
            'echo "============================================"',
            f'APP_DIR="{app_dir}"',
            f'BUNDLE_DIR="{bundle_dir}"',
            'GUI_BUNDLE="$BUNDLE_DIR/sign_estimator/sign_estimator"',
            'CONSOLE_BUNDLE="$BUNDLE_DIR/sign_estimator_console/sign_estimator_console"',
            'if [ -x "$GUI_BUNDLE" ]; then',
            '  echo "Launching bundled GUI: $GUI_BUNDLE"',
            '  (cd "$(dirname \"$GUI_BUNDLE\")" && "./$(basename \"$GUI_BUNDLE\")" &)',
            '  exit 0',
            'elif [ -x "$CONSOLE_BUNDLE" ]; then',
            '  echo "Launching console bundle: $CONSOLE_BUNDLE"',
            '  (cd "$(dirname \"$CONSOLE_BUNDLE\")" && "./$(basename \"$CONSOLE_BUNDLE\")" &)',
            '  exit 0',
            'fi',
            'echo "No bundle found; launching from source."',
            'cd "$APP_DIR"',
            'APP_NAME=SignEstimator',
            '# Per-user venv path (outside OneDrive). macOS: $HOME/Library/Application Support/<AppName>',
            'BASE_DIR="$HOME/.local/share/$APP_NAME"',
            'if [ "$(uname)" = "Darwin" ]; then',
            '  BASE_DIR="$HOME/Library/Application Support/$APP_NAME"',
            'fi',
            'VENV_DIR="$BASE_DIR/venv"',
            'mkdir -p "$BASE_DIR"',
            'if [ ! -x "$VENV_DIR/bin/python" ]; then',
            '  echo "Creating virtual environment (first run)..."',
            '  python3 -m venv "$VENV_DIR" || { echo "Failed to create venv"; exit 2; }',
            'fi',
            'PY="$VENV_DIR/bin/python"',
            'REQ=requirements.txt',
            'if [ -f "$REQ" ]; then',
            '  HASH_FILE="$BASE_DIR/requirements.sha256"',
            '  CUR_HASH=$(python3 - <<EOF\nimport hashlib,sys;print(hashlib.sha256(open(\"$REQ\",\"rb\").read()).hexdigest())\nEOF\n)',
            '  NEED_INSTALL=1',
            '  if [ -f "$HASH_FILE" ]; then',
            '    OLD_HASH=$(cat "$HASH_FILE")',
            '    if [ "$OLD_HASH" = "$CUR_HASH" ]; then NEED_INSTALL=0; fi',
            '  fi',
            '  if [ $NEED_INSTALL -eq 1 ]; then',
            '     echo "Installing/Updating dependencies..."',
            '     "$PY" -m pip install --upgrade pip >/dev/null 2>&1 || true',
            '     "$PY" -m pip install -r "$REQ" || echo "Warning: dependency install issues"',
            '     echo "$CUR_HASH" > "$HASH_FILE"',
            '  else',
            '     echo "Dependencies up-to-date."',
            '  fi',
            'fi',
            '# Core module sanity check (dash & pandas)',
            'MISSING=$("$PY" - <<EOF\nimport importlib,sys;mods=[\'dash\',\'pandas\',\'plotly\',\'dash_bootstrap_components\',\'reportlab\',\'kaleido\'];missing=[m for m in mods if importlib.util.find_spec(m) is None];print(','.join(missing))\nEOF\n)',
            'if [ -n "$MISSING" ]; then',
            '  echo "Core modules missing ($MISSING) – reinstalling..."',
            '  "$PY" -m pip install -r "$REQ" || echo "Warning: forced reinstall failed"',
            '  echo ok > "$BASE_DIR/install_complete.marker"',
            'fi',
            'echo "Starting application..."',
            'exec "$PY" app.py'
        ]
        sh_file = self.onedrive_path / 'start_app.sh'
        try:
            with open(sh_file, 'w') as f:
                f.write("\n".join(sh_lines) + "\n")
            os.chmod(sh_file, 0o755)
        except Exception:
            pass
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
