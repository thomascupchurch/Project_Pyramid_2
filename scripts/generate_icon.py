"""Generate an .ico file from the existing SVG logo.

Requires cairosvg and Pillow (already in requirements). If execution fails gracefully
prints an explanatory message. The output is placed at assets/LSI_Logo.ico.

Usage:
  python scripts/generate_icon.py
"""
from pathlib import Path
import sys

try:
    import cairosvg  # type: ignore
    from PIL import Image  # type: ignore
except Exception as e:  # noqa: BLE001
    print(f"[icon][error] Required libraries missing: {e}. Ensure cairosvg and pillow installed.")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / 'assets' / 'LSI_Logo.svg'
ICO = ROOT / 'assets' / 'LSI_Logo.ico'
TMP_PNG = ROOT / 'assets' / '_logo_tmp.png'

if not SVG.exists():
    print(f"[icon][error] SVG not found: {SVG}")
    sys.exit(2)

try:
    cairosvg.svg2png(url=str(SVG), write_to=str(TMP_PNG), output_width=256, output_height=256)
    img = Image.open(TMP_PNG).convert('RGBA')
    # Multi-resolution icon sizes
    sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
    img.save(ICO, format='ICO', sizes=sizes)
    TMP_PNG.unlink(missing_ok=True)
    print(f"[icon] Generated icon at {ICO}")
except Exception as e:  # noqa: BLE001
    print(f"[icon][error] Failed to generate icon: {e}")
    sys.exit(3)
