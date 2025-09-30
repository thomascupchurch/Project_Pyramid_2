import pytest
from pathlib import Path
from utils.pdf_export import generate_estimate_pdf

SAMPLE_ROWS = [
    {
        'Building': 'HQ',
        'Item': 'Test Sign',
        'Material': 'Acrylic',
        'Dimensions': '12x30',
        'Quantity': 2,
        'Unit_Price': 50.0,
        'Total': 100.0,
        'install_type': 'Exterior'
    }
]

def test_logo_source_present():
    db_path = Path('sign_estimation.db')
    if not db_path.exists():
        pytest.skip('Database missing; skip logo source test.')
    logo_svg = Path('assets/LSI_Logo.svg')
    if not logo_svg.exists():
        pytest.skip('SVG logo asset missing; cannot assert logo_source.')
    pdf_bytes, diag = generate_estimate_pdf(SAMPLE_ROWS, 'Summary', 'Logo Source PDF', str(db_path), disable_logo=False, embed_images=False)
    # Basic structural expectations
    assert isinstance(diag, dict)
    # logo_source should be set when logo asset exists, even if raster failed (diagnostic may show error)
    assert diag.get('logo_source'), f"Expected logo_source to be populated when logo exists. diag={diag}"
    # If logo failed to render, it should record an error; otherwise rendered should be True
    if not diag.get('logo', {}).get('rendered'):
        assert diag.get('logo', {}).get('error'), f"Logo neither rendered nor errored. diag={diag}"
