"""Seed minimal demo data into the sign_estimation.db if empty.

Creates:
  - One project (Demo Project)
  - One building (Main Building)
  - Two sign types (Panel A / Panel B)
  - One sign group including both signs
  - Assign both signs & the group to the building

Safe: Does nothing if any projects already exist.
"""
from __future__ import annotations
import sqlite3, os, sys, datetime

DB = 'sign_estimation.db'

def seed(db_path: str):
    if not os.path.exists(db_path):
        print(f'[seed] database not found: {db_path}')
        return 1
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Check if already seeded (any project)
    cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='projects'")
    if cur.fetchone()[0] == 0:
        print('[seed] schema incomplete (projects table missing). Run application once to initialize.')
        conn.close(); return 2
    cur.execute('SELECT COUNT(*) FROM projects')
    if cur.fetchone()[0] > 0:
        print('[seed] existing projects found – skipping demo seed.')
        conn.close(); return 0

    # Insert project
    cur.execute("INSERT INTO projects (name, description, created_date, sales_tax_rate, installation_rate) VALUES (?,?,?,?,?)",
                ('Demo Project','Example seeded project', datetime.date.today().isoformat(), 0.07, 0.05))
    project_id = cur.lastrowid

    # Insert building
    cur.execute("INSERT INTO buildings (project_id, name, description) VALUES (?,?,?)", (project_id, 'Main Building', 'Primary structure'))
    building_id = cur.lastrowid

    # Insert sign types
    cur.execute("INSERT INTO sign_types (name, description, unit_price, material, width, height) VALUES (?,?,?,?,?,?)", ('Panel A','Aluminum panel',150.0,'Aluminum',24,18))
    sign_a = cur.lastrowid
    cur.execute("INSERT INTO sign_types (name, description, unit_price, material, width, height) VALUES (?,?,?,?,?,?)", ('Panel B','PVC panel',90.0,'PVC',18,12))
    sign_b = cur.lastrowid

    # Assign signs to building
    cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)", (building_id, sign_a, 2))
    cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)", (building_id, sign_b, 4))

    # Create sign group
    cur.execute("INSERT INTO sign_groups (name, description) VALUES (?,?)", ('Basic Panels','Demo group'))
    group_id = cur.lastrowid
    cur.execute("INSERT INTO sign_group_members (group_id, sign_type_id, quantity) VALUES (?,?,?)", (group_id, sign_a, 1))
    cur.execute("INSERT INTO sign_group_members (group_id, sign_type_id, quantity) VALUES (?,?,?)", (group_id, sign_b, 1))

    # Attach group to building
    cur.execute("INSERT INTO building_sign_groups (building_id, group_id, quantity) VALUES (?,?,?)", (building_id, group_id, 1))

    conn.commit(); conn.close()
    print('[seed] Demo data inserted.')
    return 0

if __name__ == '__main__':
    sys.exit(seed(DB))
