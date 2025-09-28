import sqlite3, os, base64, io, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / 'utils') not in sys.path:
    sys.path.insert(0, str(ROOT / 'utils'))

from database import DatabaseManager


def test_basic_export_path(tmp_path):
    db_file = tmp_path / 'test_export.db'
    dm = DatabaseManager(str(db_file))
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("INSERT INTO projects (name, sales_tax_rate, installation_rate) VALUES ('P1',0,0)")
    project_id = cur.lastrowid
    cur.execute("INSERT INTO buildings (project_id, name) VALUES (?, 'B1')", (project_id,))
    cur.execute("INSERT INTO sign_types (name, unit_price, material, width, height, price_per_sq_ft) VALUES ('SignX', 50, 'Aluminum', 10, 2, 2.5)")
    cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (1,1,3)")
    conn.commit(); conn.close()
    data = dm.get_project_estimate(project_id)
    assert data, 'Estimate should not be empty'
    totals = [row['Total'] for row in data if row['Item'] == 'SignX']
    assert totals and totals[0] == 150, 'Total should be quantity * unit_price'
