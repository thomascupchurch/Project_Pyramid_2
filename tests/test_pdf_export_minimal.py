import os
from pathlib import Path
from utils.pdf_export import generate_estimate_pdf

# Minimal synthetic table row
SAMPLE_ROWS = [
    {
        'Building': 'A',
        'Item': 'Test Sign',
        'Material': 'Aluminum',
        'Dimensions': '24x36',
        'Quantity': 2,
        'Unit_Price': 150.0,
        'Total': 300.0,
        'install_type': 'Exterior'
    },
    {
        'Building': 'B',
        'Item': 'Interior Panel',
        'Material': 'PVC',
        'Dimensions': '12x18',
        'Quantity': 1,
        'Unit_Price': 90.0,
        'Total': 90.0,
        'install_type': 'Interior'
    }
]

def test_generate_estimate_pdf_signature(tmp_path):
    # Use existing DB path (assumes migrations already ran)
    db_path = Path('sign_estimation.db')
    assert db_path.exists(), 'Database file missing for PDF export test'
    pdf_bytes, diag = generate_estimate_pdf(SAMPLE_ROWS, 'Summary text here', 'Unit Test PDF', str(db_path))
    # Basic structure checks
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 500, f"PDF unexpectedly small: {len(pdf_bytes)} bytes"
    assert pdf_bytes.startswith(b'%PDF'), 'Missing PDF header'
    assert b'%%EOF' in pdf_bytes[-1024:], 'Missing EOF marker near end'
    # Diagnostics expectations
    assert diag['row_count'] == 2, diag
    assert diag['exterior_count'] == 1, diag
    assert diag['interior_count'] == 1, diag
    assert diag['eof_present'] is True, diag
    # Ensure deterministic fields exist
    for key in ['sha1','size','head_signature']:
        assert key in diag
