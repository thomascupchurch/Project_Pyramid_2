"""PDF export utilities for estimate generation with diagnostics.

Provides a single main function:
    generate_estimate_pdf(table_data, summary_text, title, database_path) -> (bytes, diag)

diag is a dict containing size, sha1, row_count, exterior_count, interior_count, eof_present, head_signature.
"""
from __future__ import annotations

import io
import base64
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Iterable
import sqlite3
import pandas as pd


def _collect_image_map(database_path: str) -> dict:
    image_map = {}
    try:
        conn = sqlite3.connect(database_path)
        idf = pd.read_sql_query('SELECT name, image_path FROM sign_types WHERE image_path IS NOT NULL AND image_path<>""', conn)
        conn.close()
        for _, ir in idf.iterrows():
            ip = ir['image_path']
            if ip and Path(ip).exists():
                image_map[ir['name'].lower()] = Path(ip)
    except Exception as e:
        print(f"[pdf][image-map][warn] {e}")
    return image_map


def _install_type_map(database_path: str) -> dict:
    install_map = {}
    try:
        conn = sqlite3.connect(database_path)
        it_df = pd.read_sql_query('SELECT name, install_type FROM sign_types', conn)
        conn.close()
        install_map = {name.lower(): (it or '') for name, it in it_df.values}
    except Exception as e:
        print(f"[pdf][install-map][warn] {e}")
    return install_map


def _make_thumb(path: Path) -> str | None:
    try:
        if path.suffix.lower() == '.svg':
            import cairosvg, tempfile as _tmp
            tmpf = _tmp.NamedTemporaryFile(suffix='.png', delete=False)
            cairosvg.svg2png(url=str(path), write_to=tmpf.name, output_width=120)
            return tmpf.name
        from PIL import Image as PILImage
        import tempfile as _tmp
        im = PILImage.open(path).convert('RGBA')
        im.thumbnail((110, 55))
        tmpf = _tmp.NamedTemporaryFile(suffix='.png', delete=False)
        im.save(tmpf.name, format='PNG')
        return tmpf.name
    except Exception as e:
        print(f"[pdf][thumb][warn] {e}")
        return None


