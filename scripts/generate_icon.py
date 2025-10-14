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
except Exception:
    cairosvg = None  # type: ignore
try:
    from PIL import Image  # type: ignore
except Exception as e:
    print(f"[icon][error] Pillow missing: {e}.")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / 'assets' / 'LSI_Logo.svg'
ICO = ROOT / 'assets' / 'LSI_Logo.ico'
TMP_PNG = ROOT / 'assets' / '_logo_tmp.png'

if not SVG.exists():
    # Allow PNG fallback if present
    PNG_FALLBACK = ROOT / 'assets' / 'LSI_Logo.png'
    if not PNG_FALLBACK.exists():
        print(f"[icon][error] SVG not found and no PNG fallback: {SVG}")
        sys.exit(2)
    try:
        img = Image.open(PNG_FALLBACK).convert('RGBA')
        sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
        img.save(ICO, format='ICO', sizes=sizes)
        print(f"[icon] Generated icon from PNG at {ICO}")
        sys.exit(0)
    except Exception as e:
        print(f"[icon][error] PNG fallback failed: {e}")
        sys.exit(3)

try:
    if cairosvg is not None:
        cairosvg.svg2png(url=str(SVG), write_to=str(TMP_PNG), output_width=256, output_height=256)
        img = Image.open(TMP_PNG).convert('RGBA')
        TMP_PNG.unlink(missing_ok=True)
    else:
        # If SVG cannot be rasterized and PNG fallback exists, use it to avoid Cairo dependency for icon
        PNG_FALLBACK = ROOT / 'assets' / 'LSI_Logo.png'
        if PNG_FALLBACK.exists():
            img = Image.open(PNG_FALLBACK).convert('RGBA')
        else:
            # Fallback: try to open SVG via Pillow (may fail)
            try:
                img = Image.open(SVG).convert('RGBA')
            except Exception as pe:
                print(f"[icon][error] CairoSVG not available and Pillow cannot open SVG: {pe}")
                print("[icon][hint] Install CairoSVG (and Cairo runtime), or add assets/LSI_Logo.png and re-run.")
                sys.exit(4)
    sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
    img.save(ICO, format='ICO', sizes=sizes)
    print(f"[icon] Generated icon at {ICO}")
except Exception as e:  # noqa: BLE001
    print(f"[icon][error] Failed to generate icon: {e}")
    sys.exit(3)
