import sqlite3
from pathlib import Path
import sys

# Ensure utils on path
sys.path.append(str(Path(__file__).parent.parent / 'utils'))
from database import DatabaseManager

TEST_DB = 'test_groups_materials.db'

def setup_module(module):
    p = Path(TEST_DB)
    if p.exists():
        p.unlink()

def teardown_module(module):
    p = Path(TEST_DB)
    if p.exists():
        p.unlink()

def _open():
    return sqlite3.connect(TEST_DB)

def test_group_creation_member_assignment_and_estimate():
    dbm = DatabaseManager(TEST_DB)
    conn = _open(); cur = conn.cursor()
    # Seed sign type ( dimensions for material recalculation )
    cur.execute("INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height) VALUES (?,?,?,?,?,?,?)",
                ('TestSign','Desc',0.0,'Aluminum',0.0,10,2))
    # Seed material pricing
    cur.execute("INSERT INTO material_pricing (material_name, price_per_sq_ft) VALUES (?,?)", ('Aluminum',5.0))
    # Seed project & building
    cur.execute("INSERT INTO projects (name, description, sales_tax_rate, installation_rate, include_installation, include_sales_tax) VALUES (?,?,?,?,?,?)",
                ('Proj1','Test',0.0,0.0,0,0))
    project_id = cur.lastrowid
    cur.execute("INSERT INTO buildings (project_id, name, description) VALUES (?,?,?)", (project_id,'Bldg1','B'))
    building_id = cur.lastrowid
    conn.commit(); conn.close()

    # Recalculate pricing from materials
    updated = dbm.recalc_prices_from_materials()
    assert updated == 1, "Expected exactly one sign type to be recalculated"
    conn = _open()
    price = conn.execute("SELECT unit_price FROM sign_types WHERE name='TestSign'").fetchone()[0]
    conn.close()
    assert price == 100.0, f"Unit price should be 100.0 (10*2*5) got {price}"

    # Create group and add member (quantity 2)
    conn = _open(); cur = conn.cursor()
    cur.execute("INSERT INTO sign_groups (name, description) VALUES (?,?)", ('GroupA','G'))
    group_id = cur.lastrowid
    sign_id = 1
    cur.execute("INSERT INTO sign_group_members (group_id, sign_type_id, quantity) VALUES (?,?,?)", (group_id, sign_id, 2))
    # Assign group to building quantity 3
    cur.execute("INSERT INTO building_sign_groups (building_id, group_id, quantity) VALUES (?,?,?)", (building_id, group_id, 3))
    conn.commit(); conn.close()

    estimate = dbm.get_project_estimate(project_id)
    assert estimate, "Estimate should not be empty"
    # Find group line
    group_line = next((r for r in estimate if r['Item'] == 'Group: GroupA'), None)
    assert group_line is not None, "Group line not found in estimate"
    # group member total per group = unit_price (100) * member qty (2) = 200; building assignment qty=3 => 600
    assert group_line['Unit_Price'] == 200.0, f"Expected group unit price 200 got {group_line['Unit_Price']}"
    assert group_line['Total'] == 600.0, f"Expected group total 600 got {group_line['Total']}"

def test_material_recalc_updates_changed_rate():
    dbm = DatabaseManager(TEST_DB)
    conn = _open(); cur = conn.cursor()
    # Ensure sign & material exist (previous test may have removed DB so reseed if needed)
    if not cur.execute("SELECT 1 FROM sign_types WHERE name='TestSign'").fetchone():
        cur.execute("INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height) VALUES (?,?,?,?,?,?,?)",
                    ('TestSign','Desc',0.0,'Aluminum',0.0,10,2))
    if not cur.execute("SELECT 1 FROM material_pricing WHERE material_name='Aluminum'").fetchone():
        cur.execute("INSERT INTO material_pricing (material_name, price_per_sq_ft) VALUES (?,?)", ('Aluminum',5.0))
    conn.commit(); conn.close()

    # First recalc should set 100
    dbm.recalc_prices_from_materials()
    conn = _open(); price1 = conn.execute("SELECT unit_price FROM sign_types WHERE name='TestSign'").fetchone()[0]; conn.close()
    assert price1 == 100.0
    # Update material rate
    conn = _open(); conn.execute("UPDATE material_pricing SET price_per_sq_ft=7.5 WHERE material_name='Aluminum'"); conn.commit(); conn.close()
    dbm.recalc_prices_from_materials()
    conn = _open(); price2 = conn.execute("SELECT unit_price FROM sign_types WHERE name='TestSign'").fetchone()[0]; conn.close()
    assert price2 == 150.0, f"Expected updated unit price 150 got {price2}"
