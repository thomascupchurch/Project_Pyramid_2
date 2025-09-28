"""Shared estimation logic to reduce duplication in Dash callbacks.

Functions here avoid Dash imports and focus purely on data/SQLite operations.
"""
from typing import List, Dict, Any, Optional, Tuple, Sequence
import sqlite3
from pathlib import Path
import pandas as pd
from .calculations import compute_unit_price, compute_install_cost

DatabasePath = str | Path

def compute_custom_estimate(
    db_path: DatabasePath,
    project_id: int,
    building_ids: Optional[Sequence[int]],
    price_mode: str,
    install_mode: str,
    inst_percent: float,
    inst_per_sign: float,
    inst_per_area: float,
    inst_hours: float,
    inst_hourly: float,
    auto_enabled: bool,
    return_meta: bool = False
) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Compute estimate rows (list of dict) for a project (optionally specific buildings) using extended pricing logic.

    Args:
        building_ids: Optional iterable of building ids to restrict. If None -> all buildings in project.
        return_meta: If True, also returns a meta dict with intermediate metrics for UI summaries.

    Rows have keys: Building, Item, Material, Dimensions, Quantity, Unit_Price, Total.
    Appends Installation & Sales Tax rows when applicable (Building='ALL').
    """
    def _f(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0
    conn = sqlite3.connect(db_path)
    proj_df = pd.read_sql_query('SELECT * FROM projects WHERE id=?', conn, params=(project_id,))
    if proj_df.empty:
        conn.close()
        return []
    project = proj_df.iloc[0]
    buildings = pd.read_sql_query('SELECT * FROM buildings WHERE project_id=?', conn, params=(project_id,))
    estimate_data: List[Dict[str, Any]] = []
    grand_subtotal = 0.0
    total_sign_count = 0
    total_area = 0.0
    auto_install_amount_per_sign = 0.0
    auto_install_hours = 0.0
    selected_ids = set(building_ids) if building_ids else None
    for _, b in buildings.iterrows():
        if selected_ids and b['id'] not in selected_ids:
            continue
        b_sub = 0.0
        # Signs
        signs = pd.read_sql_query('''SELECT st.name, st.unit_price, st.material, st.width, st.height, st.price_per_sq_ft, st.per_sign_install_rate, st.install_time_hours, bs.quantity
                                      FROM building_signs bs JOIN sign_types st ON bs.sign_type_id=st.id WHERE bs.building_id=?''', conn, params=(b['id'],))
        for _, s in signs.iterrows():
            qty = _f(s['quantity'])
            width=_f(s['width']); height=_f(s['height'])
            area = width*height if width and height else 0
            total_sign_count += qty
            total_area += area*qty
            ps_install=_f(s.get('per_sign_install_rate'))
            if ps_install>0:
                auto_install_amount_per_sign += ps_install * qty
            inst_time=_f(s.get('install_time_hours'))
            if inst_time>0:
                auto_install_hours += inst_time * qty
            unit_price = compute_unit_price(s.to_dict(), price_mode)
            line_total = unit_price*qty
            b_sub += line_total
            estimate_data.append({'Building': b['name'], 'Item': s['name'], 'Material': s['material'], 'Dimensions': f"{width} x {height}" if width and height else '', 'Quantity': qty, 'Unit_Price': unit_price, 'Total': line_total})
        # Groups
        groups = pd.read_sql_query('''SELECT sg.id, sg.name, bsg.quantity FROM building_sign_groups bsg JOIN sign_groups sg ON bsg.group_id=sg.id WHERE bsg.building_id=?''', conn, params=(b['id'],))
        for _, g in groups.iterrows():
            group_members = pd.read_sql_query('''SELECT st.name, st.unit_price, st.width, st.height, st.price_per_sq_ft, st.per_sign_install_rate, st.install_time_hours, st.material_multiplier, sgm.quantity
                                                  FROM sign_group_members sgm JOIN sign_types st ON sgm.sign_type_id=st.id WHERE sgm.group_id=?''', conn, params=(g['id'],))
            group_cost_unit = 0.0
            for _, m in group_members.iterrows():
                m_qty = _f(m['quantity'])
                width=_f(m['width']); height=_f(m['height'])
                area=width*height if width and height else 0
                total_sign_count += m_qty * g['quantity']
                total_area += area * m_qty * g['quantity']
                ps_install=_f(m.get('per_sign_install_rate'))
                if ps_install>0:
                    auto_install_amount_per_sign += ps_install * m_qty * g['quantity']
                inst_time=_f(m.get('install_time_hours'))
                if inst_time>0:
                    auto_install_hours += inst_time * m_qty * g['quantity']
                m_unit = compute_unit_price(m.to_dict(), price_mode)
                group_cost_unit += m_unit * m_qty
            unit_price = group_cost_unit
            line_total = unit_price * g['quantity']
            b_sub += line_total
            estimate_data.append({'Building': b['name'], 'Item': f"Group: {g['name']}", 'Material': 'Various', 'Dimensions': '', 'Quantity': g['quantity'], 'Unit_Price': unit_price, 'Total': line_total})
        grand_subtotal += b_sub
    install_cost = compute_install_cost(
        install_mode, grand_subtotal, total_sign_count, total_area,
        inst_percent, inst_per_sign, inst_per_area, inst_hours, inst_hourly,
        auto_enabled, auto_install_amount_per_sign, auto_install_hours
    )
    if install_mode != 'none' and install_cost>0:
        estimate_data.append({'Building':'ALL','Item':'Installation','Material':'','Dimensions':'','Quantity':1,'Unit_Price':install_cost,'Total':install_cost})
    if bool(project.get('include_sales_tax')) and project.get('sales_tax_rate'):
        taxable_total = sum(r['Total'] for r in estimate_data if r['Building']!='ALL' or r['Item']=='Installation')
        tax_cost = taxable_total * float(project['sales_tax_rate'])
        estimate_data.append({'Building':'ALL','Item':'Sales Tax','Material':'','Dimensions':'','Quantity':1,'Unit_Price':tax_cost,'Total':tax_cost})
    conn.close()
    if return_meta:
        meta = {
            'grand_subtotal': grand_subtotal,
            'total_sign_count': total_sign_count,
            'total_area': total_area,
            'auto_install_amount_per_sign': auto_install_amount_per_sign,
            'auto_install_hours': auto_install_hours,
            'install_cost': install_cost,
            'project_sales_tax_rate': float(project.get('sales_tax_rate') or 0),
            'include_sales_tax': bool(project.get('include_sales_tax'))
        }
        return estimate_data, meta
    return estimate_data
