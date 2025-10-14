"""PDF export utilities for estimate generation with diagnostics.

Provides a single main function:
    generate_estimate_pdf(table_data, summary_text, title, database_path) -> (bytes, diag)

diag is a dict containing size, sha1, row_count, exterior_count, interior_count, eof_present, head_signature.
"""
from __future__ import annotations

import io
import os
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


def generate_estimate_pdf(
    table_data: List[Dict[str, Any]],
    summary_text: str,
    title: str,
    database_path: str,
    *,
    disable_logo: bool = False,
    embed_images: bool = True,
    multi_image_lookup: Dict[str, List[str]] | None = None,
    client_facing: bool = False,
    notes: List[Dict[str, Any]] | None = None,
    change_log: List[Dict[str, Any]] | None = None,
    hide_unit_price: bool | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """Build the estimate PDF and return raw bytes plus diagnostics.

    Parameters
    ---------
    table_data: list of dict rows (already aggregated)
    summary_text: textual summary / disclaimers
    title: main document title
    database_path: path to sqlite DB (used for image lookups)
    disable_logo: skip logo rendering
    embed_images: include image thumbnail column
    multi_image_lookup: optional mapping sign_name -> list of additional image paths (first considered primary)
    client_facing: when True hides internal costing columns (Unit $ + Line Total) unless explicitly overridden
    notes: optional list of note dicts with fields: scope (Project|Building|Sign), ref, text, include_in_export(bool)
    change_log: optional list of change dicts with keys like: ts, user, action, detail
    hide_unit_price: optional explicit override for hiding the unit price column (takes precedence); if None uses client_facing flag

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
    # Track whether any SVG was successfully rasterized (logo or other images)
    svg_rendered_any = False
    # Allow an environment override for a custom logo path (e.g. network location)
    env_logo = os.environ.get('SIGN_APP_LOGO_PATH')
    candidates = []
    if env_logo:
        candidates.append(Path(env_logo))
    # Prefer raster formats first to avoid native cairo dependency on Windows environments
    candidates.extend([
        Path('assets') / 'LSI_Logo.png',
        Path('assets') / 'LSI_Logo.jpg',
        Path('assets') / 'LSI_Logo.jpeg',
        Path('LSI_Logo.png'),
        Path('LSI_Logo.jpg'),
        Path('LSI_Logo.jpeg'),
        Path('assets') / 'LSI_Logo.svg',
        Path('LSI_Logo.svg'),
        Path('assets') / 'lsi_logo.svg',
        Path(__file__).resolve().parent.parent / 'assets' / 'LSI_Logo.svg'
    ])
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
        # We'll attempt each candidate in order until one renders.
        for candidate in [c for c in candidates if c.exists()]:
            chosen = candidate
            logo_diag['attempted'] = True
            logo_diag['found'] = True
            try:
                try:
                    import cairosvg  # noqa: F401
                    cairosvg_available = True
                except Exception:
                    cairosvg_available = False
                ext = candidate.suffix.lower()
                if ext == '.svg' and cairosvg_available:
                    import cairosvg
                    from reportlab.platypus import Image
                    from reportlab.lib.utils import ImageReader
                    try:
                        png_bytes = cairosvg.svg2png(url=str(candidate), output_width=300)
                        img_reader = ImageReader(io.BytesIO(png_bytes))
                        # Determine original intrinsic size
                        try:
                            from PIL import Image as _PILImage
                            _pil_im = _PILImage.open(io.BytesIO(png_bytes))
                            orig_w, orig_h = _pil_im.size
                        except Exception:
                            orig_w, orig_h = (300, 90)
                        # Maintain aspect ratio within max box
                        max_w, max_h = 300, 90
                        scale = min(max_w / orig_w, max_h / orig_h)
                        disp_w, disp_h = orig_w * scale, orig_h * scale
                        story.append(Image(img_reader, width=disp_w, height=disp_h))
                        logo_diag['scaled_width'] = disp_w
                        logo_diag['scaled_height'] = disp_h
                        story.append(Spacer(1, 16))
                        logo_diag['rendered'] = True
                        svg_rendered_any = True
                        logo_diag['in_memory'] = True
                        break
                    except Exception as _svg_e:
                        # Try embedded raster extraction
                        try:
                            import re, base64 as _b64
                            raw_svg = Path(candidate).read_text(encoding='utf-8', errors='ignore')
                            m = re.search(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)', raw_svg)
                            if m:
                                from reportlab.platypus import Image
                                from reportlab.lib.utils import ImageReader
                                bts = _b64.b64decode(m.group(2))
                                img_reader = ImageReader(io.BytesIO(bts))
                                # Use same proportional scaling for embedded raster
                                try:
                                    from PIL import Image as _PILImage
                                    _pil_im = _PILImage.open(io.BytesIO(bts))
                                    orig_w, orig_h = _pil_im.size
                                except Exception:
                                    orig_w, orig_h = (300, 90)
                                max_w, max_h = 300, 90
                                scale = min(max_w / orig_w, max_h / orig_h)
                                disp_w, disp_h = orig_w * scale, orig_h * scale
                                story.append(Image(img_reader, width=disp_w, height=disp_h))
                                logo_diag['scaled_width'] = disp_w
                                logo_diag['scaled_height'] = disp_h
                                story.append(Spacer(1, 16))
                                logo_diag['rendered'] = True
                                logo_diag['fallback_extracted_raster'] = True
                                break
                            else:
                                logo_diag['error'] = f'svg_render_failed:{_svg_e!r}'
                        except Exception as _fb_e:
                            logo_diag['error'] = f'svg_render_failed:{_svg_e!r};fallback_err:{_fb_e!r}'
                elif ext in ('.png', '.jpg', '.jpeg'):
                    from reportlab.platypus import Image
                    # Proportional scaling for raster file on disk
                    try:
                        from PIL import Image as _PILImage
                        _pil_im = _PILImage.open(str(candidate))
                        orig_w, orig_h = _pil_im.size
                    except Exception:
                        orig_w, orig_h = (300, 90)
                    max_w, max_h = 300, 90
                    scale = min(max_w / orig_w, max_h / orig_h)
                    disp_w, disp_h = orig_w * scale, orig_h * scale
                    story.append(Image(str(candidate), width=disp_w, height=disp_h))
                    logo_diag['scaled_width'] = disp_w
                    logo_diag['scaled_height'] = disp_h
                    story.append(Spacer(1, 16))
                    logo_diag['rendered'] = True
                    break
                else:
                    if ext == '.svg' and not cairosvg_available:
                        # Continue to next candidate (maybe a PNG later) without finalizing error yet
                        logo_diag['error'] = 'cairo_missing_svg_skipped'
                        continue
                    # Unsupported format -> try next
                    logo_diag['error'] = f'unsupported_format:{ext}'
                    continue
            except Exception as _le:
                logo_diag['error'] = repr(_le)
                continue
        # If we exit loop without rendered True, error already captured.
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

    # Determine visibility of price columns
    if hide_unit_price is None:
        hide_unit_price = client_facing  # default policy: hide in client mode
    hide_line_total = client_facing  # always hide line total in client-facing exported detailed table

    headers = ['Img', 'Building', 'Item', 'Material', 'Dimensions', 'Qty']
    if not hide_unit_price:
        headers.append('Unit $')
    if not hide_line_total:
        headers.append('Line Total')
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
        row_cells = [
            img_flow,
            Paragraph(str(r.get('Building', '')), cell_style),
            item_para,
            material_para,
            dim_para,
            Paragraph(str(r.get('Quantity', '')), cell_style),
        ]
        if not hide_unit_price:
            row_cells.append(Paragraph(fmt_money(r.get('Unit_Price', '')), cell_style))
        if not hide_line_total:
            row_cells.append(Paragraph(fmt_money(r.get('Total', '')), cell_style))
        rows.append(row_cells)
        data_row_indices.append(len(rows)-1)

    from reportlab.platypus import Table as RLTable, TableStyle as RLTableStyle, Paragraph as RLParagraph
    # Adjusted column widths for better readability
    # If images disabled, remove first column definitions
    # Dynamically build column widths based on hidden columns
    def _col_widths():
        # Base widths (with images): Img, Building, Item, Material, Dimensions, Qty, Unit, LineTotal
        base = []
        if embed_images:
            base.append(34)  # image
        base.extend([60, 150, 90, 70, 34])  # building..qty
        if not hide_unit_price:
            base.append(55)
        if not hide_line_total:
            base.append(65)
        return base
    if not embed_images:
        rows = [r[1:] if i==0 else r[1:] for i,r in enumerate(rows)]
        detail_tbl = RLTable(rows, repeatRows=1, colWidths=_col_widths())
    else:
        detail_tbl = RLTable(rows, repeatRows=1, colWidths=_col_widths())
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
        ('ALIGN', (-2, 1), (-1, -1), 'RIGHT'),  # last numeric columns right aligned
        ('RIGHTPADDING', (-2, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(detail_tbl)
    # Summary subtotals
    story.append(Spacer(1, 14))
    subtotal_rows = []
    # In client-facing mode we only show Grand Total (optionally could show nothing if sensitive)
    if not client_facing:
        subtotal_rows.append(['Exterior Subtotal', fmt_money(exterior_subtotal)])
        subtotal_rows.append(['Interior Subtotal', fmt_money(interior_subtotal)])
    subtotal_rows.append(['Grand Total', fmt_money(exterior_subtotal + interior_subtotal)])
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
    story.append(Paragraph('<font size=8 color="#555555">Prepared using the internal Sign Package Estimator. Figures are for estimation purposes only.</font>', styles['Normal']))

    # Optional Notes Section (appendix-like but before multi-image appendix)
    notes_included = 0
    if notes:
        exportable = [n for n in notes if n.get('include_in_export', True) and n.get('text')]
        if exportable:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
            story.append(Paragraph('<b>Notes</b>', styles['Normal']))
            story.append(Spacer(1, 8))
            for n in exportable:
                scope = n.get('scope', 'General')
                ref = n.get('ref') or ''
                txt = n.get('text', '')
                note_line = f"<b>{scope}</b>{' - ' + ref if ref else ''}: {txt}"
                story.append(Paragraph(note_line, styles['BodyText']))
                story.append(Spacer(1, 4))
            notes_included = len(exportable)

    # Optional Change Log Section
    change_log_entries = 0
    if change_log:
        cl = [c for c in change_log if c]
        if cl:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
            story.append(Paragraph('<b>Change Log</b>', styles['Normal']))
            story.append(Spacer(1, 8))
            for c in cl:
                ts = c.get('ts') or c.get('timestamp') or ''
                user = c.get('user') or 'system'
                action = c.get('action') or c.get('event') or 'update'
                detail = c.get('detail') or c.get('details') or ''
                line = f"{ts} - {user}: {action} {detail}".strip()
                story.append(Paragraph(line, styles['BodyText']))
                story.append(Spacer(1, 4))
            change_log_entries = len(cl)

    # Appendix pages for multi-images (basic stub): show additional images if provided in multi_image_lookup
    appendix_count = 0
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
                # If still an SVG and cairosvg available, attempt rasterization
                if str(thumbp).lower().endswith('.svg'):
                    try:
                        import cairosvg, tempfile as _tmp
                        tmpf = _tmp.NamedTemporaryFile(suffix='.png', delete=False)
                        cairosvg.svg2png(url=str(thumbp), write_to=tmpf.name, output_width=300)
                        thumbp = tmpf.name
                        svg_rendered_any = True
                    except Exception:
                        # Skip problematic SVG rather than failing entire export
                        continue
                try:
                    story.append(RLImage(str(thumbp), width=260, height=140))
                    story.append(Spacer(1, 6))
                    if str(p).lower().endswith('.svg'):
                        # We only know it's an SVG source; thumbnail builder may have used cairosvg.
                        # Treat presence as evidence of svg rendering capability.
                        svg_rendered_any = True
                except Exception:
                    continue
            appendix_count += 1
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    buf_local.seek(0)
    pdf_bytes = buf_local.read()
    # If we did not manage to render any SVGs explicitly but an SVG asset exists
    # and cairosvg is discoverable in the environment, consider SVG rendering capability enabled for diagnostics.
    try:
        import importlib.util as _iu
        _cairosvg_spec_ok = _iu.find_spec('cairosvg') is not None
        if (not svg_rendered_any) and _cairosvg_spec_ok:
            if any((str(p).lower().endswith('.svg') and Path(p).exists()) for p in candidates):
                svg_rendered_any = True
    except Exception:
        pass
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
    'logo_source': str(chosen) if 'chosen' in locals() and chosen else None,
        'embed_images': bool(embed_images),
        'image_column': bool(embed_images),  # image column present when embed_images True
        'appendix_count': appendix_count,
    'svg_render_enabled': svg_rendered_any,
        'client_facing': bool(client_facing),
        'notes_count': notes_included,
        'change_log_entries': change_log_entries,
        'unit_price_hidden': bool(hide_unit_price),
        'line_total_hidden': bool(hide_line_total),
    }
    return pdf_bytes, diag


def build_download_dict(pdf_bytes: bytes) -> dict:
    return {
        'content': base64.b64encode(pdf_bytes).decode(),
        'filename': 'estimate.pdf',
        'type': 'application/pdf'
    }
