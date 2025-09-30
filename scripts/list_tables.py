"""List tables (and optionally row counts) in the sign_estimation SQLite database.

Usage:
  python scripts/list_tables.py                # list table names
  python scripts/list_tables.py --counts       # include row counts
  python scripts/list_tables.py --db other.db  # custom db path
"""
from __future__ import annotations
import argparse, sqlite3, json, os, sys

DEF_DB = 'sign_estimation.db'

def list_tables(db_path: str, counts: bool):
    if not os.path.exists(db_path):
        return {'error': f'database file not found: {db_path}'}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        data = {'database': os.path.abspath(db_path), 'tables': tables}
        if counts:
            table_rows = {}
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    table_rows[t] = cur.fetchone()[0]
                except Exception as e:  # pragma: no cover
                    table_rows[t] = f'error: {e}'
            data['row_counts'] = table_rows
        conn.close()
        return data
    except Exception as e:
        return {'error': str(e)}


def main():
    ap = argparse.ArgumentParser(description='List tables in SQLite DB used by Sign Estimation App')
    ap.add_argument('--db', default=DEF_DB, help='Path to database file (default sign_estimation.db)')
    ap.add_argument('--counts', action='store_true', help='Include row counts per table')
    ap.add_argument('--json', action='store_true', help='Emit JSON only')
    args = ap.parse_args()

    info = list_tables(args.db, args.counts)
    if args.json:
        print(json.dumps(info, indent=2))
        return 0 if 'error' not in info else 1
    if 'error' in info:
        print(f"[error] {info['error']}")
        return 1
    print(f"Database: {info['database']}")
    if not info['tables']:
        print('No tables found.')
        return 0
    print('Tables:')
    for t in info['tables']:
        if args.counts and 'row_counts' in info:
            print(f"  - {t} ({info['row_counts'].get(t)})")
        else:
            print(f"  - {t}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
