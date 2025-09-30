from pathlib import Path
from utils.pdf_export import generate_estimate_pdf

SAMPLE_ROWS = [
    {
        'Building': 'A',
        'Item': 'Appendix Sign',
        'Material': 'Steel',
        'Dimensions': '10x10',
        'Quantity': 1,
        'Unit_Price': 42.0,
        'Total': 42.0,
        'install_type': 'Exterior'
    }
]

def test_pdf_appendix_count(tmp_path):
    db_path = Path('sign_estimation.db')
    assert db_path.exists(), 'DB missing'
    # Simulate multi-image lookup (cover + 2 extras) using placeholder system images; Path existence required.
    # We'll point to the same logo asset multiple times if it exists to simulate.
    logo = Path('assets/LSI_Logo.svg')
    if not logo.exists():
        # Skip if logo asset absent; test environment must have at least one existing file
        return
    multi_lookup = {
        'Appendix Sign': [str(logo), str(logo), str(logo)]
    }
    pdf_bytes, diag = generate_estimate_pdf(SAMPLE_ROWS, 'Summary', 'Appendix PDF', str(db_path), disable_logo=True, embed_images=True, multi_image_lookup=multi_lookup)
    assert diag.get('appendix_count') == 1, diag
