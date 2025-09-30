from pathlib import Path
from utils.pdf_export import generate_estimate_pdf

SAMPLE_ROWS = [
    {
        'Building': 'A',
        'Item': 'Client Mode Sign',
        'Material': 'ACM',
        'Dimensions': '10x20',
        'Quantity': 1,
        'Unit_Price': 100.0,
        'Total': 100.0,
        'install_type': 'Exterior'
    }
]

NOTES = [
    {'scope': 'Project', 'ref': None, 'text': 'Overall project note visible to client', 'include_in_export': True},
    {'scope': 'Building', 'ref': 'A', 'text': 'Building A facade limitations', 'include_in_export': True},
    {'scope': 'Sign', 'ref': 'Client Mode Sign', 'text': 'Illumination TBD', 'include_in_export': False},  # excluded
]

CHANGE_LOG = [
    {'ts': '2025-09-30 10:00', 'user': 'estimator', 'action': 'snapshot', 'detail': 'Initial version'},
    {'ts': '2025-09-30 11:00', 'user': 'estimator', 'action': 'update', 'detail': 'Adjusted quantity'},
]

def test_client_facing_hides_prices_and_counts_notes(tmp_path):
    db_path = Path('sign_estimation.db')
    assert db_path.exists(), 'DB missing'
    pdf_bytes, diag = generate_estimate_pdf(
        SAMPLE_ROWS,
        'Summary for client',
        'Client Facing PDF',
        str(db_path),
        client_facing=True,
        notes=NOTES,
        change_log=CHANGE_LOG,
    )
    assert diag['client_facing'] is True
    # In client-facing mode unit + line totals hidden
    assert diag['unit_price_hidden'] is True
    assert diag['line_total_hidden'] is True
    # Notes count should only count those include_in_export True (2 of 3)
    assert diag['notes_count'] == 2, diag
    # Change log entries counted
    assert diag['change_log_entries'] == 2, diag
    # Basic PDF invariants
    assert pdf_bytes.startswith(b'%PDF') and b'%%EOF' in pdf_bytes[-1024:]
