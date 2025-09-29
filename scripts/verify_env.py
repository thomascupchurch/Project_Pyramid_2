#!/usr/bin/env python
import importlib, sys, platform
mods = [
    'flask','pandas','plotly','dash','dash_bootstrap_components','openpyxl','PIL','requests',
    'dash_cytoscape','cairosvg','reportlab','kaleido'
]
print('Python', sys.version)
print('Platform', platform.platform())
missing = []
for m in mods:
    try:
        importlib.import_module(m)
        print(f'[OK] {m}')
    except Exception as e:
        print(f'[MISSING] {m}: {e}')
        missing.append(m)
if missing:
    print('\nMissing modules:', ', '.join(missing))
    sys.exit(1)
print('\nAll dependencies present.')
