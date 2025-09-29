"""CLI helper to generate an estimate PDF outside Dash for diagnostics.

Usage (PowerShell):
  python scripts/pdf_export_cli.py --out test_estimate.pdf

Optional arguments:
  --title "Custom Title" --summary "Some summary" --ext-only

If --ext-only is supplied, only rows with install_type containing 'ext' are included.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
from pathlib import Path as _Path
# Ensure project root on path when invoked directly
_proj_root = _Path(__file__).resolve().parents[1]
if str(_proj_root) not in sys.path:
    sys.path.insert(0, str(_proj_root))

from utils.pdf_export import generate_estimate_pdf

DEFAULT_ROWS = [
    {'Building':'A','Item':'Monument Sign','Material':'Aluminum','Dimensions':'48x72','Quantity':1,'Unit_Price':1200,'Total':1200,'install_type':'Exterior'},
    {'Building':'A','Item':'Lobby Panel','Material':'Acrylic','Dimensions':'24x36','Quantity':2,'Unit_Price':250,'Total':500,'install_type':'Interior'},
    {'Building':'B','Item':'Parking Directional','Material':'Aluminum','Dimensions':'18x24','Quantity':4,'Unit_Price':95,'Total':380,'install_type':'Exterior'},
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='Output PDF path')
    ap.add_argument('--title', default='CLI Estimate PDF')
    ap.add_argument('--summary', default='CLI generated estimate for diagnostics.')
    ap.add_argument('--ext-only', action='store_true', help='Restrict to exterior rows only')
    ap.add_argument('--rows-json', help='Path to JSON file containing an array of row dicts to override sample data')
    ap.add_argument('--db', default='sign_estimation.db', help='Path to SQLite DB')
    args = ap.parse_args()

    rows = DEFAULT_ROWS
    if args.rows_json:
        rows_path = Path(args.rows_json)
        if not rows_path.exists():
            raise SystemExit(f'rows json not found: {rows_path}')
        rows = json.loads(rows_path.read_text(encoding='utf-8'))
        if not isinstance(rows, list):
            raise SystemExit('rows-json must point to a JSON array')
    if args.ext_only:
        rows = [r for r in rows if 'ext' in str(r.get('install_type','')).lower()]

    pdf_bytes, diag = generate_estimate_pdf(rows, args.summary, args.title, args.db)
    out_path = Path(args.out)
    out_path.write_bytes(pdf_bytes)
    print('[pdf-cli] wrote', out_path, 'size=', diag['size'], 'sha1=', diag['sha1'][:12])
    print('[pdf-cli] rows total=', diag['row_count'], 'ext=', diag['exterior_count'], 'int=', diag['interior_count'])
    if not (pdf_bytes.startswith(b'%PDF') and diag['eof_present']):
        print('[pdf-cli][warn] PDF structure validation failed')

if __name__ == '__main__':
    main()
