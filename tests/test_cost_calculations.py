import sqlite3
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent / 'utils'))
from calculations import CostCalculator
from database import DatabaseManager

TEST_DB = 'test_costs.db'

def setup_module(module):
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()
    # Init DB and seed minimal data
    dbm = DatabaseManager(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    cur = conn.cursor()
    # Seed sign type with unit price and dimensions
    cur.execute("INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height) VALUES (?,?,?,?,?,?,?)",
                ('Room ID', 'ADA room id sign', 50.0, 'Aluminum', 0.0, 8, 2))
    # Seed material pricing
    cur.execute("INSERT INTO material_pricing (material_name, price_per_sq_ft) VALUES (?,?)",
                ('Aluminum', 12.0))
    conn.commit()
    conn.close()


def teardown_module(module):
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


def test_calculate_sign_cost_methods():
    calc = CostCalculator(TEST_DB)
    # sign_type_id should be 1 from seed
    result = calc.calculate_sign_cost(1, quantity=3)
    assert 'cost_methods' in result
    # Unit price method expected
    assert 'unit_price' in result['cost_methods']
    unit_total = result['cost_methods']['unit_price']['total_cost']
    assert unit_total == 150.0


def test_best_cost_method_priority():
    calc = CostCalculator(TEST_DB)
    # Force scenario where we add price_per_sq_ft so two methods exist
    conn = sqlite3.connect(TEST_DB)
    conn.execute("UPDATE sign_types SET price_per_sq_ft=? WHERE id=1", (10.0,))
    conn.commit()
    conn.close()

    result = calc.calculate_sign_cost(1, quantity=2)
    # Should still prefer unit_price over sq_ft_material or sq_ft_sign
    best = calc.get_best_cost_method(result['cost_methods'])
    assert best['method'] == 'Unit Price'
