import os
from pathlib import Path
from utils.pdf_export import generate_estimate_pdf
from utils.image_cache import get_or_build_thumbnail

SAMPLE_ROWS = [
    {
        'Building': 'A',
        'Item': 'Cache Test Sign',
        'Material': 'Alum',
        'Dimensions': '5x5',
        'Quantity': 1,
        'Unit_Price': 25.0,
        'Total': 25.0,
        'install_type': 'Exterior'
    }
]

def test_pdf_without_images_has_no_image_column(tmp_path):
    db_path = Path('sign_estimation.db')
    assert db_path.exists(), 'DB missing'
    pdf_bytes, diag = generate_estimate_pdf(SAMPLE_ROWS, 'Summary', 'No Img', str(db_path), disable_logo=True, embed_images=False)
    assert diag.get('image_column') is False


def test_thumbnail_cache_roundtrip(tmp_path):
    # Attempt to build a thumbnail for existing asset (logo)
    logo = Path('assets/LSI_Logo.svg')
    if not logo.exists():
        return
    thumb1 = get_or_build_thumbnail(logo, 110, 55)
    thumb2 = get_or_build_thumbnail(logo, 110, 55)
    assert thumb1 == thumb2, 'Cache should return same path for identical requests'
    assert thumb1 is not None and Path(thumb1).exists()
