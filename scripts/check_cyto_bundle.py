#!/usr/bin/env python
"""Check that dash_cytoscape resources are present in a (possibly frozen) environment.
Run inside bundle (after build) or in source venv.
"""
import sys, json, importlib.util, pathlib

frozen = bool(getattr(sys, 'frozen', False))
print(f"[diag] frozen={frozen} sys.executable={sys.executable}")

spec = importlib.util.find_spec('dash_cytoscape')
if not spec or not spec.origin:
    print('[fail] dash_cytoscape not importable')
    sys.exit(2)

pkg_dir = pathlib.Path(spec.origin).parent
pkg_json = pkg_dir / 'package.json'
print(f"[diag] dash_cytoscape dir={pkg_dir}")
print(f"[diag] package.json exists={pkg_json.exists()} size={pkg_json.stat().st_size if pkg_json.exists() else 'NA'}")

if not pkg_json.exists():
    # List directory contents for troubleshooting
    print('[list] contents:')
    for p in pkg_dir.iterdir():
        print('   ', p.name)
    sys.exit(3)

# Minimal validation of JSON structure
try:
    meta = json.loads(pkg_json.read_text(encoding='utf-8'))
    print('[ok] package.json parsed keys:', sorted(list(meta.keys()))[:8])
except Exception as e:
    print('[warn] could not parse package.json:', e)
    sys.exit(4)

print('[success] dash_cytoscape resources present.')
