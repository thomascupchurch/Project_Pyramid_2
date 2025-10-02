"""PyInstaller hook to ensure dash_cytoscape data (including package.json) is bundled.

Using the conventional 'datas' variable is sufficient; no custom hook() needed.
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('dash_cytoscape', include_py_files=True)
