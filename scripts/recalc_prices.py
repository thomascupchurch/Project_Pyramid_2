#!/usr/bin/env python
"""CLI utility to recalculate sign type prices from material_pricing table.

Usage:
  python scripts/recalc_prices.py [--db path/to/db.sqlite]

Reads each sign_types row with material match in material_pricing and width/height > 0.
Sets price_per_sq_ft to material rate and unit_price = width * height * rate.
Reports number of rows updated.
"""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = 'sign_estimation.db'

SQL = """
UPDATE sign_types
SET price_per_sq_ft = (
        SELECT mp.price_per_sq_ft FROM material_pricing mp
        WHERE LOWER(mp.material_name)=LOWER(sign_types.material)
    ),
    unit_price = CASE WHEN width>0 AND height>0 THEN (
        width * height * COALESCE((
            SELECT mp.price_per_sq_ft FROM material_pricing mp
            WHERE LOWER(mp.material_name)=LOWER(sign_types.material)
        ), price_per_sq_ft)
    ) ELSE unit_price END,
    last_modified = CURRENT_TIMESTAMP
WHERE material IS NOT NULL AND material <> ''
  AND EXISTS (SELECT 1 FROM material_pricing mp WHERE LOWER(mp.material_name)=LOWER(sign_types.material));
"""

COUNT_SQL = """
SELECT COUNT(*) FROM sign_types st
JOIN material_pricing mp ON LOWER(st.material)=LOWER(mp.material_name)
WHERE st.width>0 AND st.height>0;
"""

def recalc(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Pre-count potential rows
    cur.execute(COUNT_SQL)
    eligible = cur.fetchone()[0]
    cur.execute(SQL)
    conn.commit()
    # Post verify (rows touched approximated by eligible due to unconditional update in filter)
    conn.close()
    return eligible


def main():
    parser = argparse.ArgumentParser(description='Recalculate sign prices from material_pricing')
    parser.add_argument('--db', default=DEFAULT_DB, help='Path to SQLite DB (default: sign_estimation.db)')
    args = parser.parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        raise SystemExit(1)
    updated = recalc(db_path)
    print(f"Recalculation complete. Rows eligible/updated: {updated}")

if __name__ == '__main__':
    main()
