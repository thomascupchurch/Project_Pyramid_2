"""SQLite -> MSSQL migration utility.

Usage (PowerShell):
  $env:SIGN_APP_DB_BACKEND='mssql'
  $env:SIGN_APP_MSSQL_CONN='Driver={ODBC Driver 18 for SQL Server};Server=tcp:host,1433;Database=SignEstimation;Uid=user;Pwd=pass;Encrypt=yes;TrustServerCertificate=no;'
  python scripts/migrate_sqlite_to_mssql.py --sqlite sign_estimation.db

Notes:
 - Run this ONCE after provisioning the SQL Server empty database.
 - Order of table copies respects foreign key dependencies.
 - Existing rows in MSSQL with same natural keys will be skipped (rudimentary idempotence).
 - Large tables use executemany batching.
 - JSON/text fields copied verbatim; timestamps not transformed.
 - Pricing profiles / tagging / advanced tables are included if present in SQLite schema.

Safety:
 - Script is read-only against SQLite (no writes back).
 - You can dry-run with --dry-run to view counts without inserting.
"""
from __future__ import annotations
import argparse
import os
import sys
import sqlite3
import json
from typing import Sequence

try:
    import pyodbc  # type: ignore
except Exception as e:  # pragma: no cover
    print("[ERROR] pyodbc not available: install pyodbc and ODBC driver", file=sys.stderr)
    raise

from config import MSSQL_CONN_STRING  # type: ignore

FK_ORDER = [
    'projects', 'buildings', 'sign_types', 'sign_groups',
    'sign_group_members', 'building_signs', 'building_sign_groups',
    'material_pricing', 'user_roles', 'audit_log', 'estimate_snapshots',
    'pricing_profiles', 'sign_type_tags', 'sign_type_tag_map', 'notes',
    'bid_templates', 'bid_template_items', 'sign_type_images'
]

NATURAL_KEY = {
    'projects': ['name'],
    'buildings': ['project_id','name'],
    'sign_types': ['name'],
    'sign_groups': ['name'],
    'material_pricing': ['material_name'],
    'user_roles': ['username'],
    'pricing_profiles': ['name'],
    'sign_type_tags': ['name'],
    'bid_templates': ['name']
}

BATCH_SIZE = 500

def table_exists_sqlite(cur, table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None

def fetch_sqlite_rows(sqlite_cur, table: str):
    sqlite_cur.execute(f'SELECT * FROM {table}')
    cols = [d[0] for d in sqlite_cur.description]
    for row in sqlite_cur.fetchall():
        yield dict(zip(cols, row))

def ensure_target_schema(conn):
    # Rely on DatabaseManager(MSSQL) init to create core tables; minimal guard here.
    pass

def upsert_row(cur, table: str, row: dict):
    # For tables with natural key: skip insert if already present
    nk = NATURAL_KEY.get(table)
    if nk:
        where = ' AND '.join(f"{c}=?" for c in nk)
        cur.execute(f"SELECT 1 FROM {table} WHERE {where}", [row[c] for c in nk])
        if cur.fetchone():
            return False
    # Build insert
    cols = list(row.keys())
    placeholders = ','.join('?' for _ in cols)
    col_list = ','.join(cols)
    cur.execute(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", [row[c] for c in cols])
    return True

def migrate(sqlite_path: str, mssql_conn_str: str, dry_run: bool = False):
    if not os.path.exists(sqlite_path):
        raise SystemExit(f"SQLite DB not found: {sqlite_path}")
    print(f"[INFO] Opening source SQLite {sqlite_path}")
    s_conn = sqlite3.connect(sqlite_path)
    s_cur = s_conn.cursor()

    print("[INFO] Connecting to target MSSQL")
    t_conn = pyodbc.connect(mssql_conn_str)
    t_cur = t_conn.cursor()

    copied_counts = {}
    for table in FK_ORDER:
        if not table_exists_sqlite(s_cur, table):
            print(f"[SKIP] {table} missing in SQLite")
            continue
        rows = list(fetch_sqlite_rows(s_cur, table))
        if not rows:
            print(f"[INFO] {table}: 0 rows")
            continue
        inserted = 0
        if dry_run:
            print(f"[DRY] {table}: would copy {len(rows)} rows")
            continue
        # Strip SQLite autoincrement id collisions if target already has rows: naive approach
        has_id = 'id' in rows[0]
        if has_id:
            # Detect existing IDs to avoid PK collision
            try:
                t_cur.execute(f'SELECT id FROM {table}')
                existing_ids = {r[0] for r in t_cur.fetchall()}
            except Exception:
                existing_ids = set()
        else:
            existing_ids = set()
        batch = []
        for r in rows:
            if has_id and r['id'] in existing_ids:
                # attempt natural key insert instead (skip if exists)
                changed = upsert_row(t_cur, table, {k: v for k,v in r.items() if k != 'id'}) if table in NATURAL_KEY else False
                if changed:
                    inserted += 1
                continue
            try:
                if table in NATURAL_KEY:
                    # Try natural key upsert semantics
                    changed = upsert_row(t_cur, table, r)
                    if changed:
                        inserted += 1
                else:
                    batch.append(r)
                    if len(batch) >= BATCH_SIZE:
                        cols = list(batch[0].keys())
                        col_list = ','.join(cols)
                        placeholders = ','.join('?' for _ in cols)
                        t_cur.executemany(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", [[rr[c] for c in cols] for rr in batch])
                        inserted += len(batch)
                        batch.clear()
            except Exception as e:
                print(f"[WARN] row in {table} failed: {e}")
        if batch:
            cols = list(batch[0].keys())
            col_list = ','.join(cols)
            placeholders = ','.join('?' for _ in cols)
            t_cur.executemany(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", [[rr[c] for c in cols] for rr in batch])
            inserted += len(batch)
        t_conn.commit()
        copied_counts[table] = inserted
        print(f"[OK] {table}: inserted {inserted} (source {len(rows)})")

    print("[SUMMARY]")
    for t, c in copied_counts.items():
        print(f"  {t}: {c}")
    s_conn.close(); t_conn.close()


def main():
    ap = argparse.ArgumentParser(description="Migrate data from local SQLite DB to configured MSSQL database")
    ap.add_argument('--sqlite', default='sign_estimation.db', help='Path to source SQLite file')
    ap.add_argument('--conn', default=MSSQL_CONN_STRING, help='Override MSSQL connection string (else env SIGN_APP_MSSQL_CONN)')
    ap.add_argument('--dry-run', action='store_true', help='List actions without inserting')
    args = ap.parse_args()
    conn_str = args.conn or MSSQL_CONN_STRING
    if not conn_str:
        ap.error('MSSQL connection string required (set env SIGN_APP_MSSQL_CONN or pass --conn)')
    migrate(args.sqlite, conn_str, dry_run=args.dry_run)

if __name__ == '__main__':
    main()