def generate_estimate_pdf(table_data: List[Dict[str, Any]], summary_text: str, title: str, database_path: str, *, disable_logo: bool = False, embed_images: bool = True, multi_image_lookup: Dict[str, List[str]] | None = None) -> Tuple[bytes, Dict[str, Any]]:
    """Build the estimate PDF and return raw bytes plus diagnostics.

    The ordering groups exterior (install_type substring 'ext') first then others.
    """
    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Flowable)
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfgen import canvas as _canvas

    buf_local = io.BytesIO()
    styles = getSampleStyleSheet()
    if 'MetaLabel' not in styles:
        styles.add(ParagraphStyle(name='MetaLabel', fontSize=8, textColor=colors.grey, leading=10))
    if 'MetaValue' not in styles:
        styles.add(ParagraphStyle(name='MetaValue', fontSize=9, leading=11))

    title_text = (title or 'Sign Estimation Project Export').strip()

    def _footer(canvas: _canvas.Canvas, doc):
        canvas.saveState()
        footer_text = f"© 2025 LSI Graphics, LLC  |  Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Page {doc.page}"
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(LETTER[0] / 2, 22, footer_text)
        canvas.restoreState()

    doc = SimpleDocTemplate(buf_local, pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=72, bottomMargin=40)
    story = []

    logo_diag = {"attempted": False, "found": False, "rendered": False, "error": None, "candidates": []}
    candidates = [
        Path('assets') / 'LSI_Logo.svg',
        Path('LSI_Logo.svg'),
        Path('assets') / 'lsi_logo.svg',
        Path(__file__).resolve().parent.parent / 'assets' / 'LSI_Logo.svg'
    ]
    logo_diag['candidates'] = [str(p) for p in candidates]
    # prefer first existing
    chosen = None
    if not disable_logo:
        for c in candidates:
            if c.exists():
                chosen = c
                break
    if disable_logo:
        logo_diag['error'] = 'disabled'
    elif not chosen:
        logo_diag['error'] = 'not_found_any'
    else:
        logo_diag['attempted'] = True
        logo_diag['found'] = True
        try:
            try:
                import cairosvg  # noqa: F401
                cairosvg_available = True
            except Exception:
                cairosvg_available = False
            if chosen.suffix.lower() == '.svg' and cairosvg_available:
                import cairosvg, tempfile as _tmp
                tmpf = _tmp.NamedTemporaryFile(suffix='.png', delete=False)
                cairosvg.svg2png(url=str(chosen), write_to=tmpf.name, output_width=300)
                from reportlab.platypus import Image
                story.append(Image(tmpf.name, width=220, height=66))
                story.append(Spacer(1, 16))
                logo_diag['rendered'] = True
            elif chosen.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                from reportlab.platypus import Image
                story.append(Image(str(chosen), width=220, height=66))
                story.append(Spacer(1, 16))
                logo_diag['rendered'] = True
            else:
                logo_diag['error'] = f'unsupported_or_missing_renderer(cairosvg_available={cairosvg_available})'
        except Exception as _le:
            logo_diag['error'] = repr(_le)
    # If logo failed to render, insert a textual header spacer for consistent layout
    if not logo_diag.get('rendered'):
        story.append(Paragraph('<para align="left"><font size=16 color="#1f4e79"><b>LSI Graphics</b></font></para>', styles['Normal']))
        story.append(Spacer(1, 10))
    else:
        try:
            print(f"[pdf][logo] rendered path={chosen} candidates={logo_diag.get('candidates')}")
        except Exception:
            pass

    story.append(Paragraph(f'<para align="left"><font size=20><b>{title_text}</b></font></para>', styles['Normal']))
    story.append(Spacer(1, 12))
    if summary_text.strip():
        story.append(Paragraph(summary_text, styles['BodyText']))
        story.append(Spacer(1, 14))

    total_value = 0.0
    building_totals = {}
    for r in table_data:
        try:
            amt = float(r.get('Total') or 0)
        except Exception:
            amt = 0.0
        total_value += amt
        b = r.get('Building')
        if b and b not in ('ALL', ''):
            building_totals[b] = building_totals.get(b, 0) + amt

    meta_rows = [
        ['Generated', datetime.now().strftime('%Y-%m-%d %H:%M')],
        ['Total Value', f"$ {total_value:,.2f}"]
    ]
    for name, val in sorted(building_totals.items(), key=lambda x: x[1], reverse=True)[:3]:
        meta_rows.append([f"Building: {name}", f"$ {val:,.2f}"])
    meta_tbl = Table(meta_rows, hAlign='LEFT', colWidths=[130, 200])
    meta_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 1)
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 18))

    image_map = _collect_image_map(database_path)
    install_map = _install_type_map(database_path)

    def _norm_item_name(item: str):
        return (item.split('Group:')[-1].strip() if item.startswith('Group:') else item).lower()

    def _install_sort_key(row: dict):
        nm = _norm_item_name(row.get('Item', ''))
        it = install_map.get(nm, row.get('install_type', '') or '')
        it_l = it.lower()
        is_ext = 'ext' in it_l
        return (0 if is_ext else 1, row.get('Building', '') or '', nm)

    try:
        sorted_table_data = sorted(table_data, key=_install_sort_key)
    except Exception:
        sorted_table_data = table_data

    headers = ['Img', 'Building', 'Item', 'Material', 'Dimensions', 'Qty', 'Unit $', 'Line Total']
    rows = [headers]

    def fmt_money(v):
        try:
            return f"$ {float(v):,.2f}" if str(v).strip() != '' else ''
        except Exception:
            return str(v)

    exterior_count = interior_count = 0
    exterior_subtotal = 0.0
    interior_subtotal = 0.0
    # Use Paragraph for wrapping text-heavy columns
    from reportlab.lib.styles import ParagraphStyle
    if 'CellSmall' not in styles:
        styles.add(ParagraphStyle(name='CellSmall', fontSize=8, leading=9))
    cell_style = styles['CellSmall']

    data_row_indices = []  # track indices of actual sign rows (for diagnostics)
    from utils.image_cache import get_or_build_thumbnail
    for r in sorted_table_data:
        item = r.get('Item', '')
        base_item = item.split('Group:')[-1].strip() if item.startswith('Group:') else item
        img_flow = ''
        if embed_images:
            thumb = image_map.get(base_item.lower())
            if thumb:
                tp = get_or_build_thumbnail(thumb, 110, 55)
                if tp and Path(tp).exists():
                    try:
                        from reportlab.platypus import Image as RLImage
                        img_flow = RLImage(str(tp), width=50, height=28, kind='proportional')
                    except Exception:
                        img_flow = ''
        it_raw = install_map.get(base_item.lower(), r.get('install_type', '') or '')
        is_ext = 'ext' in (it_raw or '').lower()
        if is_ext:
            exterior_count += 1
        else:
            interior_count += 1
        try:
            lt = float(r.get('Total') or 0)
        except Exception:
            lt = 0.0
        if is_ext:
            exterior_subtotal += lt
        else:
            interior_subtotal += lt
        # Wrap longer text fields
        item_para = Paragraph(str(item), cell_style)
        material_para = Paragraph(str(r.get('Material', '')), cell_style)
        dim_para = Paragraph(str(r.get('Dimensions', '')), cell_style)
        rows.append([
            img_flow,
            Paragraph(str(r.get('Building', '')), cell_style),
            item_para,
            material_para,
            dim_para,
            Paragraph(str(r.get('Quantity', '')), cell_style),
            Paragraph(fmt_money(r.get('Unit_Price', '')), cell_style),
            Paragraph(fmt_money(r.get('Total', '')), cell_style)
        ])
        data_row_indices.append(len(rows)-1)

    from reportlab.platypus import Table as RLTable, TableStyle as RLTableStyle, Paragraph as RLParagraph
    # Adjusted column widths for better readability
    # If images disabled, remove first column definitions
    if not embed_images:
        # remove Img header cell
        rows = [r[1:] if i==0 else r[1:] for i,r in enumerate(rows)]
        detail_tbl = RLTable(rows, repeatRows=1, colWidths=[60, 150, 90, 70, 34, 55, 65])
    else:
        detail_tbl = RLTable(rows, repeatRows=1, colWidths=[34, 60, 150, 90, 70, 34, 55, 65])
    detail_tbl.setStyle(RLTableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#b0b0b0')),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.Color(0.97, 0.97, 0.97)]),
        ('ALIGN', (-2, 1), (-1, -1), 'RIGHT'),
        ('RIGHTPADDING', (-2, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(detail_tbl)
    # Summary subtotals
    story.append(Spacer(1, 14))
    subtotal_rows = [
        ['Exterior Subtotal', fmt_money(exterior_subtotal)],
        ['Interior Subtotal', fmt_money(interior_subtotal)],
        ['Grand Total', fmt_money(exterior_subtotal + interior_subtotal)]
    ]
    subtotal_tbl = Table(subtotal_rows, hAlign='LEFT', colWidths=[130, 100])
    subtotal_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#333333')),
        ('TEXTCOLOR', (1, -1), (1, -1), colors.HexColor('#1f4e79')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 0.25, colors.HexColor('#1f4e79')),
    ]))
    story.append(subtotal_tbl)
    story.append(Spacer(1, 18))
    story.append(Paragraph('<font size=8 color="#555555">Prepared using the internal Sign Estimation Tool. Figures are for estimation purposes only.</font>', styles['Normal']))

    # Appendix pages for multi-images (basic stub): show additional images if provided in multi_image_lookup
    if embed_images and multi_image_lookup:
        from reportlab.platypus import PageBreak, Image as RLImage
        for sign_name, paths in multi_image_lookup.items():
            extra = [p for p in paths if Path(p).exists()]
            if len(extra) <= 1:
                continue
            story.append(PageBreak())
            story.append(Paragraph(f"<b>Additional Images: {sign_name}</b>", styles['Normal']))
            story.append(Spacer(1, 8))
            for p in extra[1:]:  # skip cover (assumed first)
                thumbp = get_or_build_thumbnail(p, 300, 180) or p
                try:
                    story.append(RLImage(str(thumbp), width=260, height=140))
                    story.append(Spacer(1, 6))
                except Exception:
                    continue
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buf_local.seek(0)
    pdf_bytes = buf_local.read()
    # Optional debug dump (environment controlled) to inspect Acrobat issues
    try:
        if Path('.pdf_debug').exists():
            dbg_dir = Path('.pdf_debug'); dbg_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            with open(dbg_dir / f'estimate_{ts}.pdf', 'wb') as fdbg:
                fdbg.write(pdf_bytes)
    except Exception as _dbg_e:
        print(f"[pdf][debug-dump][warn] {_dbg_e}")
    diag = {
        'size': len(pdf_bytes),
        'sha1': hashlib.sha1(pdf_bytes).hexdigest(),
        'row_count': len(data_row_indices),  # only actual sign rows
        'exterior_count': exterior_count,
        'interior_count': interior_count,
        'head_signature': pdf_bytes[:8],
        'eof_present': b'%%EOF' in pdf_bytes[-1024:],
        'logo': logo_diag,
    }
    return pdf_bytes, diag


def build_download_dict(pdf_bytes: bytes) -> dict:
    return {
        'content': base64.b64encode(pdf_bytes).decode(),
        'filename': 'estimate.pdf',
        'type': 'application/pdf'
    }
