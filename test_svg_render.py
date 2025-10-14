import os
import pytest

# This test exercises CairoSVG, which requires native Cairo DLLs on Windows.
# On environments without Cairo installed, we skip to keep the suite green.
try:
	import cairosvg  # type: ignore
except Exception as e:  # ImportError or OSError when libcairo is missing
	pytest.skip(f"cairosvg not available: {e}", allow_module_level=True)

svg = "<svg xmlns='http://www.w3.org/2000/svg' width='50' height='20'><rect width='50' height='20' fill='red'/></svg>"
cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to="test_cairo.png")
print("Rendered:", os.path.getsize("test_cairo.png"), "bytes")
