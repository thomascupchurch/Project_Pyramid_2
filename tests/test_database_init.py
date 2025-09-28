import os
import sqlite3
from pathlib import Path

# Ensure we import from utils
import sys
sys.path.append(str(Path(__file__).parent.parent / 'utils'))

from database import DatabaseManager

TEST_DB = 'test_sign_estimation.db'

def setup_module(module):
    # Remove old test db if exists
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


def teardown_module(module):
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


def test_database_initialization_creates_tables():
    dbm = DatabaseManager(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")] 

    expected = {
        'projects','buildings','sign_types','sign_groups','sign_group_members',
        'building_signs','building_sign_groups','material_pricing'
    }
    missing = expected.difference(tables)
    assert not missing, f"Missing tables: {missing}"
    conn.close()
