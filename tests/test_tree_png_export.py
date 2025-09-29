import pytest

# We'll test the export_tree_png function by importing from app.
# If kaleido is missing, function returns a fallback image with guidance.

from app import export_tree_png

def test_tree_png_export_basic():
    # Minimal fake figure dict: Plotly expects 'data' and 'layout'
    fig_dict = {
        'data': [{'type':'scatter','x':[0,1],'y':[0,1]}],
        'layout': {'title':'Test'}
    }
    # Simulate click
    result = export_tree_png(1, fig_dict)
    assert result is not None
    assert result['filename'].endswith('.png')
    # Ensure content decodes from base64
    import base64
    raw = base64.b64decode(result['content'])
    # PNG magic number check
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    assert len(raw) > 100  # some minimal size
