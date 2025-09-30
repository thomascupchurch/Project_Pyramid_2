from pathlib import Path
from utils.pdf_export import generate_estimate_pdf

SAMPLE_ROWS = [
    {
        'Building': 'A',
        'Item': 'Sign One',
        'Material': 'Aluminum',
        'Dimensions': '10x20',
        'Quantity': 1,
        'Unit_Price': 100.0,
        'Total': 100.0,
        'install_type': 'Exterior'
    },
    {
        'Building': 'B',
        'Item': 'Sign Two',
        'Material': 'PVC',
        'Dimensions': '12x18',
        'Quantity': 2,
        'Unit_Price': 50.0,
        'Total': 100.0,
        'install_type': 'Interior'
    }
]

def test_pdf_extended_diagnostics_embed_true(tmp_path):
    db_path = Path('sign_estimation.db')
    assert db_path.exists(), 'DB missing'
    pdf_bytes, diag = generate_estimate_pdf(SAMPLE_ROWS, 'Summary', 'Diag PDF', str(db_path), disable_logo=True, embed_images=True)
    assert diag.get('embed_images') is True
    assert diag.get('image_column') is True
    assert diag.get('appendix_count') == 0  # no multi_image_lookup provided
    assert 'svg_render_enabled' in diag  # presence check
    assert isinstance(diag.get('svg_render_enabled'), bool)


def test_pdf_extended_diagnostics_embed_false(tmp_path):
    db_path = Path('sign_estimation.db')
    assert db_path.exists(), 'DB missing'
    pdf_bytes, diag = generate_estimate_pdf(SAMPLE_ROWS, 'Summary', 'Diag PDF', str(db_path), disable_logo=True, embed_images=False)
    assert diag.get('embed_images') is False
    assert diag.get('image_column') is False
    assert diag.get('appendix_count') == 0
    assert 'svg_render_enabled' in diag
    assert isinstance(diag.get('svg_render_enabled'), bool)
