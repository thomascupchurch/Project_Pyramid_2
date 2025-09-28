import sqlite3
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent / 'utils'))
from database import DatabaseManager

TEST_DB = 'test_mixed_validation.db'

def setup_module(module):
    p = Path(TEST_DB)
    if p.exists():
        p.unlink()

def teardown_module(module):
    p = Path(TEST_DB)
    if p.exists():
        p.unlink()

def _conn():
    return sqlite3.connect(TEST_DB)

def seed_base():
    dbm = DatabaseManager(TEST_DB)
    conn = _conn(); cur = conn.cursor()
    # project with tax/install
    cur.execute("INSERT INTO projects (name, description, sales_tax_rate, installation_rate, include_installation, include_sales_tax) VALUES (?,?,?,?,?,?)",
                ('Proj','P',0.05,0.10,1,1))
    pid = cur.lastrowid
    # buildings
    cur.execute("INSERT INTO buildings (project_id, name, description) VALUES (?,?,?)", (pid,'B1',''))
    bid = cur.lastrowid
    # sign types
    cur.execute("INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height) VALUES (?,?,?,?,?,?,?)",
                ('SignA','',100,'Metal',0,10,10))
    cur.execute("INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height) VALUES (?,?,?,?,?,?,?)",
                ('SignB','',50,'Metal',0,5,5))
    # group with SignB qty2
    cur.execute("INSERT INTO sign_groups (name, description) VALUES (?,?)", ('Group1',''))
    gid = cur.lastrowid
    cur.execute("INSERT INTO sign_group_members (group_id, sign_type_id, quantity) VALUES (?,?,?)", (gid,2,2))
    # assign signs & group
    cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)", (bid,1,3))  # 3 * 100 = 300
    cur.execute("INSERT INTO building_sign_groups (building_id, group_id, quantity) VALUES (?,?,?)", (bid,gid,4))  # group unit: 2*50=100; qty4 => 400
    conn.commit(); conn.close()
    return dbm, pid

def test_mixed_signs_groups_and_adjustments():
    dbm, pid = seed_base()
    est = dbm.get_project_estimate(pid)
    assert est, 'Estimate should have lines'
    total_signA = next(r for r in est if r['Item']=='SignA')['Total']
    assert total_signA == 300
    group_line = next(r for r in est if r['Item']=='Group: Group1')
    assert group_line['Unit_Price'] == 100 and group_line['Total']==400
    # subtotal before adjustments
    subtotal = 300 + 400
    install = subtotal * 0.10
    tax = (subtotal + install) * 0.05
    grand_expected = subtotal + install + tax
    grand_calc = sum(r['Total'] for r in est)
    assert abs(grand_calc - grand_expected) < 0.01, f'Grand total mismatch {grand_calc} vs {grand_expected}'
    # ensure Installation and Sales Tax lines exist
    assert any(r['Item']=='Installation' for r in est)
    assert any(r['Item']=='Sales Tax' for r in est)

def test_duplicate_building_name_enforced():
    dbm = DatabaseManager(TEST_DB)
    conn = _conn(); cur = conn.cursor()
    cur.execute("INSERT INTO projects (name) VALUES (?)", ('DupProj',))
    pid = cur.lastrowid
    cur.execute("INSERT INTO buildings (project_id, name) VALUES (?,?)", (pid,'Same'))
    conn.commit()
    # Attempt duplicate (should violate index)
    try:
        cur.execute("INSERT INTO buildings (project_id, name) VALUES (?,?)", (pid,'Same'))
        conn.commit()
        duplicate_inserted = True
    except Exception:
        duplicate_inserted = False
    conn.close()
    assert not duplicate_inserted, 'Duplicate building name should be prevented'
