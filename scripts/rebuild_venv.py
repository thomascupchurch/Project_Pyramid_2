#!/usr/bin/env python
"""Rebuild the local .venv safely and consistently.

Features:
  - Detect cross-platform mismatch (using pyvenv.cfg home path heuristics)
  - Optional dry-run (--dry-run) to preview actions
  - Optional --force to skip mismatch requirement and rebuild anyway
  - Optional requirements file override via --req requirements-alt.txt
  - Produces summary JSON (--json / --out)
  - Automatic backup of existing requirements freeze to .venv_freeze_<timestamp>.txt before removal
  - Safe abort if uncommitted changes to requirements.txt (unless --ignore-dirty)

Exit codes:
  0 success, 1 generic failure, 2 aborted (user declined), 3 dirty requirements abort
"""
from __future__ import annotations
import argparse, os, sys, shutil, subprocess, json, hashlib, datetime, pathlib, textwrap

ROOT = pathlib.Path(__file__).parent.parent
VENV_DIR = ROOT / '.venv'
REQ_FILE_DEFAULT = ROOT / 'requirements.txt'


def detect_mismatch() -> tuple[bool,str|None,str|None]:
    cfg = VENV_DIR / 'pyvenv.cfg'
    if not cfg.exists():
        # Partial / corrupted venv (e.g., only Scripts/python.exe). Treat as no mismatch but flag for rebuild.
        return False, None, None
    txt = cfg.read_text(errors='ignore').lower()
    origin = None
    if os.name == 'nt' and '\nhome = /users/' in txt:
        origin = 'macOS'
    elif os.name != 'nt' and '\\python.exe' in txt:
        origin = 'Windows'
    return (origin is not None), origin, txt

def hash_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def git_requirements_dirty(req: pathlib.Path) -> bool:
    try:
        # Only run if .git present
        if not (ROOT / '.git').exists():
            return False
        res = subprocess.run(['git','status','--porcelain', str(req)], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return bool(res.stdout.strip())
    except Exception:
        return False

def create_parser():
    p = argparse.ArgumentParser(description='Rebuild local .venv for Sign Estimation app')
    p.add_argument('--force', action='store_true', help='Rebuild even if no mismatch detected')
    p.add_argument('--dry-run', action='store_true', help='Show what would happen without changing anything')
    p.add_argument('--req', default=str(REQ_FILE_DEFAULT), help='Requirements file to install (default requirements.txt)')
    p.add_argument('--ignore-dirty', action='store_true', help='Ignore modified requirements.txt safety check')
    p.add_argument('--python', default=sys.executable, help='Python interpreter to use for venv creation')
    p.add_argument('--json', action='store_true', help='Emit JSON summary to stdout')
    p.add_argument('--out', help='Write JSON summary to file path')
    p.add_argument('-y','--yes', action='store_true', help='Assume yes to prompt')
    return p

def main():
    args = create_parser().parse_args()
    summary = {
        'action': 'rebuild_venv',
        'root': str(ROOT),
        'venv_exists': VENV_DIR.exists(),
        'mismatch_detected': False,
        'mismatch_origin': None,
        'removed': False,
        'created': False,
        'installed': False,
        'requirements': args.req,
        'requirements_hash': None,
        'error': None,
        'aborted': False
    }
    mismatch, origin, raw = detect_mismatch()
    summary['mismatch_detected'] = mismatch
    summary['mismatch_origin'] = origin

    req_path = pathlib.Path(args.req)
    if not req_path.exists():
        summary['error'] = f'Requirements file not found: {req_path}'
        emit(summary, args)
        return 1
    try:
        summary['requirements_hash'] = hash_file(req_path)
    except Exception:
        pass

    if git_requirements_dirty(req_path) and not args.ignore_dirty:
        summary['error'] = 'requirements.txt has uncommitted changes (use --ignore-dirty to override)'
        summary['aborted'] = True
        emit(summary, args)
        return 3

    # Identify partial/corrupt venv (missing pyvenv.cfg but Scripts exists)
    partial = VENV_DIR.exists() and not (VENV_DIR / 'pyvenv.cfg').exists() and (VENV_DIR / ('Scripts' if os.name=='nt' else 'bin')).exists()
    summary['partial_detected'] = partial

    if not mismatch and not args.force and VENV_DIR.exists() and not partial:
        print('No cross-platform mismatch detected; use --force to rebuild anyway.')
        summary['aborted'] = True
        emit(summary, args)
        return 2

    if args.dry_run:
        print('[DRY-RUN] Would remove .venv and recreate using', args.python)
        emit(summary, args)
        return 0

    if VENV_DIR.exists():
        if not args.yes:
            resp = input(f'Recreate virtual env at {VENV_DIR}? This will delete it. [y/N]: ').strip().lower()
            if resp not in ('y','yes'):
                summary['aborted'] = True
                emit(summary, args)
                return 2
        # Backup freeze
        try:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            freeze_file = ROOT / f'.venv_freeze_{ts}.txt'
            subprocess.run([sys.executable,'-m','pip','freeze'], cwd=ROOT, stdout=freeze_file.open('w'), timeout=25)
        except Exception:
            pass
        print('Removing existing .venv ...')
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        summary['removed'] = True

    # If we are currently inside the venv we're about to remove/recreate, prefer using base interpreter
    active_prefix = pathlib.Path(sys.prefix)
    base_prefix = pathlib.Path(getattr(sys, 'base_prefix', sys.prefix))
    if active_prefix == VENV_DIR and base_prefix != active_prefix:
        # Switch to base interpreter for creation to avoid transient file lock/partial deletion issues
        base_python = base_prefix / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
        if base_python.exists():
            args.python = str(base_python)
            print(f"[info] Using base interpreter for rebuild: {args.python}")
        else:
            print('[warn] Could not locate base interpreter; proceeding with current')

    print('Creating new virtual environment ...')
    create_cmd = [args.python, '-m', 'venv', str(VENV_DIR)]
    rc = subprocess.run(create_cmd).returncode
    if rc != 0:
        summary['error'] = f'Venv creation failed (rc={rc})'
        emit(summary, args)
        return 1
    summary['created'] = True

    # Activate indirectly by referencing the interpreter inside venv
    py_bin = VENV_DIR / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
    if not py_bin.exists():
        # Provide more context (frequent on Windows if AV locked a file transiently)
        summary['error'] = f'Python executable missing inside venv: {py_bin}. Possible transient lock or antivirus interference. Retry or remove .venv manually.'
        emit(summary, args)
        return 1

    print('Upgrading pip ...')
    subprocess.run([str(py_bin), '-m', 'pip', 'install', '--upgrade', 'pip'], check=False)

    print(f'Installing dependencies from {req_path} ...')
    install_rc = subprocess.run([str(py_bin), '-m', 'pip', 'install', '-r', str(req_path)]).returncode
    if install_rc != 0:
        summary['error'] = f'pip install returned {install_rc}'
    else:
        summary['installed'] = True

    if summary['installed']:
        print('Rebuild complete.')
    else:
        print('Rebuild finished with errors (see summary).')

    emit(summary, args)
    return 0 if summary['installed'] else 1


def emit(summary, args):
    if args.json:
        print(json.dumps(summary, indent=2))
    if args.out:
        try:
            with open(args.out,'w') as f:
                json.dump(summary,f, indent=2)
        except Exception as e:
            print(f'[warn] failed writing summary file: {e}')


if __name__ == '__main__':
    sys.exit(main())
