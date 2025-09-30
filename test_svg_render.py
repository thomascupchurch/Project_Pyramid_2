import cairosvg, os
svg = "<svg xmlns='http://www.w3.org/2000/svg' width='50' height='20'><rect width='50' height='20' fill='red'/></svg>"
cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to="test_cairo.png")
print("Rendered:", os.path.getsize("test_cairo.png"), "bytes")
