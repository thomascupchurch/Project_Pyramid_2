import sqlite3
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent / 'utils'))
from database import DatabaseManager
from estimate_core import compute_custom_estimate

TEST_DB = 'test_multi_building.db'


def setup_module(module):
    p = Path(TEST_DB)
    if p.exists():
        p.unlink()


def teardown_module(module):
    p = Path(TEST_DB)
    if p.exists():
        p.unlink()


def seed_multi():
    dbm = DatabaseManager(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    cur = conn.cursor()
    # Project with tax + install percent
    cur.execute("INSERT INTO projects (name, sales_tax_rate, include_sales_tax, installation_rate, include_installation) VALUES (?,?,?,?,?)", ('Proj',0.07,1,0.10,1))
    pid = cur.lastrowid
    # Two buildings
    cur.execute("INSERT INTO buildings (project_id, name) VALUES (?,?)", (pid,'Building A'))
    b1 = cur.lastrowid
    cur.execute("INSERT INTO buildings (project_id, name) VALUES (?,?)", (pid,'Building B'))
    b2 = cur.lastrowid
    # Sign types
    cur.execute("INSERT INTO sign_types (name, unit_price, material, width, height) VALUES (?,?,?,?,?)", ('Type1',100,'Metal',10,10))
    cur.execute("INSERT INTO sign_types (name, unit_price, material, width, height) VALUES (?,?,?,?,?)", ('Type2',50,'Metal',5,5))
    # Assign signs: Building A gets Type1 x2; Building B gets Type2 x4
    cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)", (b1,1,2))  # 2*100=200
    cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)", (b2,2,4))  # 4*50=200
    conn.commit(); conn.close()
    return dbm, pid, (b1,b2)


def test_multi_building_subset_filter():
    dbm, pid, (b1,b2) = seed_multi()
    # Compute full project (both buildings) meta
    all_rows, meta_all = compute_custom_estimate(TEST_DB, pid, None, 'per_sign','percent',0.10,0,0,0,0,False, return_meta=True)
    assert any(r['Building']=='Building A' for r in all_rows)
    assert any(r['Building']=='Building B' for r in all_rows)
    subtotal_all = meta_all['grand_subtotal']
    assert abs(subtotal_all - 400) < 0.01
    # Now restrict to a single building (b1)
    rows_one, meta_one = compute_custom_estimate(TEST_DB, pid, [b1], 'per_sign','percent',0.10,0,0,0,0,False, return_meta=True)
    assert any(r['Building']=='Building A' for r in rows_one)
    assert not any(r['Building']=='Building B' for r in rows_one)
    subtotal_one = meta_one['grand_subtotal']
    assert abs(subtotal_one - 200) < 0.01
    # Ensure install line present
    assert any(r['Item']=='Installation' for r in rows_one)
    # Sales tax line present
    assert any(r['Item']=='Sales Tax' for r in rows_one)
    # Meta sign count matches expected (2 signs)
    assert meta_one['total_sign_count'] == 2
