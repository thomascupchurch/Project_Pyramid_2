"""Generate a sample estimate PDF outside Dash for quick validation.

Usage:
  python scripts/pdf_export_selftest.py output.pdf
If output path omitted, writes sample_estimate.pdf in CWD.
"""
from __future__ import annotations
import sys, io, base64, sqlite3
from pathlib import Path
from datetime import datetime

DB = Path('sign_estimation.db')
if not DB.exists():
    print('[warn] sign_estimation.db not found; creating in-memory sample for test')

def build_sample_rows():
    return [
        {'Building':'B1','Item':'Sample Sign A','Material':'Aluminum','Dimensions':'4x2','Quantity':2,'Unit_Price':120,'Total':240},
        {'Building':'B1','Item':'Sample Sign B','Material':'PVC','Dimensions':'3x1.5','Quantity':5,'Unit_Price':60,'Total':300},
        {'Building':'B2','Item':'Large Panel','Material':'Acrylic','Dimensions':'10x4','Quantity':1,'Unit_Price':950,'Total':950},
    ]

def build_pdf(table_data, title='Self-Test Estimate PDF') -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=60, bottomMargin=40)
    story = []
    story.append(Paragraph(f'<font size=20><b>{title}</b></font>', styles['Normal']))
    story.append(Spacer(1,12))
    total = sum(float(r.get('Total') or 0) for r in table_data)
    story.append(Paragraph(f'Total Value: $ {total:,.2f}', styles['Normal']))
    story.append(Spacer(1,16))
    headers = ['Building','Item','Material','Dimensions','Qty','Unit $','Line Total']
    rows = [headers]
    def m(v):
        try: return f"$ {float(v):,.2f}" if v not in (None,'') else ''
        except: return str(v)
    for r in table_data:
        rows.append([
            r.get('Building',''), r.get('Item',''), r.get('Material',''), r.get('Dimensions',''),
            r.get('Quantity',''), m(r.get('Unit_Price','')), m(r.get('Total',''))
        ])
    tbl = Table(rows, repeatRows=1, colWidths=[70,120,70,70,30,55,70])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#1f4e79')),
        ('TEXTCOLOR',(0,0),(-1,0), colors.whitesmoke),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,0),9),
        ('GRID',(0,0),(-1,-1),0.25, colors.HexColor('#b0b0b0')),
        ('FONTSIZE',(0,1),(-1,-1),7),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.whitesmoke, colors.Color(0.97,0.97,0.97)])
    ]))
    story.append(tbl)
    story.append(Spacer(1,18))
    story.append(Paragraph('<font size=7 color="#666666">© 2025 LSI Graphics, LLC — Test Export</font>', styles['Normal']))
    doc.build(story)
    buf.seek(0)
    return buf.read()

def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('sample_estimate.pdf')
    pdf_bytes = build_pdf(build_sample_rows())
    out.write_bytes(pdf_bytes)
    print(f'Wrote {out} ({len(pdf_bytes)} bytes)')
    if not pdf_bytes.startswith(b'%PDF'):
        print('[warn] PDF does not start with %PDF header')
    else:
        print('[ok] PDF header validated')

if __name__ == '__main__':
    main()
