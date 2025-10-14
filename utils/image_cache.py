"""Image thumbnail caching utilities.

get_or_build_thumbnail(src_path, max_w, max_h) -> Path | None

Creates a cached PNG thumbnail for raster images (and SVG if cairosvg available).
Cache key is sha1(file_bytes + size spec). Thumbnails stored under:
    sign_images/.cache/thumbnails/<sha1>_<w>x<h>.png

Safe for concurrent calls (best-effort). If generation fails returns None.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import hashlib
import io

CACHE_ROOT = Path('sign_images') / '.cache' / 'thumbnails'


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def get_or_build_thumbnail(src_path: str | Path, max_w: int, max_h: int) -> Optional[Path]:
    try:
        p = Path(src_path)
        if not p.exists() or p.is_dir():
            return None
        try:
            raw = p.read_bytes()
        except Exception:
            return None
        key = _hash_bytes(raw + f"{max_w}x{max_h}".encode())
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        out_path = CACHE_ROOT / f"{key}_{max_w}x{max_h}.png"
        if out_path.exists():
            return out_path
        # Build thumbnail
        if p.suffix.lower() == '.svg':
            # Try CairoSVG first; if it fails (native Cairo missing), try sibling raster fallbacks
            try:
                import cairosvg
                cairosvg.svg2png(url=str(p), write_to=str(out_path), output_width=max_w)
                return out_path if out_path.exists() else None
            except Exception:
                # Fallback: look for a raster with same basename in same folder or assets/
                base = p.stem
                candidates = [
                    p.with_suffix('.png'), p.with_suffix('.jpg'), p.with_suffix('.jpeg'),
                    Path('assets') / f"{base}.png",
                    Path('assets') / f"{base}.jpg",
                    Path('assets') / f"{base}.jpeg",
                ]
                for rp in candidates:
                    try:
                        if rp.exists():
                            from PIL import Image as PILImage  # type: ignore
                            with PILImage.open(rp) as im:
                                im = im.convert('RGBA')
                                im.thumbnail((max_w, max_h))
                                im.save(out_path, format='PNG')
                            return out_path if out_path.exists() else None
                    except Exception:
                        continue
                return None
        from PIL import Image as PILImage  # type: ignore
        with PILImage.open(p) as im:
            im = im.convert('RGBA')
            im.thumbnail((max_w, max_h))
            im.save(out_path, format='PNG')
        return out_path if out_path.exists() else None
    except Exception:
        return None
