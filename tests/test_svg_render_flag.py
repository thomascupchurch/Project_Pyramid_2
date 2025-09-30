import importlib
from pathlib import Path
import pytest
from utils.pdf_export import generate_estimate_pdf

SAMPLE_ROWS = [
    {
        'Building': 'A',
        'Item': 'SVG Sign',
        'Material': 'Aluminum',
        'Dimensions': '10x20',
        'Quantity': 1,
        'Unit_Price': 100.0,
        'Total': 100.0,
        'install_type': 'Exterior'
    }
]


def test_svg_render_flag():
    db_path = Path('sign_estimation.db')
    assert db_path.exists(), 'DB missing for test'
    logo_svg = Path('assets/LSI_Logo.svg')
    if not logo_svg.exists():
        pytest.skip('Logo SVG asset not present; skipping SVG render flag test.')
    cairosvg_available = importlib.util.find_spec('cairosvg') is not None
    if not cairosvg_available:
        pytest.skip('cairosvg not installed; skipping SVG render flag assertion.')
    # With cairosvg available and SVG present, svg_render_enabled should become True unless disabled
    pdf_bytes, diag = generate_estimate_pdf(SAMPLE_ROWS, 'Summary', 'SVG Flag PDF', str(db_path), disable_logo=False, embed_images=False)
    assert 'svg_render_enabled' in diag
    # If logo rendered and is svg, svg_render_enabled should be True. If it's False, provide detailed diagnostics.
    if diag.get('logo', {}).get('rendered') and str(logo_svg).lower().endswith('.svg'):
        assert diag['svg_render_enabled'] is True, f"Expected svg_render_enabled True when SVG logo rendered. diag={diag}"
    else:
        # If logo didn't render as SVG (fallback path), we just assert field is boolean.
        assert isinstance(diag['svg_render_enabled'], bool)