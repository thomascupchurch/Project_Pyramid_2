import io, base64, hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def main():
    # Simple deterministic PNG to validate signature recognition pipeline
    img = Image.new('RGB', (320, 120), 'white')
    d = ImageDraw.Draw(img)
    text = 'PNG SELFTEST'
    try:
        font = ImageFont.truetype('Arial.ttf', 20)
    except Exception:
        font = ImageFont.load_default()
    d.text((10,40), text, fill='black', font=font)
    buff = io.BytesIO()
    img.save(buff, format='PNG')
    data = buff.getvalue()
    print('[png-selftest] size=', len(data), 'sig=', data[:8], 'sha1=', hashlib.sha1(data).hexdigest()[:12])
    b64 = base64.b64encode(data).decode()
    # Simulate dash download dict structure
    out = dict(content=b64, filename='selftest.png', type='image/png')
    print('[png-selftest] download dict keys:', list(out.keys()))
    # Quick heuristic validation like the app
    assert data.startswith(b'\x89PNG\r\n\x1a\n'), 'PNG signature mismatch'
    assert b'IEND' in data[-64:], 'PNG missing IEND chunk near tail'
    print('[png-selftest] PASS')

if __name__ == '__main__':
    main()
