#!/usr/bin/env python3
"""Verify presence and integrity of key bundle assets.

Usage:
  python scripts/verify_bundle.py [--bundle-root path_to_bundle_dir] [--json]

If --bundle-root not supplied, script looks for ./bundle/ under project root.
Checks:
  * Bundle variants: sign_estimator, sign_estimator_console (if present)
  * dash_cytoscape core files: package.json, metadata.json, js assets
  * Reports size and SHA256 of package.json for traceability
Exit codes:
  0 success (no missing critical assets)
  1 minor issues (some optional assets missing)
  2 critical missing (package.json absent in variant)
"""
from __future__ import annotations
import argparse, json, hashlib, os
from pathlib import Path

CORE_FILES = [
    'package.json', 'metadata.json', 'dash_cytoscape.min.js', 'dash_cytoscape.dev.js',
    'dash_cytoscape_extra.min.js', 'dash_cytoscape_extra.dev.js'
]

OPTIONAL_FILES = ['metadata.json']  # treat metadata.json as optional for now


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def inspect_variant(root: Path, name: str):
    vdir = root / name
    result = {
        'variant': name,
        'exists': vdir.exists(),
        'dash_cytoscape': {},
        'missing': [],
        'status': 'ok'
    }
    if not vdir.exists():
        result['status'] = 'absent'
        return result
    cy_dir = vdir / 'dash_cytoscape'
    if not cy_dir.exists():
        result['status'] = 'missing_cyto_dir'
        return result
    for f in CORE_FILES:
        fp = cy_dir / f
        if fp.exists():
            entry = {'size': fp.stat().st_size}
            if f == 'package.json':
                try:
                    entry['sha256'] = sha256(fp)
                except Exception as e:  # noqa: BLE001
                    entry['hash_error'] = str(e)
            result['dash_cytoscape'][f] = entry
        else:
            result['missing'].append(f)
    critical_missing = [m for m in result['missing'] if m not in OPTIONAL_FILES]
    if critical_missing:
        result['status'] = 'incomplete'
    return result


def main():
    parser = argparse.ArgumentParser(description='Verify PyInstaller bundle resources')
    parser.add_argument('--bundle-root', help='Path containing bundle variants (default ./bundle)')
    parser.add_argument('--json', action='store_true', help='Output JSON only')
    args = parser.parse_args()
    project_root = Path(__file__).parent.parent
    bundle_root = Path(args.bundle_root) if args.bundle_root else (project_root / 'bundle')

    variants = ['sign_estimator', 'sign_estimator_console']
    reports = [inspect_variant(bundle_root, v) for v in variants]

    if args.json:
        print(json.dumps({'bundle_root': str(bundle_root), 'reports': reports}, indent=2))
    else:
        print(f"Bundle root: {bundle_root}")
        for r in reports:
            print(f"\nVariant: {r['variant']}")
            print(f"  Exists: {r['exists']}")
            print(f"  Status: {r['status']}")
            if r['dash_cytoscape']:
                print("  Files:")
                for fname, meta in r['dash_cytoscape'].items():
                    extra = f" size={meta.get('size')}"
                    if 'sha256' in meta:
                        extra += f" sha256={meta['sha256'][:12]}..."
                    print(f"    - {fname}{extra}")
            if r['missing']:
                print("  Missing:")
                for m in r['missing']:
                    print(f"    - {m}")
    # Determine exit code
    code = 0
    any_critical = False
    for r in reports:
        if r['status'] in {'missing_cyto_dir','incomplete'}:
            any_critical = True
    if any_critical:
        code = 2
    else:
        # treat absent console variant as minor (exit 0)
        code = 0
    return code

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
