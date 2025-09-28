"""
Sign Estimation Application
A modern Python web application for sign manufacturing cost estimation and project management.
"""

import os
import sys
import socket
import dash
from dash import html, dcc, Input, Output, State, callback_context, dash_table
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import dash_cytoscape as cyto
import pandas as pd
import sqlite3
from datetime import datetime
import base64
import io
import json
from pathlib import Path
from dash.exceptions import PreventUpdate

# Add utils to path
sys.path.append(str(Path(__file__).parent / "utils"))

# Import custom utilities (prefer explicit utils.* path)
try:
    from utils.database import DatabaseManager  # type: ignore
    from utils.calculations import CostCalculator, compute_unit_price, compute_install_cost  # type: ignore
    from utils.onedrive import OneDriveManager  # type: ignore
except ImportError as e:
    print(f"Warning: Could not import utilities via utils.* path: {e}; attempting direct import fallback.")
    try:
        from database import DatabaseManager  # type: ignore
        from calculations import CostCalculator, compute_unit_price, compute_install_cost  # type: ignore
        from onedrive import OneDriveManager  # type: ignore
    except Exception as ee:
        print(f"Fallback import also failed: {ee}. Using minimal placeholder classes.")
        class DatabaseManager:  # minimal fallback
            def __init__(self, db_path): self.db_path = db_path
            def init_database(self): pass
            def get_project_estimate(self, project_id): return []
        class CostCalculator:  # minimal fallback
            def __init__(self, db_path): pass
        def compute_unit_price(row_dict, price_mode):
            try: return float(row_dict.get('unit_price') or 0)
            except Exception: return 0.0
        def compute_install_cost(*args, **kwargs): return 0.0
        class OneDriveManager:  # minimal fallback
            def __init__(self, local_path): pass

# Initialize Dash app
print("[startup] Import phase complete. Initializing Dash app...", flush=True)
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
app.title = "Sign Estimation Tool"

from config import DATABASE_PATH, APP_HOST, APP_PORT, DASH_DEBUG, ensure_backup_dir, AUTO_BACKUP_INTERVAL_SEC, BACKUP_DIR, ONEDRIVE_SYNC_DIR, ONEDRIVE_AUTOSYNC_SEC
DATABASE_PATH = os.getenv("SIGN_APP_DB", DATABASE_PATH)
print(f"[startup] Database path resolved to: {DATABASE_PATH}", flush=True)
db_manager = None
try:
    print("[startup] Creating DatabaseManager...", flush=True)
    db_manager = DatabaseManager(DATABASE_PATH)
    print("[startup] DatabaseManager created.", flush=True)
except Exception as e:
    print(f"[startup][error] Failed to create DatabaseManager: {e}", flush=True)
    raise

print("[startup] Creating CostCalculator...", flush=True)
cost_calculator = CostCalculator(DATABASE_PATH)
print("[startup] CostCalculator ready.", flush=True)
print("[startup] Creating OneDriveManager...", flush=True)
onedrive_manager = OneDriveManager(Path.cwd())
print("[startup] OneDriveManager ready.", flush=True)

# Optional: configure OneDrive target path if env var provided
if ONEDRIVE_SYNC_DIR:
    try:
        onedrive_manager.setup_onedrive_path(ONEDRIVE_SYNC_DIR)
        print(f"[startup] OneDrive sync dir set to {ONEDRIVE_SYNC_DIR}")
    except Exception as e:
        print(f"[startup][warn] Failed to set OneDrive path: {e}")

print("[startup] Ensuring database schema...", flush=True)
try:
    db_manager.init_database()
    print("[startup] Schema ensured.", flush=True)
except Exception as e:
    print(f"[startup][error] init_database failed: {e}", flush=True)
    raise

# --- Lightweight runtime migration for extended columns --- #
def ensure_extended_schema():
    """Add newly used columns to tables if they do not yet exist.

    Safe to run at startup; uses PRAGMA table_info inspection then ALTER TABLE for any missing columns.
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        # sign_types extended columns
        cur.execute("PRAGMA table_info('sign_types')")
        existing_cols = {r[1] for r in cur.fetchall()}
        alter_statements = []
        if 'material_alt' not in existing_cols:
            alter_statements.append("ALTER TABLE sign_types ADD COLUMN material_alt TEXT")
        if 'material_multiplier' not in existing_cols:
            alter_statements.append("ALTER TABLE sign_types ADD COLUMN material_multiplier REAL DEFAULT 0")
        if 'install_type' not in existing_cols:
            alter_statements.append("ALTER TABLE sign_types ADD COLUMN install_type TEXT")
        if 'install_time_hours' not in existing_cols:
            alter_statements.append("ALTER TABLE sign_types ADD COLUMN install_time_hours REAL DEFAULT 0")
        if 'per_sign_install_rate' not in existing_cols:
            alter_statements.append("ALTER TABLE sign_types ADD COLUMN per_sign_install_rate REAL DEFAULT 0")
        # building_signs optional custom_price
        cur.execute("PRAGMA table_info('building_signs')")
        bs_cols = {r[1] for r in cur.fetchall()}
        if 'custom_price' not in bs_cols:
            alter_statements.append("ALTER TABLE building_signs ADD COLUMN custom_price REAL")
        for stmt in alter_statements:
            try:
                cur.execute(stmt)
                print(f"[migrate] Executed: {stmt}")
            except Exception as ie:
                # Ignore if race or platform restriction
                print(f"[migrate][warn] {ie} while executing {stmt}")
        conn.commit(); conn.close()
    except Exception as e:
        print(f"[migrate][error] {e}")

ensure_extended_schema()

# Background autosync (database only) if enabled
if ONEDRIVE_SYNC_DIR and ONEDRIVE_AUTOSYNC_SEC > 0:
    import threading, time
    def _autosync_loop():
        while True:
            try:
                ok, msg = onedrive_manager.sync_database()
                if ok:
                    print(f"[autosync] {msg}")
            except Exception as e:
                print(f"[autosync][error] {e}")
            time.sleep(ONEDRIVE_AUTOSYNC_SEC)
    threading.Thread(target=_autosync_loop, daemon=True).start()

# ------------------ Initial Sign Types Auto-Load ------------------ #
def _sign_types_count():
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM sign_types")
    count = cur.fetchone()[0]
    conn.close()
    return count

def _load_sign_types_from_df(df: pd.DataFrame) -> int:
    """Insert/merge sign types from DataFrame. Returns number inserted/updated."""
    required_cols_map = {
        'name': ['name','sign_name','Sign Name'],
        'description': ['description','desc','Description'],
        'unit_price': ['unit_price','price','Price','Unit Price'],
        'material': ['material','Material'],
        'width': ['width','Width','W'],
        'height': ['height','Height','H'],
        'price_per_sq_ft': ['price_per_sq_ft','Price/Sq Ft','price_sqft']
    }
    # Normalize columns
    norm_df = pd.DataFrame()
    for target, aliases in required_cols_map.items():
        for alias in aliases:
            if alias in df.columns:
                norm_df[target] = df[alias]
                break
        if target not in norm_df.columns:
            # Fill missing numeric with 0, text with ''
            if target in ('unit_price','width','height','price_per_sq_ft'):
                norm_df[target] = 0
            else:
                norm_df[target] = ''
    # Coerce numeric-like strings
    def _coerce_numeric(val):
        if pd.isna(val):
            return 0
        if isinstance(val,(int,float)):
            return val
        if isinstance(val,str):
            txt = val.strip().replace('$','').replace(',','')
            try:
                return float(txt) if txt else 0
            except:
                return 0
        try:
            return float(val)
        except:
            return 0
    for _c in ['unit_price','width','height','price_per_sq_ft']:
        norm_df[_c] = norm_df[_c].apply(_coerce_numeric)
    # Compute price_per_sq_ft if absent but width/height/unit_price present
    calc_mask = (norm_df['price_per_sq_ft']==0) & (norm_df['width']>0) & (norm_df['height']>0) & (norm_df['unit_price']>0)
    norm_df.loc[calc_mask,'price_per_sq_ft'] = norm_df.loc[calc_mask].apply(lambda r: (r['unit_price'] / (r['width']*r['height'])) if r['width']*r['height'] else 0, axis=1)
    # Drop duplicates (case-insensitive name) keeping first
    norm_df['__name_key'] = norm_df['name'].astype(str).str.strip().str.lower()
    norm_df = norm_df.drop_duplicates('__name_key')
    # Upsert rows
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    inserted = 0
    for row in norm_df.itertuples():
        name = str(row.name).strip()
        if not name:
            continue
        cur.execute('''
            INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
              description=excluded.description,
              unit_price=excluded.unit_price,
              material=excluded.material,
              price_per_sq_ft=excluded.price_per_sq_ft,
              width=excluded.width,
              height=excluded.height
        ''', (
            name,
            str(row.description or ''),
            float(row.unit_price or 0),
            str(row.material or ''),
            float(row.price_per_sq_ft or 0),
            float(row.width or 0),
            float(row.height or 0)
        ))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted

def auto_load_initial_sign_types():
    if _sign_types_count() > 0:
        return 0, None
    csv_path_env = os.getenv('SIGN_APP_INITIAL_CSV')
    candidates = []
    if csv_path_env:
        candidates.append(Path(csv_path_env))
    candidates.append(Path(__file__).parent / 'initial_sign_types.csv')
    for candidate in candidates:
        if candidate.exists():
            try:
                df = pd.read_csv(candidate)
                count = _load_sign_types_from_df(df)
                print(f"Loaded {count} sign types from {candidate}")
                return count, str(candidate)
            except Exception as e:
                print(f"Failed loading sign types from {candidate}: {e}")
                return 0, None
    return 0, None

_loaded_count, _loaded_source = auto_load_initial_sign_types()
if _loaded_count:
    print(f"Auto-initialized sign_types with {_loaded_count} rows from {_loaded_source}")

# Attempt secondary import from Book2.csv if dataset appears empty/minimal
def _attempt_import_book2():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sign_types")
        count = cur.fetchone()[0]
        conn.close()
        if count > 5:
            return
        csv_path = Path('Book2.csv')
        if not csv_path.exists():
            return
        print('[startup] Importing Book2.csv into sign_types...')
        import pandas as pd
        df = pd.read_csv(csv_path)
        # Normalize columns -> best effort mapping
        def parse_cost(val):
            if isinstance(val, str):
                return float(val.replace('$','').replace(',','') or 0) if any(ch.isdigit() for ch in val) else 0.0
            try: return float(val or 0)
            except: return 0.0
        records = []
        for r in df.to_dict('records'):
            name = str(r.get('Code') or r.get('Desc') or r.get('full_name') or '').strip()
            if not name:
                continue
            width = r.get('Width') or 0
            height = r.get('Height') or 0
            material = r.get('Material2') or r.get('Material') or ''
            # Derive price_per_sq_ft from 'Unnamed: 24' if numeric else material_multiplier
            ppsf_raw = r.get('Unnamed: 24') or r.get('material_multiplier') or 0
            try: ppsf = float(str(ppsf_raw).replace('$','').replace(',','')) if ppsf_raw not in (None,'') else 0.0
            except: ppsf = 0.0
            # Unit price attempt: item_cost if present else (width*height*ppsf)
            unit_price = parse_cost(r.get('item_cost'))
            try:
                if unit_price == 0 and width and height and ppsf:
                    unit_price = float(width) * float(height) * float(ppsf)
            except: pass
            records.append((name[:120], str(r.get('Desc') or r.get('full_name') or '')[:255], unit_price, str(material)[:120], ppsf, float(width or 0), float(height or 0)))
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.executemany('''
            INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET description=excluded.description,
                unit_price=excluded.unit_price, material=excluded.material,
                price_per_sq_ft=excluded.price_per_sq_ft, width=excluded.width, height=excluded.height
        ''', records)
        conn.commit()
        conn.close()
        print(f'[startup] Imported/merged {len(records)} sign types from Book2.csv')
    except Exception as e:
        print(f'[startup][warn] Book2.csv import skipped: {e}')

_attempt_import_book2()

# (Removed duplicate inline schema function; schema managed by utils/database.py)

def load_csv_data(file_path):
    """Load initial data from CSV file."""
    try:
        df = pd.read_csv(file_path)
        conn = sqlite3.connect(DATABASE_PATH)
        
        # Process CSV data and populate sign_types table
        for _, row in df.iterrows():
            # Adjust column names based on your CSV structure
            # This is a placeholder - will need to be customized based on actual CSV
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO sign_types (name, description, unit_price, material)
                VALUES (?, ?, ?, ?)
            ''', (row.get('name', ''), row.get('description', ''), 
                  row.get('price', 0.0), row.get('material', '')))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return False

def get_project_tree_data():
    """Generate tree visualization data including running cost totals.

    Building totals: sum of (sign/group member computed unit prices * quantities).
    Project totals: sum of building totals.
    Sign pricing heuristic: try area * price_per_sq_ft (or material_multiplier) else unit_price.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
    nodes = []

    # Helper to compute unit price using existing logic (reuse per_area mode to allow area attempt)
    def _price(row_dict):
        try:
            return compute_unit_price(row_dict, 'per_area')
        except Exception:
            # Fallback minimal
            return float(row_dict.get('unit_price') or 0)

    for _, project in projects_df.iterrows():
        project_node_index = len(nodes)
        nodes.append({
            'id': f"project_{project['id']}",
            'label': project['name'],
            'type': 'project',
            'level': 0
        })
        project_total = 0.0

        buildings_df = pd.read_sql_query("SELECT * FROM buildings WHERE project_id = ?", conn, params=(project['id'],))
        for _, building in buildings_df.iterrows():
            building_node_index = len(nodes)
            nodes.append({
                'id': f"building_{building['id']}",
                'label': building['name'],
                'type': 'building',
                'level': 1,
                'parent': f"project_{project['id']}"
            })
            building_total = 0.0

            # Individual signs (include fields for pricing)
            signs_df = pd.read_sql_query('''
                SELECT st.name, st.unit_price, st.width, st.height, st.price_per_sq_ft, st.material_multiplier, bs.quantity
                FROM building_signs bs
                JOIN sign_types st ON bs.sign_type_id = st.id
                WHERE bs.building_id = ?
            ''', conn, params=(building['id'],))
            for _, sign in signs_df.iterrows():
                unit_price = _price(sign.to_dict())
                line_total = unit_price * (sign['quantity'] or 0)
                building_total += line_total
                nodes.append({
                    'id': f"sign_{building['id']}_{sign['name']}",
                    'label': f"{sign['name']} ({sign['quantity']})",
                    'type': 'sign',
                    'level': 2,
                    'parent': f"building_{building['id']}"
                })

            # Sign groups attached to building
            groups_df = pd.read_sql_query('''
                SELECT bsg.id, bsg.group_id, bsg.quantity, sg.name as group_name
                FROM building_sign_groups bsg
                JOIN sign_groups sg ON bsg.group_id = sg.id
                WHERE bsg.building_id = ?
            ''', conn, params=(building['id'],))
            for _, grp in groups_df.iterrows():
                # Aggregate cost of group members
                members_df = pd.read_sql_query('''
                    SELECT st.unit_price, st.width, st.height, st.price_per_sq_ft, st.material_multiplier, sgm.quantity
                    FROM sign_group_members sgm
                    JOIN sign_types st ON sgm.sign_type_id = st.id
                    WHERE sgm.group_id = ?
                ''', conn, params=(grp['group_id'],))
                group_unit_cost = 0.0
                for _, mem in members_df.iterrows():
                    g_unit = _price(mem.to_dict())
                    group_unit_cost += g_unit * (mem['quantity'] or 0)
                building_total += group_unit_cost * (grp['quantity'] or 0)
                # Represent group as a sign-level node
                nodes.append({
                    'id': f"sign_{building['id']}_group_{grp['group_id']}",
                    'label': f"Group: {grp['group_name']} ({grp['quantity']})",
                    'type': 'sign',
                    'level': 2,
                    'parent': f"building_{building['id']}"
                })

            project_total += building_total
            # Update building node label with total
            # Format building total with comma thousands and 2 decimals
            nodes[building_node_index]['label'] = f"{building['name']} (${'{:,.2f}'.format(building_total)})"

        # Update project node label with total
    # Format project total similarly
    nodes[project_node_index]['label'] = f"{project['name']} (${'{:,.2f}'.format(project_total)})"

    conn.close()
    return nodes

def create_tree_visualization():
    """Create Plotly tree visualization."""
    nodes = get_project_tree_data()
    if not nodes:
        return go.Figure()
    # Group by level preserving order
    levels = {}
    for n in nodes:
        levels.setdefault(n['level'], []).append(n)
    # Compute positions
    x_gap = 260
    y_gap = 46
    pos = {}
    for level, lvl_nodes in levels.items():
        for i, n in enumerate(lvl_nodes):
            pos[n['id']] = (level * x_gap, i * y_gap)
    # Build edge coordinate arrays (ultra-thin lines)
    edge_x = []
    edge_y = []
    for n in nodes:
        parent = n.get('parent')
        if parent and parent in pos:
            x0, y0 = pos[parent]; x1, y1 = pos[n['id']]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]
    fig = go.Figure()
    if edge_x:
        fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(color='#cccccc', width=0.5), hoverinfo='none', showlegend=False))
    color_map = {'project': '#1f77b4', 'building': '#ff7f0e', 'sign': '#2ca02c'}
    for lvl, lvl_nodes in levels.items():
        fig.add_trace(go.Scatter(
            x=[pos[n['id']][0] for n in lvl_nodes],
            y=[pos[n['id']][1] for n in lvl_nodes],
            mode='markers+text',
            marker=dict(size=15, color=[color_map.get(n['type'], '#4a90e2') for n in lvl_nodes]),
            text=[n['label'] for n in lvl_nodes],
            textposition='middle right',
            hoverinfo='text',
            name=f'Level {lvl}'
        ))
    fig.update_layout(
        title='Project Tree Visualization',
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=600,
        margin=dict(l=10, r=10, t=40, b=10),
        showlegend=False
    )
    return fig

def safe_tree_figure():
    """Wrapper around create_tree_visualization that never raises; returns an error-annotated figure on failure."""
    try:
        return create_tree_visualization()
    except Exception as e:
        print(f"[tree][error] {e}", flush=True)
        err_fig = go.Figure()
        err_fig.add_annotation(text=f"Tree error: {e}", showarrow=False, x=0.5, y=0.5, xref='paper', yref='paper')
        err_fig.update_layout(height=600, margin=dict(l=10, r=10, t=40, b=10))
        return err_fig

# Database already initialized above

# App layout
app.layout = dbc.Container([
    # Header with logo
    dbc.Row([
        dbc.Col([
            html.Div([
                html.Img(src="/assets/LSI_Logo.svg", className="app-logo me-3"),
                html.H1("Sign Estimation Tool", className="d-inline-block align-middle mb-0")
            ], className="d-flex align-items-center py-3")
        ])
    ]),
    
    # Navigation tabs
    dbc.Row([
        dbc.Col([
            dbc.Tabs([
                dbc.Tab(label="Projects", tab_id="projects-tab"),
                dbc.Tab(label="Sign Types", tab_id="signs-tab"),
                dbc.Tab(label="Sign Groups", tab_id="groups-tab"),
                dbc.Tab(label="Building View", tab_id="building-tab"),
                dbc.Tab(label="Estimates", tab_id="estimates-tab"),
                dbc.Tab(label="Import Data", tab_id="import-tab")
            ], id="main-tabs", active_tab="projects-tab")
        ])
    ], className="mb-4"),
    
    # Main content area
    dcc.Store(id='app-state', data={}),
    dcc.Store(id='last-error-message'),
    # Global toast for surfaced errors
    html.Div([
        dbc.Toast(id='app-error-toast', header='Notice', is_open=False, dismissable=True, duration=4000, icon='danger', style={'position':'fixed','top':10,'right':10,'zIndex':1080})
    ]),
    html.Div(id="tab-content", className='flex-grow-1'),
    html.Footer(
        className='app-footer text-center text-muted py-3 small mt-auto',
        children=[
            html.Span("© 2025 LSI Graphics, LLC")
        ]
    )
    
], fluid=True, className='d-flex flex-column min-vh-100')

@app.callback(
    Output("tab-content", "children"),
    Input("main-tabs", "active_tab")
)
def render_tab_content(active_tab):
    if active_tab == "projects-tab":
        return render_projects_tab()
    elif active_tab == "signs-tab":
        return render_signs_tab()
    elif active_tab == "groups-tab":
        return render_groups_tab()
    elif active_tab == "building-tab":
        return render_building_tab()
    elif active_tab == "estimates-tab":
        return render_estimates_tab()
    elif active_tab == "import-tab":
        return render_import_tab()
    
    return html.Div("Select a tab")

def render_projects_tab():
    """Render the projects management tab."""
    # Load current projects for initial render
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query("SELECT id, name, created_date FROM projects ORDER BY id DESC", conn)
    conn.close()
    if df.empty:
        project_list_component = html.Div("No projects yet.")
        project_options = []
    else:
        rows = [html.Li(f"{r.name} (ID {r.id}) - {r.created_date}") for r in df.itertuples()]
        project_list_component = html.Ul(rows, className="mb-0")
        project_options = [{"label": r.name, "value": r.id} for r in df.itertuples()]
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Project Tree Visualization")),
                dbc.CardBody([
                    dbc.RadioItems(
                        id='tree-view-mode',
                        options=[{'label':'Static','value':'static'},{'label':'Interactive','value':'cyto'}],
                        value='static', inline=True, className='mb-2'
                    ),
                    # Tree figure populated asynchronously by init callback; avoids layout-time exceptions blocking tab
                    html.Div(id='project-tree-wrapper', children=dcc.Graph(id='project-tree'))
                ])
            ]),
            dbc.Card([
                dbc.CardHeader(html.H4("Building & Sign Assignment")),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Select Project"),
                            dcc.Dropdown(id='assign-project-dropdown', placeholder='Choose project', options=project_options)
                        ], md=4),
                        dbc.Col([
                            dbc.Label("Create Building"),
                            dbc.Input(id='new-building-name', placeholder='Building name'),
                            dbc.Textarea(id='new-building-desc', placeholder='Description', style={"height": "60px"}),
                            dbc.Button("Add Building", id='add-building-btn', color='secondary', className='mt-2 w-100')
                        ], md=4),
                        dbc.Col([
                            dbc.Label("Select Building"),
                            dcc.Dropdown(id='building-dropdown', placeholder='Choose building'),
                            dbc.Input(id='rename-building-input', placeholder='Rename building', className='mt-2'),
                            dbc.Button('Rename', id='rename-building-btn', color='warning', size='sm', className='mt-1'),
                            html.Small(id='building-action-feedback', className='text-muted')
                        ], md=4)
                    ], className='mb-3 g-3'),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Add Sign Type"),
                            dcc.Dropdown(id='sign-type-dropdown', placeholder='Select sign type')
                        ], md=5),
                        dbc.Col([
                            dbc.Label("Quantity"),
                            dbc.Input(id='sign-qty-input', type='number', min=1, value=1)
                        ], md=3),
                        dbc.Col([
                            dbc.Button("Add / Update Sign", id='add-sign-to-building-btn', color='success', className='mt-4 w-100')
                        ], md=4)
                    ], className='mb-3'),
                    dash_table.DataTable(
                        id='building-signs-table',
                        columns=[
                            {"name": "Sign", "id": "sign_name", "editable": False},
                            {"name": "Quantity", "id": "quantity", "type": "numeric", "editable": True},
                            {"name": "Unit Price", "id": "unit_price", "type": "numeric", "editable": False},
                            {"name": "Total", "id": "total", "type": "numeric", "editable": False}
                        ],
                        data=[],
                        editable=True,
                        row_deletable=False,
                        style_table={"overflowX": "auto"},
                        page_size=10
                    ),
                    dbc.Button("Save Quantity Changes", id='save-building-signs-btn', color='primary', className='mt-2'),
                    html.Div(id='save-building-signs-feedback', className='mt-2'),
                    html.Hr(className='my-3'),
                    html.H5("Sign Groups for Building"),
                    dbc.Row([
                        dbc.Col(dbc.Checklist(id='project-groups-show-all', options=[{'label':'Show All Groups','value':'all'}], value=[], switch=True), width='auto')
                    ], className='mb-2 g-2'),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Add Group"),
                            dcc.Dropdown(id='project-group-dropdown', placeholder='Select sign group')
                        ], md=5),
                        dbc.Col([
                            dbc.Label("Quantity"),
                            dbc.Input(id='group-qty-input', type='number', min=1, value=1)
                        ], md=3),
                        dbc.Col([
                            dbc.Button("Add / Update Group", id='add-group-to-building-btn', color='success', className='mt-4 w-100')
                        ], md=4)
                    ], className='mb-3 g-3'),
                    dash_table.DataTable(
                        id='project-building-groups-table',
                        columns=[
                            {"name": "Group", "id": "group_name", "editable": False},
                            {"name": "Quantity", "id": "quantity", "type": "numeric", "editable": True}
                        ],
                        data=[],
                        editable=True,
                        row_deletable=False,
                        style_table={"overflowX":"auto"},
                        page_size=8
                    ),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Remove Group"),
                            dcc.Dropdown(id='assigned-group-delete-dropdown', placeholder='Assigned group')
                        ], md=8),
                        dbc.Col([
                            dbc.Button("Remove", id='remove-group-from-building-btn', color='danger', className='mt-4 w-100')
                        ], md=4)
                    ], className='mt-3 g-3'),
                    dbc.Button("Save Group Quantities", id='save-building-groups-btn', color='secondary', className='mt-2'),
                    html.Div(id='building-groups-feedback', className='mt-2')
                ])
            ], className='mt-3')
        ], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Project Management")),
                dbc.CardBody([
                    dbc.Form([
                        dbc.Row([
                            dbc.Label("Edit Existing", width=4),
                            dbc.Col(dcc.Dropdown(id='project-edit-dropdown', placeholder='Select project to edit', options=project_options), width=8)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Label("Debug Projects", width=4),
                            dbc.Col(html.Small(id='projects-debug-list', className='text-muted'), width=8)
                        ], className='mb-2'),
                        dbc.Row([
                            dbc.Label("Project Name", width=4),
                            dbc.Col(dbc.Input(id="project-name-input", type="text"), width=8)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Label("Description", width=4),
                            dbc.Col(dbc.Textarea(id="project-desc-input"), width=8)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Label("Sales Tax Rate (%)", width=4),
                            dbc.Col(dbc.Input(id="sales-tax-input", type="number", value=0), width=8)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Label("Installation Rate (%)", width=4),
                            dbc.Col(dbc.Input(id="installation-rate-input", type="number", value=0), width=8)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Label("Include Install?", width=4),
                            dbc.Col(dbc.Checklist(id="include-installation-input", options=[{"label": "Yes", "value": 1}], value=[1]), width=8)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Label("Include Sales Tax?", width=4),
                            dbc.Col(dbc.Checklist(id="include-sales-tax-input", options=[{"label": "Yes", "value": 1}], value=[1]), width=8)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col(dbc.Button("Create Project", id="create-project-btn", color="primary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("Update Project", id="update-project-btn", color="secondary", className="w-100"), width=6)
                        ])
                    ], className='mb-2'),
                    dbc.Row([
                        dbc.Col(dbc.Button("Delete Project", id="delete-project-btn", color="danger", className="w-100"))
                    ]),
                    dcc.ConfirmDialog(id='delete-project-confirm', message='Delete this project and all related buildings, signs, and groups? This cannot be undone.')
                ])
            ], className="mb-3"),
            dbc.Card([
                dbc.CardHeader(html.H4("Existing Projects")),
                dbc.CardBody(id="projects-list", children=html.Div("No projects yet."))
            ]),
            html.Div(id="project-create-feedback")
        ], width=4)
    ])

def render_signs_tab():
    """Render the sign types management tab."""
    # Preload current sign_types so the table isn't empty if callback hasn't fired yet
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        preload_df = pd.read_sql_query(
            "SELECT name, description, material_alt, unit_price, material, price_per_sq_ft, material_multiplier, width, height, install_type, install_time_hours, per_sign_install_rate FROM sign_types ORDER BY name",
            conn
        )
        # Also preload material pricing so user immediately sees saved materials
        try:
            material_df = pd.read_sql_query("SELECT material_name, price_per_sq_ft FROM material_pricing ORDER BY material_name", conn)
        except Exception as me:
            print(f"[render_signs_tab][warn] failed preloading material_pricing: {me}")
            material_df = pd.DataFrame(columns=['material_name','price_per_sq_ft'])
        conn.close()
        preload_records = preload_df.to_dict('records')
        preload_materials = material_df.to_dict('records')
    except Exception as e:
        print(f"[render_signs_tab][warn] failed preloading sign_types: {e}")
        preload_records = []
        preload_materials = []
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Sign Types")),
                dbc.CardBody([
                    dash_table.DataTable(
                        id="signs-table",
                        columns=[
                            {"name": "Name", "id": "name", "editable": True},
                            {"name": "Description", "id": "description", "editable": True},
                            {"name": "Alt Material", "id": "material_alt", "editable": True},
                            {"name": "Material", "id": "material", "editable": True},
                            {"name": "Unit Price", "id": "unit_price", "type": "numeric", "editable": True},
                            {"name": "Price/Sq Ft", "id": "price_per_sq_ft", "type": "numeric", "editable": True},
                            {"name": "Mult", "id": "material_multiplier", "type": "numeric", "editable": True},
                            {"name": "Width", "id": "width", "type": "numeric", "editable": True},
                            {"name": "Height", "id": "height", "type": "numeric", "editable": True},
                            {"name": "Install Type", "id": "install_type", "editable": True},
                            {"name": "Install Hrs", "id": "install_time_hours", "type": "numeric", "editable": True},
                            {"name": "Per Sign Install $", "id": "per_sign_install_rate", "type": "numeric", "editable": True}
                        ],
                        data=preload_records,
                        editable=True,
                        row_deletable=True,
                        page_size=10,
                        style_table={"overflowX": "auto"}
                    ),
                    dbc.Button("Add New Sign Type", id="add-sign-btn", color="success", className="mt-3 me-2"),
                    dbc.Badge(id="signs-save-status", color="secondary", className="ms-2")
                ])
            ]),
            dbc.Card([
                dbc.CardHeader(html.H5("Material Pricing")),
                dbc.CardBody([
                    dash_table.DataTable(
                        id='material-pricing-table',
                        columns=[
                            {"name":"Material","id":"material_name","editable":True},
                            {"name":"Price / Sq Ft","id":"price_per_sq_ft","type":"numeric","editable":True}
                        ],
                        data=preload_materials, editable=True, row_deletable=True, page_size=8, style_table={'overflowX':'auto'}
                    ),
                    dbc.Button('Add Material', id='add-material-btn', color='secondary', className='mt-2 me-2'),
                    dbc.Button('Save Materials', id='save-materials-btn', color='primary', className='mt-2 me-2'),
                    dbc.Button('Recalculate Sign Prices', id='recalc-sign-prices-btn', color='warning', className='mt-2'),
                    html.Div(id='material-pricing-feedback', className='mt-2')
                ])
            ], className='mt-3')
        ]),
        dbc.Card([
            dbc.CardBody(
                dbc.Row([
                    dbc.Col(html.Small(id='debug-signs-stats', className='text-muted'), width='auto'),
                    dbc.Col(dbc.Button('×', id='close-debug-stats', color='link', size='sm', className='p-0 text-decoration-none'), width='auto')
                ], className='g-2 align-items-center justify-content-between flex-nowrap')
            )
        ], id='debug-signs-card', className='mt-2')
    ])

def render_groups_tab():
    """Render the sign groups management tab."""
    # Preload sign types & groups
    conn = sqlite3.connect(DATABASE_PATH)
    sign_types_df = pd.read_sql_query("SELECT id, name FROM sign_types ORDER BY name", conn)
    groups_df = pd.read_sql_query("SELECT id, name FROM sign_groups ORDER BY name", conn)
    conn.close()
    sign_type_options = [{"label": r.name, "value": r.id} for r in sign_types_df.itertuples()]
    group_options = [{"label": r.name, "value": r.id} for r in groups_df.itertuples()]
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("Create / Edit Group")),
                dbc.CardBody([
                    dbc.Input(id='group-name-input', placeholder='Group name'),
                    dbc.Textarea(id='group-desc-input', placeholder='Description', className='mt-2', style={'height': '60px'}),
                    dbc.Button('Save Group', id='save-group-btn', color='primary', className='mt-2 w-100'),
                    html.Div(id='group-save-feedback', className='mt-2')
                ])
            ]),
            dbc.Card([
                dbc.CardHeader(html.H5("Existing Groups")),
                dbc.CardBody([
                    dcc.Dropdown(id='group-select-dropdown', options=group_options, placeholder='Select group'),
                    dash_table.DataTable(
                        id='group-members-table',
                        columns=[
                            {"name": "Sign", "id": "sign_name"},
                            {"name": "Quantity", "id": "quantity", "type": "numeric"}
                        ],
                        data=[], editable=True, row_deletable=True, page_size=8, style_table={'overflowX': 'auto'}
                    ),
                    dbc.Row([
                        dbc.Col(dcc.Dropdown(id='group-add-sign-dropdown', options=sign_type_options, placeholder='Add sign type'), width=7),
                        dbc.Col(dbc.Input(id='group-add-sign-qty', type='number', min=1, value=1), width=3),
                        dbc.Col(dbc.Button('Add', id='group-add-sign-btn', color='success', className='w-100'), width=2)
                    ], className='mt-2 g-2'),
                    dbc.Button('Save Member Changes', id='group-save-members-btn', color='secondary', className='mt-2'),
                    html.Div(id='group-members-feedback', className='mt-2')
                ])
            ], className='mt-3')
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("Assign Groups to Building")),
                dbc.CardBody([
                    dcc.Dropdown(id='group-assign-project-dropdown', placeholder='Select project'),
                    dcc.Dropdown(id='group-assign-building-dropdown', placeholder='Select building', className='mt-2'),
                    dcc.Dropdown(id='group-assign-group-dropdown', options=group_options, placeholder='Select group', className='mt-2'),
                    dbc.Input(id='group-assign-qty', type='number', min=1, value=1, className='mt-2'),
                    dbc.Button('Add Group to Building', id='group-assign-btn', color='success', className='mt-2 w-100'),
                    html.Div(id='group-assign-feedback', className='mt-2'),
                    dash_table.DataTable(
                        id='building-groups-table',
                        columns=[
                            {"name": "Group", "id": "group_name"},
                            {"name": "Quantity", "id": "quantity", "type": "numeric"}
                        ],
                        data=[], editable=True, row_deletable=False, page_size=8
                    ),
                    dbc.Button('Save Group Quantities', id='building-save-group-qty-btn', color='primary', className='mt-2'),
                    html.Div(id='building-group-save-feedback', className='mt-2')
                ])
            ])
        ], width=6)
    ])

def render_building_tab():
    """Render dedicated building view and sign management."""
    # Preload project options
    conn = sqlite3.connect(DATABASE_PATH)
    pdf = pd.read_sql_query('SELECT id, name FROM projects ORDER BY name', conn)
    conn.close()
    project_options = ([{'label': r.name, 'value': r.id} for r in pdf.itertuples()]) if not pdf.empty else []
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4('Select Building')),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Project'),
                            dcc.Dropdown(id='bv-project-dropdown', options=project_options, placeholder='Select project')
                        ], md=4),
                        dbc.Col([
                            dbc.Label('Building'),
                            dcc.Dropdown(id='bv-building-dropdown', placeholder='Select building')
                        ], md=4),
                        dbc.Col([
                            dbc.Label('Rename'),
                            dbc.Input(id='bv-rename-building-input', placeholder='New building name'),
                            dbc.Button('Apply', id='bv-rename-building-btn', size='sm', color='warning', className='mt-1 w-100')
                        ], md=4)
                    ], className='g-3'),
                    html.Div(id='bv-building-meta', className='text-muted small mt-2')
                ])
            ]),
            dbc.Card([
                dbc.CardHeader(html.H5('Manage Signs')),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Add / Update Sign Type'),
                            dcc.Dropdown(id='bv-sign-type-dropdown', placeholder='Select sign type')
                        ], md=5),
                        dbc.Col([
                            dbc.Label('Quantity'),
                            dbc.Input(id='bv-sign-qty-input', type='number', min=1, value=1)
                        ], md=3),
                        dbc.Col([
                            dbc.Button('Add / Update', id='bv-add-sign-btn', color='success', className='mt-4 w-100')
                        ], md=4)
                    ], className='g-3 mb-3'),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Delete Sign'),
                            dcc.Dropdown(id='bv-delete-sign-dropdown', placeholder='Assigned sign')
                        ], md=8),
                        dbc.Col([
                            dbc.Button('Delete', id='bv-delete-sign-btn', color='danger', className='mt-4 w-100')
                        ], md=4)
                    ], className='g-3 mb-2'),
                    html.Hr(),
                    dbc.Row([
                        dbc.Col(html.H6('Groups', className='mt-2'), width=12)
                    ], className='mb-1'),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label('Remove Group'),
                            dcc.Dropdown(id='bv-delete-group-dropdown', placeholder='Assigned group')
                        ], md=8),
                        dbc.Col([
                            dbc.Button('Remove Group', id='bv-delete-group-btn', color='danger', className='mt-4 w-100')
                        ], md=4)
                    ], className='g-3 mb-2'),
                    dash_table.DataTable(
                        id='bv-signs-table',
                        columns=[
                            {'name':'Sign','id':'sign_name','editable':False},
                            {'name':'Quantity','id':'quantity','type':'numeric','editable':True},
                            {'name':'Unit Price','id':'unit_price','type':'numeric','editable':False},
                            {'name':'Total','id':'total','type':'numeric','editable':False}
                        ],
                        data=[], editable=True, row_deletable=False, page_size=12, style_table={'overflowX':'auto'}
                    ),
                    dbc.Button('Save Quantities', id='bv-save-signs-btn', color='primary', className='mt-2'),
                    html.Div(id='bv-feedback', className='mt-2')
                ])
            ], className='mt-3')
        ], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5('Summary')),
                dbc.CardBody([
                    html.Div(id='bv-summary', className='fw-bold'),
                    html.Hr(),
                    html.Small('Modify sign assignments directly. Use Projects tab for groups.', className='text-muted')
                ])
            ])
        ], width=4)
    ])

def render_estimates_tab():
    """Render the cost estimation and export tab."""
    # Populate project options fresh on each render
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query("SELECT id, name FROM projects ORDER BY name", conn)
    bdf = pd.read_sql_query("SELECT b.id, b.name, b.project_id, p.name as project_name FROM buildings b JOIN projects p ON b.project_id=p.id ORDER BY p.name, b.name", conn)
    conn.close()
    project_options = [{"label": r.name, "value": r.id} for r in df.itertuples()] if not df.empty else []
    building_options = [{"label": f"{r.name} (Project: {r.project_name})", "value": r.id} for r in bdf.itertuples()] if not bdf.empty else []
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Generate Project Estimate")),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Project"),
                            dcc.Dropdown(id='estimate-project-dropdown', placeholder='Select project', options=project_options)
                        ], md=4),
                        dbc.Col([
                            dbc.Label("Or Single Building"),
                            dcc.Dropdown(id='estimate-building-dropdown', placeholder='Optional: choose building(s)', options=building_options, multi=True)
                        ], md=4),
                        dbc.Col([
                            dbc.Button("Generate Estimate", id='generate-estimate-btn', color='primary', className='mt-4 w-100')
                        ], md=2),
                        dbc.Col([
                            dbc.Button("Export to Excel", id='export-estimate-btn', color='success', className='mt-4 w-100', disabled=True)
                        ], md=2),
                        dbc.Col([
                            dcc.Download(id='estimate-download')
                        ], md=2)
                    ], className='mb-3 g-2'),
                    dbc.Accordion([
                        dbc.AccordionItem([
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label('Sign Price Basis'),
                                    dbc.RadioItems(id='price-calc-mode', options=[
                                        {'label':'Stored Unit Price (Per Sign)','value':'per_sign'},
                                        {'label':'Area * Material Rate','value':'per_area'}
                                    ], value='per_sign', inline=False)
                                ], md=4),
                                dbc.Col([
                                    dbc.Label('Installation Mode'),
                                    dbc.RadioItems(id='install-mode', options=[
                                        {'label':'Percent of Subtotal','value':'percent'},
                                        {'label':'Per Sign','value':'per_sign'},
                                        {'label':'Per Area (sq ft)','value':'per_area'},
                                        {'label':'Hours * Hourly Rate','value':'hours'},
                                        {'label':'None','value':'none'}
                                    ], value='percent', inline=False)
                                ], md=4),
                                dbc.Col([
                                    dbc.Label('Parameters'),
                                    dbc.Row([
                                        dbc.Col(dbc.Input(id='install-percent-input', type='number', value=0, placeholder='% Install'), width=6),
                                        dbc.Col(dbc.Input(id='install-per-sign-rate', type='number', value=0, placeholder='Install $/Sign'), width=6)
                                    ], className='g-1 mt-1'),
                                    dbc.Row([
                                        dbc.Col(dbc.Input(id='install-per-area-rate', type='number', value=0, placeholder='Install $/SqFt'), width=6),
                                        dbc.Col(dbc.Input(id='install-hours-input', type='number', value=0, placeholder='Hours'), width=3),
                                        dbc.Col(dbc.Input(id='install-hourly-rate-input', type='number', value=0, placeholder='$/Hour'), width=3)
                                    ], className='g-1 mt-1'),
                                    dbc.Checklist(id='auto-install-use', options=[{'label':'Use auto per-sign rates / hours when manual blank','value':1}], value=[1], className='mt-2'),
                                    html.Small("Only the fields relevant to selected modes are used.", className='text-muted')
                                ], md=4)
                            ], className='g-3')
                        ], title='Advanced Calculation Options')
                    ], start_collapsed=True, className='mb-3'),
                    dash_table.DataTable(
                        id='estimate-table',
                        columns=[
                            {"name": "Building", "id": "Building"},
                            {"name": "Item", "id": "Item"},
                            {"name": "Material", "id": "Material"},
                            {"name": "Dimensions", "id": "Dimensions"},
                            {"name": "Quantity", "id": "Quantity", "type": "numeric"},
                            {"name": "Unit Price", "id": "Unit_Price", "type": "numeric"},
                            {"name": "Total", "id": "Total", "type": "numeric"}
                        ],
                        data=[],
                        style_table={"overflowX": "auto"},
                        page_size=15
                    ),
                    html.Hr(),
                    html.Div(id='estimate-summary')
                ])
            ])
        ])
    ])

def render_import_tab():
    """Render the data import tab."""
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Import CSV Data")),
                dbc.CardBody([
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div([
                            'Drag and Drop or ',
                            html.A('Select Files')
                        ]),
                        style={
                            'width': '100%',
                            'height': '60px',
                            'lineHeight': '60px',
                            'borderWidth': '1px',
                            'borderStyle': 'dashed',
                            'borderRadius': '5px',
                            'textAlign': 'center',
                            'margin': '10px'
                        },
                        multiple=False
                    ),
                    html.Div(id='upload-output'),
                    html.Hr(),
                    dbc.Button('Import Local Book2.csv', id='import-book2-btn', color='secondary'),
                    html.Div(id='book2-import-feedback', className='mt-2 text-muted', style={'fontSize':'0.9rem'})
                ])
            ])
        ])
    ])

@app.callback(
    Output('upload-output', 'children'),
    Output('signs-table', 'data', allow_duplicate=True),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    prevent_initial_call=True
)
def update_output(contents, filename):
    if contents is not None:
        # Process uploaded file
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        try:
            # Assume CSV file
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
            inserted = _load_sign_types_from_df(df)
            # Reload table data after import
            conn = sqlite3.connect(DATABASE_PATH)
            table_df = pd.read_sql_query("SELECT name, description, unit_price, material, price_per_sq_ft, width, height FROM sign_types ORDER BY name", conn)
            conn.close()
            return dbc.Alert(f"Imported/updated {inserted} sign types from {filename}", color="success"), table_df.to_dict('records')
            
        except Exception as e:
            return dbc.Alert(f"Error processing file: {str(e)}", color="danger"), dash.no_update
    
    return html.Div(), dash.no_update

# ----------- Force Import Book2.csv (manual trigger) ------------- #
def _force_import_book2(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found")
    df = pd.read_csv(csv_path)
    records = []
    def parse_cost(val):
        if isinstance(val, str):
            txt = val.replace('$','').replace(',','').strip()
            if not txt:
                return 0.0
            try:
                return float(txt)
            except:
                return 0.0
        try:
            return float(val or 0)
        except:
            return 0.0
    for r in df.to_dict('records'):
        name = str(r.get('Code') or r.get('Desc') or r.get('full_name') or '').strip()
        if not name:
            continue
        width = r.get('Width') or 0
        height = r.get('Height') or 0
        material = r.get('Material2') or r.get('Material') or ''
        ppsf_raw = r.get('material_multiplier') or r.get('Unnamed: 24') or 0
        try:
            ppsf = float(str(ppsf_raw).replace('$','').replace(',','')) if ppsf_raw not in (None,'') else 0.0
        except:
            ppsf = 0.0
        unit_price = parse_cost(r.get('item_cost'))
        try:
            if unit_price == 0 and width and height and ppsf:
                unit_price = float(width) * float(height) * float(ppsf)
        except:
            pass
        records.append((name[:120], str(r.get('Desc') or r.get('full_name') or '')[:255], unit_price, str(material)[:120], ppsf, float(width or 0), float(height or 0)))
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.executemany('''
        INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(name) DO UPDATE SET description=excluded.description,
            unit_price=excluded.unit_price, material=excluded.material,
            price_per_sq_ft=excluded.price_per_sq_ft, width=excluded.width, height=excluded.height
    ''', records)
    conn.commit()
    cur.execute('SELECT COUNT(*) FROM sign_types')
    total = cur.fetchone()[0]
    conn.close()
    return len(records), total

@app.callback(
    Output('book2-import-feedback','children'),
    Output('signs-table','data', allow_duplicate=True),
    Input('import-book2-btn','n_clicks'),
    prevent_initial_call=True
)
def manual_import_book2(n):
    if not n:
        raise PreventUpdate
    csv_path = Path('Book2.csv')
    try:
        imported, total = _force_import_book2(csv_path)
        conn = sqlite3.connect(DATABASE_PATH)
        df = pd.read_sql_query(
            "SELECT name, description, material_alt, unit_price, material, price_per_sq_ft, material_multiplier, width, height, install_type, install_time_hours, per_sign_install_rate FROM sign_types ORDER BY name",
            conn
        )
        conn.close()
        return dbc.Alert(f"Imported/merged {imported} rows from {csv_path.name}. sign_types now has {total} rows.", color='success'), df.to_dict('records')
    except Exception as e:
        return dbc.Alert(f"Import failed: {e}", color='danger'), dash.no_update

# ------------------ Project Creation & Listing ------------------ #
@app.callback(
    Output('projects-list', 'children', allow_duplicate=True),
    Output('project-create-feedback', 'children', allow_duplicate=True),
    Output('project-tree', 'figure', allow_duplicate=True),
    Output('assign-project-dropdown', 'options'),
    Output('project-edit-dropdown', 'options', allow_duplicate=True),
    Output('projects-debug-list','children', allow_duplicate=True),
    Input('create-project-btn', 'n_clicks'),
    State('project-name-input', 'value'),
    State('project-desc-input', 'value'),
    State('sales-tax-input', 'value'),
    State('installation-rate-input', 'value'),
    State('include-installation-input', 'value'),
    State('include-sales-tax-input', 'value'),
    prevent_initial_call=True
)
def create_or_refresh_projects(n_clicks, name, desc, sales_tax, install_rate, include_install_values, include_tax_values):
    if not n_clicks:
        raise PreventUpdate
    if not name:  # early validation
        return (
            dash.no_update,  # projects-list
            dbc.Alert("Project name required", color='danger'),  # feedback
            dash.no_update,  # tree fig
            dash.no_update,  # assign-project-dropdown options
            dash.no_update,  # project-edit-dropdown options
            dash.no_update   # projects-debug-list
        )
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO projects (name, description, sales_tax_rate, installation_rate, include_installation, include_sales_tax) VALUES (?,?,?,?,?,?)", (
            name.strip(),
            desc or '',
            float(sales_tax or 0)/100.0,
            float(install_rate or 0)/100.0,
            1 if (include_install_values and 1 in include_install_values) else 0,
            1 if (include_tax_values and 1 in include_tax_values) else 0
        ))
        conn.commit()
        # Reload project list/options
        df = pd.read_sql_query("SELECT id, name, created_date FROM projects ORDER BY id DESC", conn)
        conn.close()
        if df.empty:
            list_children = html.Div("No projects yet.")
            project_options = []
        else:
            rows = [html.Li(f"{r.name} (ID {r.id}) - {r.created_date}") for r in df.itertuples()]
            list_children = html.Ul(rows, className="mb-0")
            project_options = [{"label": r.name, "value": r.id} for r in df.itertuples()]
        tree_fig = safe_tree_figure()
        feedback = dbc.Alert(f"Project '{name}' created", color='success', dismissable=True)
        debug_txt = ' | '.join(f"{r.id}:{r.name}" for r in df.itertuples()) if not df.empty else 'none'
        return list_children, feedback, tree_fig, project_options, project_options, debug_txt
    except sqlite3.IntegrityError:
        return dash.no_update, dbc.Alert(f"Project '{name}' already exists", color='warning'), dash.no_update, dash.no_update, dash.no_update, dash.no_update
    except Exception as e:
        return dash.no_update, dbc.Alert(f"Error: {e}", color='danger'), dash.no_update, dash.no_update, dash.no_update, dash.no_update

@app.callback(
    Output('project-name-input','value'),
    Output('project-desc-input','value'),
    Output('sales-tax-input','value'),
    Output('installation-rate-input','value'),
    Output('include-installation-input','value'),
    Output('include-sales-tax-input','value'),
    Input('project-edit-dropdown','value'),
    prevent_initial_call=True
)
def load_project_for_edit(project_id):
    if not project_id:
        raise PreventUpdate
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query('SELECT * FROM projects WHERE id=?', conn, params=(project_id,))
    conn.close()
    if df.empty:
        raise PreventUpdate
    r = df.iloc[0]
    return r['name'], r.get('description',''), round((r.get('sales_tax_rate') or 0)*100,4), round((r.get('installation_rate') or 0)*100,4), ([1] if r.get('include_installation') else []), ([1] if r.get('include_sales_tax') else [])

@app.callback(
    Output('project-create-feedback','children', allow_duplicate=True),
    Output('project-tree','figure', allow_duplicate=True),
    Input('update-project-btn','n_clicks'),
    State('project-edit-dropdown','value'),
    State('project-name-input','value'),
    State('project-desc-input','value'),
    State('sales-tax-input','value'),
    State('installation-rate-input','value'),
    State('include-installation-input','value'),
    State('include-sales-tax-input','value'),
    prevent_initial_call=True
)
def update_project(n_clicks, project_id, name, desc, sales_tax, install_rate, include_install_values, include_tax_values):
    if not n_clicks:
        raise PreventUpdate
    if not project_id or not name:
        return dbc.Alert('Select project and ensure name present', color='danger'), dash.no_update
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute('''UPDATE projects SET name=?, description=?, sales_tax_rate=?, installation_rate=?, include_installation=?, include_sales_tax=?, last_modified=CURRENT_TIMESTAMP WHERE id=?''', (
        name.strip(), desc or '', float(sales_tax or 0)/100.0, float(install_rate or 0)/100.0,
        1 if (include_install_values and 1 in include_install_values) else 0,
        1 if (include_tax_values and 1 in include_tax_values) else 0,
        project_id
    ))
    conn.commit(); conn.close()
    return dbc.Alert('Project updated', color='success'), safe_tree_figure()

# Unified refresh for project-edit-dropdown and debug list
## removed refresh_project_dropdown to simplify; debug string handled in create/delete callbacks

# ------------------ Building Management & Sign Assignment ------------------ #
@app.callback(
    Output('building-dropdown', 'options'),
    Output('building-dropdown', 'value'),
    Output('sign-type-dropdown', 'options'),
    Input('assign-project-dropdown', 'value')
)
def load_buildings_for_project(project_id):
    if not project_id:
        return [], None, []
    conn = sqlite3.connect(DATABASE_PATH)
    buildings = pd.read_sql_query("SELECT id, name FROM buildings WHERE project_id = ? ORDER BY id", conn, params=(project_id,))
    sign_types = pd.read_sql_query("SELECT id, name, unit_price FROM sign_types ORDER BY name", conn)
    conn.close()
    building_options = [{"label": r.name, "value": r.id} for r in buildings.itertuples()]
    sign_type_options = [{"label": f"{r.name} (${r.unit_price})", "value": r.id} for r in sign_types.itertuples()]
    return building_options, (building_options[0]['value'] if building_options else None), sign_type_options

@app.callback(
    Output('building-dropdown', 'options', allow_duplicate=True),
    Output('building-action-feedback', 'children', allow_duplicate=True),
    Output('project-tree', 'figure', allow_duplicate=True),
    Input('add-building-btn', 'n_clicks'),
    State('assign-project-dropdown', 'value'),
    State('new-building-name', 'value'),
    State('new-building-desc', 'value'),
    prevent_initial_call=True
)
def add_building(n_clicks, project_id, name, desc):
    if not n_clicks:
        raise PreventUpdate
    if not project_id or not name:
        return dash.no_update, "Select project and enter name", dash.no_update
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    # Duplicate name check (case-insensitive) within project
    cur.execute("SELECT 1 FROM buildings WHERE project_id=? AND LOWER(name)=LOWER(?)", (project_id, name.strip()))
    if cur.fetchone():
        conn.close()
        return dash.no_update, f"Building name '{name}' already exists", dash.no_update
    cur.execute("INSERT INTO buildings (project_id, name, description) VALUES (?,?,?)", (project_id, name.strip(), desc or ''))
    conn.commit()
    buildings = pd.read_sql_query("SELECT id, name FROM buildings WHERE project_id = ? ORDER BY id", conn, params=(project_id,))
    conn.close()
    options = [{"label": r.name, "value": r.id} for r in buildings.itertuples()]
    tree_fig = safe_tree_figure()
    return options, f"Building '{name}' added", tree_fig

@app.callback(
    Output('building-dropdown','options', allow_duplicate=True),
    Output('building-action-feedback','children', allow_duplicate=True),
    Output('project-tree','figure', allow_duplicate=True),
    Input('rename-building-btn','n_clicks'),
    State('assign-project-dropdown','value'),
    State('building-dropdown','value'),
    State('rename-building-input','value'),
    prevent_initial_call=True
)
def rename_building(n_clicks, project_id, building_id, new_name):
    if not n_clicks:
        raise PreventUpdate
    if not (project_id and building_id and new_name and new_name.strip()):
        return dash.no_update, 'Provide building and new name', dash.no_update
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    # uniqueness within project
    cur.execute('SELECT 1 FROM buildings WHERE project_id=? AND LOWER(name)=LOWER(?) AND id<>?', (project_id, new_name.strip(), building_id))
    if cur.fetchone():
        conn.close()
        return dash.no_update, f"Name '{new_name}' already exists", dash.no_update
    cur.execute('UPDATE buildings SET name=?, last_modified=CURRENT_TIMESTAMP WHERE id=?', (new_name.strip(), building_id))
    conn.commit()
    bdf = pd.read_sql_query('SELECT id, name FROM buildings WHERE project_id=? ORDER BY id', conn, params=(project_id,))
    conn.close()
    options = [{'label': r.name, 'value': r.id} for r in bdf.itertuples()]
    return options, 'Building renamed', safe_tree_figure()

def _fetch_building_signs(building_id):
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query('''
        SELECT st.name as sign_name, bs.quantity, st.unit_price, (bs.quantity * st.unit_price) as total
        FROM building_signs bs
        JOIN sign_types st ON bs.sign_type_id = st.id
        WHERE bs.building_id = ?
        ORDER BY st.name
    ''', conn, params=(building_id,))
    conn.close()
    return df.to_dict('records')

def _fetch_building_name(building_id):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        df = pd.read_sql_query('SELECT name FROM buildings WHERE id=?', conn, params=(building_id,))
        conn.close()
        if df.empty:
            return ''
        return df.iloc[0]['name']
    except Exception:
        return ''

@app.callback(
    Output('building-signs-table', 'data'),
    Output('building-action-feedback', 'children', allow_duplicate=True),
    Output('project-tree', 'figure', allow_duplicate=True),
    Input('building-dropdown', 'value'),
    Input('add-sign-to-building-btn', 'n_clicks'),
    Input('save-building-signs-btn', 'n_clicks'),
    State('sign-type-dropdown', 'value'),
    State('sign-qty-input', 'value'),
    State('building-signs-table', 'data'),
    prevent_initial_call=True
)
def manage_building_signs(building_id, add_clicks, save_clicks, sign_type_id, qty, current_rows):
    triggered = [t['prop_id'].split('.')[0] for t in callback_context.triggered] if callback_context.triggered else []
    if not building_id:
        return [], dash.no_update, dash.no_update
    action_msg = dash.no_update
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    if 'add-sign-to-building-btn' in triggered and sign_type_id:
        qty = max(1, int(qty or 1))
        cur.execute("SELECT id, quantity FROM building_signs WHERE building_id=? AND sign_type_id=?", (building_id, sign_type_id))
        existing = cur.fetchone()
        if existing:
            cur.execute("UPDATE building_signs SET quantity=? WHERE id=?", (qty, existing[0]))
        else:
            cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)", (building_id, sign_type_id, qty))
        action_msg = "Sign added/updated"
    elif 'save-building-signs-btn' in triggered and current_rows:
        for row in current_rows:
            name = row.get('sign_name')
            q = max(0, int(row.get('quantity') or 0))
            cur.execute("SELECT id FROM sign_types WHERE name = ?", (name,))
            st_row = cur.fetchone()
            if not st_row:
                continue
            st_id = st_row[0]
            cur.execute("SELECT id FROM building_signs WHERE building_id=? AND sign_type_id=?", (building_id, st_id))
            ex = cur.fetchone()
            if ex:
                cur.execute("UPDATE building_signs SET quantity=? WHERE id=?", (q, ex[0]))
            else:
                cur.execute("INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)", (building_id, st_id, q))
        action_msg = "Quantities saved"
    if action_msg is not dash.no_update:
        conn.commit()
    conn.close()
    data = _fetch_building_signs(building_id)
    tree_fig = safe_tree_figure()
    return data, action_msg, tree_fig

# -------- Sign Groups within Projects Tab -------- #
@app.callback(
    Output('project-group-dropdown','options'),
    Input('assign-project-dropdown','value')
)
def load_group_options_for_project(_project_id):
    conn = sqlite3.connect(DATABASE_PATH)
    gdf = pd.read_sql_query('SELECT id, name FROM sign_groups ORDER BY name', conn)
    conn.close()
    return ([{'label': r.name, 'value': r.id} for r in gdf.itertuples()]) if not gdf.empty else []

def _fetch_building_groups(building_id):
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query('''SELECT sg.name as group_name, bsg.quantity, sg.id as group_id
                               FROM building_sign_groups bsg
                               JOIN sign_groups sg ON bsg.group_id = sg.id
                               WHERE bsg.building_id=? ORDER BY sg.name''', conn, params=(building_id,))
    conn.close()
    return df.to_dict('records')

def _fetch_assigned_group_options(building_id):
    """Return dropdown options for groups already assigned to a building."""
    if not building_id:
        return []
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query('''SELECT sg.id, sg.name FROM sign_groups sg
                               JOIN building_sign_groups bsg ON bsg.group_id=sg.id
                               WHERE bsg.building_id=? ORDER BY sg.name''', conn, params=(building_id,))
    conn.close()
    return [{'label': r['name'], 'value': r['id']} for _, r in df.iterrows()]

@app.callback(
    Output('project-building-groups-table','data'),
    Output('building-groups-feedback','children', allow_duplicate=True),
    Output('project-tree','figure', allow_duplicate=True),
    Input('building-dropdown','value'),
    Input('add-group-to-building-btn','n_clicks'),
    Input('save-building-groups-btn','n_clicks'),
    State('project-group-dropdown','value'),
    State('group-qty-input','value'),
    State('project-building-groups-table','data'),
    prevent_initial_call=True
)
def manage_building_groups_inline(building_id, add_clicks, save_clicks, group_id, qty, rows):
    triggered = [t['prop_id'].split('.')[0] for t in callback_context.triggered] if callback_context.triggered else []
    if not building_id:
        return [], dash.no_update, dash.no_update
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    msg = dash.no_update
    if 'add-group-to-building-btn' in triggered and group_id:
        q = max(1, int(qty or 1))
        cur.execute('SELECT id, quantity FROM building_sign_groups WHERE building_id=? AND group_id=?', (building_id, group_id))
        ex = cur.fetchone()
        if ex:
            cur.execute('UPDATE building_sign_groups SET quantity=? WHERE id=?', (q, ex[0]))
        else:
            cur.execute('INSERT INTO building_sign_groups (building_id, group_id, quantity) VALUES (?,?,?)', (building_id, group_id, q))
        msg = 'Group added/updated'
    elif 'save-building-groups-btn' in triggered and rows:
        for r in rows:
            gname = r.get('group_name')
            q = max(0, int(r.get('quantity') or 0))
            cur.execute('SELECT id FROM sign_groups WHERE name=?', (gname,))
            gr = cur.fetchone()
            if not gr:
                continue
            cur.execute('SELECT id FROM building_sign_groups WHERE building_id=? AND group_id=?', (building_id, gr[0]))
            ex = cur.fetchone()
            if ex:
                cur.execute('UPDATE building_sign_groups SET quantity=? WHERE id=?', (q, ex[0]))
        msg = 'Group quantities saved'
    conn.commit()
    group_rows = _fetch_building_groups(building_id)
    conn.close()
    tree_fig = safe_tree_figure()
    return group_rows, msg, tree_fig

# --- Filter group options (Show All vs project-assigned) & populate deletion dropdown --- #
@app.callback(
    Output('project-group-dropdown','options', allow_duplicate=True),
    Output('assigned-group-delete-dropdown','options'),
    Input('assign-project-dropdown','value'),
    Input('building-dropdown','value'),
    Input('project-groups-show-all','value'),
    Input('project-building-groups-table','data'),  # refresh after add/save quantity
    prevent_initial_call=True
)
def refresh_project_group_dropdowns(project_id, building_id, show_all_values, _group_table_rows):
    try:
        # Deletion dropdown
        assigned_opts = _fetch_assigned_group_options(building_id)
        # Group options
        show_all = bool(show_all_values and 'all' in show_all_values)
        if show_all:
            conn = sqlite3.connect(DATABASE_PATH)
            gdf = pd.read_sql_query('SELECT id, name FROM sign_groups ORDER BY name', conn)
            conn.close()
            group_opts = [{'label': r['name'], 'value': r['id']} for _, r in gdf.iterrows()]
        else:
            if project_id:
                conn = sqlite3.connect(DATABASE_PATH)
                gdf = pd.read_sql_query('''SELECT DISTINCT sg.id, sg.name FROM sign_groups sg
                                            JOIN building_sign_groups bsg ON bsg.group_id=sg.id
                                            JOIN buildings b ON bsg.building_id=b.id
                                            WHERE b.project_id=? ORDER BY sg.name''', conn, params=(project_id,))
                conn.close()
                group_opts = [{'label': r['name'], 'value': r['id']} for _, r in gdf.iterrows()]
            else:
                group_opts = []
        return group_opts, assigned_opts
    except Exception as e:
        print(f"[groups][filter][error] {e}")
        return dash.no_update, dash.no_update

# --- Remove group from building --- #
@app.callback(
    Output('project-building-groups-table','data', allow_duplicate=True),
    Output('building-groups-feedback','children', allow_duplicate=True),
    Output('project-tree','figure', allow_duplicate=True),
    Output('assigned-group-delete-dropdown','options', allow_duplicate=True),
    Input('remove-group-from-building-btn','n_clicks'),
    State('building-dropdown','value'),
    State('assigned-group-delete-dropdown','value'),
    prevent_initial_call=True
)
def remove_group_from_building(n_clicks, building_id, group_id):
    if not n_clicks:
        raise PreventUpdate
    if not building_id or not group_id:
        return dash.no_update, 'Select building and group to remove', dash.no_update, dash.no_update
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.execute('DELETE FROM building_sign_groups WHERE building_id=? AND group_id=?', (building_id, group_id))
        conn.commit()
        df = pd.read_sql_query('''SELECT sg.name as group_name, bsg.quantity, sg.id as group_id
                                   FROM building_sign_groups bsg
                                   JOIN sign_groups sg ON bsg.group_id=sg.id
                                   WHERE bsg.building_id=? ORDER BY sg.name''', conn, params=(building_id,))
        conn.close()
        table_rows = df.to_dict('records')
        assigned_opts = _fetch_assigned_group_options(building_id)
        return table_rows, 'Group removed', safe_tree_figure(), assigned_opts
    except Exception as e:
        print(f"[groups][remove][error] {e}")
        return dash.no_update, f'Error removing: {e}', dash.no_update, dash.no_update

# --- Global error toast trigger (simple heuristic scanning for keyword) --- #
@app.callback(
    Output('app-error-toast','is_open'),
    Output('app-error-toast','children'),
    Input('building-groups-feedback','children'),
    Input('project-create-feedback','children'),
    prevent_initial_call=True
)
def surface_errors(*feedback_children):
    for child in feedback_children:
        if not child:
            continue
        # Convert component to string for heuristic search
        text = ''
        try:
            if isinstance(child, (str, int, float)):
                text = str(child)
            elif hasattr(child, 'props') and 'children' in child.props:
                # For dbc.Alert etc.
                inner = child.props.get('children')
                text = inner if isinstance(inner, str) else str(inner)
            else:
                text = str(child)
        except Exception:
            text = str(child)
        lowered = text.lower()
        if 'error' in lowered or 'warning' in lowered or 'already exists' in lowered:
            return True, text
    raise PreventUpdate

# ------------------ Estimate Generation & Export ------------------ #
@app.callback(
    Output('estimate-table', 'data'),
    Output('estimate-summary', 'children'),
    Output('export-estimate-btn', 'disabled'),
    Input('generate-estimate-btn', 'n_clicks'),
    State('estimate-project-dropdown', 'value'),
    State('estimate-building-dropdown', 'value'),
    State('price-calc-mode','value'),
    State('install-mode','value'),
    State('install-percent-input','value'),
    State('install-per-sign-rate','value'),
    State('install-per-area-rate','value'),
    State('install-hours-input','value'),
    State('install-hourly-rate-input','value'),
    State('auto-install-use','value'),
    prevent_initial_call=True
)
def generate_estimate(n_clicks, project_id, building_id, price_mode, install_mode, inst_percent, inst_per_sign, inst_per_area, inst_hours, inst_hourly, auto_install_toggle):
    if not n_clicks:
        raise PreventUpdate
    if db_manager is None:
        return [], dbc.Alert("Database not initialized", color='danger'), True
    # building_id may now be list (multi select). Normalize.
    building_ids = []
    if isinstance(building_id, list):
        building_ids = [b for b in building_id if b is not None]
    elif building_id:
        building_ids = [building_id]
    if not project_id and not building_ids:
        return [], dbc.Alert("Select a project or building(s)", color='warning'), True
    # If only buildings chosen, derive project (assume same project; take first)
    if building_ids and not project_id:
        conn = sqlite3.connect(DATABASE_PATH)
        placeholders = ','.join(['?']*len(building_ids))
        pdf = pd.read_sql_query(f'SELECT DISTINCT project_id FROM buildings WHERE id IN ({placeholders})', conn, params=tuple(building_ids))
        conn.close()
        if not pdf.empty:
            project_id = pdf.iloc[0]['project_id']
    def _coerce(v):
        try: return float(v or 0)
        except: return 0.0
    inst_percent = _coerce(inst_percent)
    inst_per_sign = _coerce(inst_per_sign)
    inst_per_area = _coerce(inst_per_area)
    inst_hours = _coerce(inst_hours)
    inst_hourly = _coerce(inst_hourly)

    use_default = (price_mode == 'per_sign' and install_mode == 'percent')
    auto_enabled = bool(auto_install_toggle and 1 in auto_install_toggle)
    meta = {}
    if use_default:
        estimate_data = db_manager.get_project_estimate(project_id) or []
    else:
        from utils.estimate_core import compute_custom_estimate
        # Provide building filter directly if user selected building_ids; else None for all
        estimate_result = compute_custom_estimate(
            DATABASE_PATH, project_id, building_ids if building_ids else None,
            price_mode, install_mode,
            inst_percent, inst_per_sign, inst_per_area, inst_hours, inst_hourly,
            auto_enabled, return_meta=True
        )
        if isinstance(estimate_result, tuple):
            estimate_data, meta = estimate_result
        else:
            estimate_data = estimate_result
    if not estimate_data:
        return [], dbc.Alert("No data", color='warning'), True
    # If we used default path and building_ids provided, filter manually
    if use_default and building_ids:
        conn = sqlite3.connect(DATABASE_PATH)
        placeholders = ','.join(['?']*len(building_ids))
        ndf = pd.read_sql_query(f'SELECT id, name FROM buildings WHERE id IN ({placeholders})', conn, params=tuple(building_ids))
        conn.close()
        selected_names = set(ndf['name'].tolist())
        estimate_data = [r for r in estimate_data if r['Building'] in selected_names or r['Building']=='ALL']
    if not estimate_data:
        return [], dbc.Alert("No data for selection", color='warning'), True
    df = pd.DataFrame(estimate_data)
    total = df['Total'].sum() if 'Total' in df else 0
    # Build chips & meta display
    chips = []
    chips.append(dbc.Badge(f"Total: ${total:,.2f}", color='primary', className='me-1'))
    if building_ids:
        chips.append(dbc.Badge(f"Buildings: {len(building_ids)}", color='secondary', className='me-1'))
    if not use_default and meta:
        chips.append(dbc.Badge(f"Signs: {int(meta.get('total_sign_count',0))}", color='info', className='me-1'))
        if meta.get('total_area'):
            chips.append(dbc.Badge(f"Area: {meta['total_area']:.1f} sq ft", color='light', text_color='dark', className='me-1'))
        if meta.get('auto_install_amount_per_sign'):
            chips.append(dbc.Badge(f"Auto Inst $/sign sum: ${meta['auto_install_amount_per_sign']:.2f}", color='warning', className='me-1'))
        if meta.get('auto_install_hours'):
            chips.append(dbc.Badge(f"Auto Inst Hours: {meta['auto_install_hours']:.1f}", color='warning', className='me-1'))
        if meta.get('install_cost'):
            chips.append(dbc.Badge(f"Install: ${meta['install_cost']:.2f}", color='danger', className='me-1'))
    # Pricing mode note
    note_lines = []
    if price_mode == 'per_area':
        note_lines.append("Pricing basis: Area * Material Rate")
    if not use_default:
        note_lines.append(f"Install mode: {install_mode}")
    summary = html.Div([
        html.Div(chips, className='mb-1'),
        html.Small(" | ".join(note_lines)) if note_lines else None
    ])
    return df.to_dict('records'), summary, False

@app.callback(
    Output('estimate-download', 'data'),
    Input('export-estimate-btn', 'n_clicks'),
    State('estimate-project-dropdown', 'value'),
    State('estimate-building-dropdown', 'value'),
    State('price-calc-mode','value'),
    State('install-mode','value'),
    State('install-percent-input','value'),
    State('install-per-sign-rate','value'),
    State('install-per-area-rate','value'),
    State('install-hours-input','value'),
    State('install-hourly-rate-input','value'),
    State('auto-install-use','value'),
    prevent_initial_call=True
)
def export_estimate(n_clicks, project_id, building_id, price_mode, install_mode, inst_percent, inst_per_sign, inst_per_area, inst_hours, inst_hourly, auto_install_toggle):
    if not n_clicks:
        raise PreventUpdate
    # Normalize multi select
    building_ids = []
    if isinstance(building_id, list):
        building_ids = [b for b in building_id if b is not None]
    elif building_id:
        building_ids = [building_id]
    if not project_id and not building_ids:
        return dash.no_update
    if db_manager is None:
        return dash.no_update
    # Derive project id from building if needed
    if building_ids and not project_id:
        conn = sqlite3.connect(DATABASE_PATH)
        placeholders = ','.join(['?']*len(building_ids))
        pdf = pd.read_sql_query(f'SELECT DISTINCT project_id FROM buildings WHERE id IN ({placeholders})', conn, params=tuple(building_ids))
        conn.close()
        if not pdf.empty:
            project_id = pdf.iloc[0]['project_id']
    try:
        # Reuse generate_estimate core logic by lightweight inline recompute (duplicated minimal branch for export)
        def _coerce(v):
            try: return float(v or 0)
            except: return 0.0
        inst_percent=_coerce(inst_percent); inst_per_sign=_coerce(inst_per_sign); inst_per_area=_coerce(inst_per_area); inst_hours=_coerce(inst_hours); inst_hourly=_coerce(inst_hourly)
        use_default = (price_mode=='per_sign' and install_mode=='percent')
        if use_default:
            estimate_data = db_manager.get_project_estimate(project_id) or []
        else:
            estimate_data = []
            conn = sqlite3.connect(DATABASE_PATH)
            proj_df = pd.read_sql_query('SELECT * FROM projects WHERE id=?', conn, params=(project_id,))
            if proj_df.empty:
                conn.close(); return dash.no_update
            project = proj_df.iloc[0]
            buildings = pd.read_sql_query('SELECT * FROM buildings WHERE project_id=?', conn, params=(project_id,))
            grand_subtotal=0.0; total_sign_count=0; total_area=0.0; auto_install_amount_per_sign=0.0; auto_install_hours=0.0
            auto_enabled = bool(auto_install_toggle and 1 in auto_install_toggle)
            for _, b in buildings.iterrows():
                b_sub=0.0
                signs = pd.read_sql_query('''SELECT st.name, st.unit_price, st.material, st.width, st.height, st.price_per_sq_ft, st.per_sign_install_rate, st.install_time_hours, bs.quantity
                                              FROM building_signs bs JOIN sign_types st ON bs.sign_type_id=st.id WHERE bs.building_id=?''', conn, params=(b['id'],))
                for _, s in signs.iterrows():
                    qty = s['quantity'] or 0
                    total_sign_count += qty
                    width=_coerce(s['width']); height=_coerce(s['height']); ppsf=_coerce(s['price_per_sq_ft'])
                    area = width*height if width and height else 0
                    total_area += area*qty
                    ps_install=_coerce(s.get('per_sign_install_rate'))
                    if ps_install>0:
                        auto_install_amount_per_sign += ps_install * qty
                    inst_time=_coerce(s.get('install_time_hours'))
                    if inst_time>0:
                        auto_install_hours += inst_time * qty
                    unit_price = compute_unit_price(s.to_dict(), price_mode)
                    line_total = unit_price*qty
                    b_sub += line_total
                    estimate_data.append({'Building':b['name'],'Item':s['name'],'Material':s['material'],'Dimensions':f"{width} x {height}" if width and height else '', 'Quantity':qty,'Unit_Price':unit_price,'Total':line_total})
                groups = pd.read_sql_query('''SELECT sg.id, sg.name, bsg.quantity FROM building_sign_groups bsg JOIN sign_groups sg ON bsg.group_id=sg.id WHERE bsg.building_id=?''', conn, params=(b['id'],))
                for _, g in groups.iterrows():
                    group_members = pd.read_sql_query('''SELECT st.name, st.unit_price, st.width, st.height, st.price_per_sq_ft, st.per_sign_install_rate, st.install_time_hours, st.material_multiplier, sgm.quantity FROM sign_group_members sgm JOIN sign_types st ON sgm.sign_type_id=st.id WHERE sgm.group_id=?''', conn, params=(g['id'],))
                    group_cost_unit=0.0
                    for _, m in group_members.iterrows():
                        m_qty = (m['quantity'] or 0)
                        width=_coerce(m['width']); height=_coerce(m['height']); ppsf=_coerce(m['price_per_sq_ft'])
                        area=width*height if width and height else 0
                        total_sign_count += m_qty * g['quantity']
                        total_area += area * m_qty * g['quantity']
                        ps_install=_coerce(m.get('per_sign_install_rate'))
                        if ps_install>0:
                            auto_install_amount_per_sign += ps_install * m_qty * g['quantity']
                        inst_time=_coerce(m.get('install_time_hours'))
                        if inst_time>0:
                            auto_install_hours += inst_time * m_qty * g['quantity']
                        m_unit = compute_unit_price(m.to_dict(), price_mode)
                        group_cost_unit += m_unit * m_qty
                    unit_price=group_cost_unit; line_total=unit_price * g['quantity']; b_sub+=line_total
                    estimate_data.append({'Building':b['name'],'Item':f"Group: {g['name']}",'Material':'Various','Dimensions':'','Quantity':g['quantity'],'Unit_Price':unit_price,'Total':line_total})
                grand_subtotal+=b_sub
            install_cost = compute_install_cost(
                install_mode, grand_subtotal, total_sign_count, total_area,
                inst_percent, inst_per_sign, inst_per_area, inst_hours, inst_hourly,
                auto_enabled, auto_install_amount_per_sign, auto_install_hours
            )
            if install_mode!='none' and install_cost>0:
                estimate_data.append({'Building':'ALL','Item':'Installation','Material':'','Dimensions':'','Quantity':1,'Unit_Price':install_cost,'Total':install_cost})
            if bool(project.get('include_sales_tax')) and project.get('sales_tax_rate'):
                taxable_total = sum(r['Total'] for r in estimate_data if r['Building']!='ALL' or r['Item']=='Installation')
                tax_cost = taxable_total * float(project['sales_tax_rate'])
                estimate_data.append({'Building':'ALL','Item':'Sales Tax','Material':'','Dimensions':'','Quantity':1,'Unit_Price':tax_cost,'Total':tax_cost})
            conn.close()
        if not estimate_data:
            return dash.no_update
        # Filter to building if requested
        if building_ids:
            conn = sqlite3.connect(DATABASE_PATH)
            placeholders = ','.join(['?']*len(building_ids))
            ndf = pd.read_sql_query(f'SELECT name FROM buildings WHERE id IN ({placeholders})', conn, params=tuple(building_ids))
            conn.close()
            selected_names = set(ndf['name'].tolist())
            estimate_data = [r for r in estimate_data if r['Building'] in selected_names or r['Building']=='ALL']
            if not estimate_data:
                return dash.no_update
        df = pd.DataFrame(estimate_data)
        buffer = io.BytesIO()
        from openpyxl.drawing.image import Image as XLImage
        from tempfile import NamedTemporaryFile
        logo_path = Path('assets') / 'LSI_Logo.svg'
        try:
            import cairosvg  # optional dependency
        except Exception:
            cairosvg = None
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Estimate')
            wb = writer.book
            ws = wb['Estimate']
            # Insert branding header above table
            ws.insert_rows(1, amount=4)
            ws.merge_cells('A1:D3')
            ws['A1'] = 'Sign Estimation Project Export'
            # Safely copy font/alignment if row 5 exists
            try:
                base_font = ws['A5'].font
                base_align = ws['A5'].alignment
            except Exception:
                base_font = ws['A1'].font
                base_align = ws['A1'].alignment
            ws['A1'].font = base_font.copy(bold=True)
            ws['A1'].alignment = base_align.copy(horizontal='left', vertical='center', wrap_text=True)
            if cairosvg and logo_path.exists():
                try:
                    with NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        png_temp = tmp.name
                    cairosvg.svg2png(url=str(logo_path), write_to=png_temp, output_width=240)
                    img = XLImage(png_temp)
                    img.anchor = 'E1'
                    ws.add_image(img)
                except Exception:
                    pass
        buffer.seek(0)
        suffix = ''
        if building_ids:
            suffix = f"_buildings_{'-'.join(map(str, building_ids))}"
        return dict(content=base64.b64encode(buffer.read()).decode(), filename=f'project_{project_id}{suffix}_estimate.xlsx', type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        print(f"[export][error] {e}")
        err_buf = io.BytesIO()
        with pd.ExcelWriter(err_buf, engine='openpyxl') as writer:
            pd.DataFrame([{"Error": str(e)}]).to_excel(writer, index=False, sheet_name='Error')
        err_buf.seek(0)
        return dict(content=base64.b64encode(err_buf.read()).decode(), filename=f'project_{project_id}_export_error.xlsx', type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ------------------ Tree View Mode Switch (Cytoscape) ------------------ #
@app.callback(
    Output('project-tree-wrapper','children'),
    Input('tree-view-mode','value'),
    prevent_initial_call=True
)
def switch_tree_view(mode):
    if mode == 'cyto':
        nodes = get_project_tree_data()
        elements = []
        id_map = {n['id']: n for n in nodes}
        for n in nodes:
            # label already contains totals for project/building nodes; show sign names directly
            elements.append({'data': {'id': n['id'], 'label': n['label']}, 'classes': n['type']})
        for n in nodes:
            parent = n.get('parent')
            if parent and parent in id_map:
                elements.append({'data': {'source': parent, 'target': n['id']}})
        stylesheet = [
            {'selector': 'node','style': {'content':'data(label)','text-wrap':'wrap','text-max-width':120,'text-valign':'center','color':'#fff','font-size':'9px','background-color':'#4a90e2','padding':'4px'}},
            {'selector': '.project','style': {'background-color':'#1f77b4','font-size':'11px','font-weight':'bold'}},
            {'selector': '.building','style': {'background-color':'#ff7f0e'}},
            {'selector': '.sign','style': {'background-color':'#2ca02c'}},
            {'selector': 'edge','style': {'width':2,'line-color':'#ccc','curve-style':'bezier'}}
        ]
        return cyto.Cytoscape(
            id='project-tree-cyto',
            elements=elements,
            layout={'name':'breadthfirst','directed':True,'spacingFactor':1.25,'padding':15},
            style={'width':'100%','height':'600px'},
            stylesheet=stylesheet
        )
    return dcc.Graph(id='project-tree', figure=safe_tree_figure())

# Initial tree population when app loads / Projects tab first shown
@app.callback(
    Output('project-tree','figure'),
    Input('main-tabs','active_tab')
)
def init_tree(active_tab):
    if active_tab == 'projects-tab':
        return safe_tree_figure()
    raise PreventUpdate

# Project deletion callback
@app.callback(
    Output('projects-list','children', allow_duplicate=True),
    Output('project-create-feedback','children', allow_duplicate=True),
    Output('project-tree','figure', allow_duplicate=True),
    Output('assign-project-dropdown','options', allow_duplicate=True),
    Output('project-edit-dropdown','options', allow_duplicate=True),
    Output('projects-debug-list','children', allow_duplicate=True),
    Input('delete-project-confirm','submit_n_clicks'),
    State('project-edit-dropdown','value'),
    prevent_initial_call=True
)
def delete_project(confirm_clicks, project_id):
    if not confirm_clicks:
        raise PreventUpdate
    if not project_id:
        return (dash.no_update,
                dbc.Alert('Select a project to delete', color='warning'),
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        print(f"[delete_project] Deleting project id={project_id}")
        cur.execute('DELETE FROM building_sign_groups WHERE building_id IN (SELECT id FROM buildings WHERE project_id=?)', (project_id,))
        cur.execute('DELETE FROM building_signs WHERE building_id IN (SELECT id FROM buildings WHERE project_id=?)', (project_id,))
        cur.execute('DELETE FROM buildings WHERE project_id=?', (project_id,))
        cur.execute('DELETE FROM projects WHERE id=?', (project_id,))
        conn.commit()
        df = pd.read_sql_query('SELECT id, name, created_date FROM projects ORDER BY id DESC', conn)
        conn.close()
        if df.empty:
            list_children = html.Div('No projects yet.')
            options = []
        else:
            rows = [html.Li(f"{r.name} (ID {r.id}) - {r.created_date}") for r in df.itertuples()]
            list_children = html.Ul(rows, className='mb-0')
            options = [{'label': r.name, 'value': r.id} for r in df.itertuples()]
        debug_txt = ' | '.join(f"{r.id}:{r.name}" for r in df.itertuples()) if not df.empty else 'none'
        return (list_children,
                dbc.Alert('Project deleted', color='info'),
                safe_tree_figure(),
                options,
                options,
                debug_txt)
    except Exception as e:
        return (dash.no_update,
                dbc.Alert(f'Error deleting: {e}', color='danger'),
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update)

# Show delete confirmation dialog
@app.callback(
    Output('delete-project-confirm','displayed'),
    Output('project-create-feedback','children', allow_duplicate=True),
    Input('delete-project-btn','n_clicks'),
    State('project-edit-dropdown','value'),
    prevent_initial_call=True
)
def show_delete_confirm(n_clicks, project_id):
    if not n_clicks:
        raise PreventUpdate
    if not project_id:
        return False, dbc.Alert('Select a project to delete first', color='warning')
    return True, dash.no_update

# Dynamic disabling of install parameter inputs + hint text
@app.callback(
    Output('install-percent-input','disabled'),
    Output('install-per-sign-rate','disabled'),
    Output('install-per-area-rate','disabled'),
    Output('install-hours-input','disabled'),
    Output('install-hourly-rate-input','disabled'),
    Output('install-mode-hint','children'),
    Input('install-mode','value')
)
def update_install_inputs(mode):
    if not mode:
        raise PreventUpdate
    percent_dis = mode != 'percent'
    per_sign_dis = mode != 'per_sign'
    per_area_dis = mode != 'per_area'
    hours_hours_dis = mode != 'hours'
    hours_rate_dis = mode != 'hours'
    hints = {
        'percent': 'Percent: Uses % of subtotal for installation.',
        'per_sign': 'Per Sign: Uses Install $/Sign * total signs (auto if enabled when blank).',
        'per_area': 'Per Area: Install $/SqFt * total sign area.',
        'hours': 'Hours: (Hours or auto sum) * $/Hour.',
        'none': 'None: No installation cost added.'
    }
    return percent_dis, per_sign_dis, per_area_dis, hours_hours_dis, hours_rate_dis, hints.get(mode,'')

# ------------------ Sign Types Table CRUD ------------------ #
@app.callback(
    Output('signs-table', 'data'),
    Output('signs-save-status', 'children'),
    Input('main-tabs', 'active_tab'),
    Input('signs-table', 'data_timestamp'),
    Input('add-sign-btn', 'n_clicks'),
    State('signs-table', 'data')
)
def manage_sign_types(active_tab, data_ts, add_clicks, data_rows):
    triggered = [t['prop_id'].split('.')[0] for t in callback_context.triggered] if callback_context.triggered else []
    if 'main-tabs' in triggered and active_tab == 'signs-tab':
        conn = sqlite3.connect(DATABASE_PATH)
        df = pd.read_sql_query(
            "SELECT name, description, material_alt, unit_price, material, price_per_sq_ft, material_multiplier, width, height, install_type, install_time_hours, per_sign_install_rate FROM sign_types ORDER BY name",
            conn
        )
        conn.close()
        return df.to_dict('records'), ''
    if 'add-sign-btn' in triggered:
        rows = data_rows or []
        rows.append({"name":"","description":"","unit_price":0,"material":"","price_per_sq_ft":0,"width":0,"height":0})
        return rows, 'New row added'
    if 'signs-table' in triggered and active_tab == 'signs-tab':
        rows = data_rows or []
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        saved = 0
        cleaned = []
        for row in rows:
            name = (row.get('name') or '').strip()
            if not name:
                continue
            def n(v):
                try: return float(v or 0)
                except: return 0.0
            # New extended columns (may not yet be in table for older deployments; ignore errors silently)
            extended_sql = '''
                INSERT INTO sign_types (name, description, material_alt, unit_price, material, price_per_sq_ft, width, height, material_multiplier, install_type, install_time_hours, per_sign_install_rate)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET description=excluded.description, material_alt=excluded.material_alt, unit_price=excluded.unit_price,
                    material=excluded.material, price_per_sq_ft=excluded.price_per_sq_ft, width=excluded.width, height=excluded.height,
                    material_multiplier=excluded.material_multiplier, install_type=excluded.install_type, install_time_hours=excluded.install_time_hours,
                    per_sign_install_rate=excluded.per_sign_install_rate
            '''
            material_alt = (row.get('material_alt') or row.get('Material2') or '')[:120]
            material_multiplier = n(row.get('material_multiplier'))
            install_type_val = (row.get('install_type') or '')[:60]
            install_time_hours = n(row.get('install_time_hours') or row.get('install_time'))
            per_sign_install_rate = n(row.get('per_sign_install_rate'))
            try:
                cur.execute(extended_sql, (
                    name,
                    (row.get('description') or '')[:255],
                    material_alt,
                    n(row.get('unit_price')),
                    (row.get('material') or '')[:120],
                    n(row.get('price_per_sq_ft')),
                    n(row.get('width')),
                    n(row.get('height')),
                    material_multiplier,
                    install_type_val,
                    install_time_hours,
                    per_sign_install_rate
                ))
            except Exception:
                # Fallback to legacy column set if migration not applied
                cur.execute('''
                    INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(name) DO UPDATE SET description=excluded.description, unit_price=excluded.unit_price,
                        material=excluded.material, price_per_sq_ft=excluded.price_per_sq_ft, width=excluded.width, height=excluded.height
                ''', (
                    name,
                    (row.get('description') or '')[:255],
                    n(row.get('unit_price')),
                    (row.get('material') or '')[:120],
                    n(row.get('price_per_sq_ft')),
                    n(row.get('width')),
                    n(row.get('height'))
                ))
            saved += 1
            cleaned.append(row)
        conn.commit(); conn.close()
        return cleaned, f'Saved {saved} rows'
    raise PreventUpdate

# Tiny debug stats updater (tab focused or after save/import) 
@app.callback(
    Output('debug-signs-stats','children'),
    Input('main-tabs','active_tab'),
    Input('signs-save-status','children'),
    Input('material-pricing-feedback','children'),
    prevent_initial_call=True
)
def update_debug_stats(active_tab, sign_save_msg, material_msg):
    if active_tab != 'signs-tab':
        raise PreventUpdate
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM sign_types')
        sign_count = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM material_pricing')
        mat_count = cur.fetchone()[0]
        cur.execute("SELECT name FROM sign_types ORDER BY last_modified DESC LIMIT 3")
        recent_signs = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT material_name FROM material_pricing ORDER BY last_updated DESC LIMIT 3")
        recent_mats = [r[0] for r in cur.fetchall()]
        conn.close()
        return f"sign_types: {sign_count} (recent: {', '.join(recent_signs) if recent_signs else 'n/a'}) | materials: {mat_count} (recent: {', '.join(recent_mats) if recent_mats else 'n/a'})"
    except Exception as e:
        return f"debug error: {e}"

# Allow closing the debug card
@app.callback(
    Output('debug-signs-card','style'),
    Input('close-debug-stats','n_clicks'),
    prevent_initial_call=True
)
def hide_debug_card(n):
    if not n:
        raise PreventUpdate
    return {'display':'none'}

# ------------------ Material Pricing CRUD & Recalc ------------------ #
@app.callback(
    Output('material-pricing-table','data'),
    Output('material-pricing-feedback','children'),
    Input('main-tabs','active_tab'),
    Input('add-material-btn','n_clicks'),
    Input('save-materials-btn','n_clicks'),
    Input('recalc-sign-prices-btn','n_clicks'),
    State('material-pricing-table','data'),
    prevent_initial_call=True
)
def manage_material_pricing(active_tab, add_clicks, save_clicks, recalc_clicks, rows):
    triggered = [t['prop_id'].split('.')[0] for t in callback_context.triggered] if callback_context.triggered else []
    if 'main-tabs' in triggered and active_tab == 'signs-tab':
        conn = sqlite3.connect(DATABASE_PATH)
        try:
            df = pd.read_sql_query("SELECT material_name, price_per_sq_ft FROM material_pricing ORDER BY material_name", conn)
        except Exception as e:
            conn.close()
            return [], dbc.Alert(f"Error loading materials: {e}", color='danger')
        conn.close()
        return df.to_dict('records'), ''
    if 'add-material-btn' in triggered:
        data = rows or []
        data.append({'material_name':'','price_per_sq_ft':0})
        return data, 'Row added'
    if 'save-materials-btn' in triggered and rows is not None:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        saved = 0
        for r in rows:
            name = (r.get('material_name') or '').strip()
            if not name:
                continue
            try:
                p = float(r.get('price_per_sq_ft') or 0)
            except:
                p = 0
            cur.execute('''
                INSERT INTO material_pricing (material_name, price_per_sq_ft)
                VALUES (?,?)
                ON CONFLICT(material_name) DO UPDATE SET price_per_sq_ft=excluded.price_per_sq_ft, last_updated=CURRENT_TIMESTAMP
            ''', (name, p))
            saved += 1
        conn.commit(); conn.close()
        return rows, f'Saved {saved} materials'
    if 'recalc-sign-prices-btn' in triggered:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.execute('''
            UPDATE sign_types
            SET unit_price = CASE 
                WHEN width>0 AND height>0 THEN (
                    width*height*COALESCE(
                        (SELECT price_per_sq_ft FROM material_pricing mp WHERE LOWER(mp.material_name)=LOWER(sign_types.material)),
                        price_per_sq_ft
                    )
                ) 
                ELSE unit_price END,
                price_per_sq_ft = COALESCE((SELECT price_per_sq_ft FROM material_pricing mp WHERE LOWER(mp.material_name)=LOWER(sign_types.material)), price_per_sq_ft),
                last_modified = CURRENT_TIMESTAMP
        ''')
        conn.commit(); conn.close()
        return rows, 'Recalculated sign prices'
    raise PreventUpdate

# ------------------ Sign Groups CRUD ------------------ #
@app.callback(
    Output('group-save-feedback','children'),
    Output('group-select-dropdown','options', allow_duplicate=True),
    Output('group-assign-group-dropdown','options', allow_duplicate=True),
    Input('save-group-btn','n_clicks'),
    State('group-name-input','value'),
    State('group-desc-input','value'),
    prevent_initial_call=True
)
def save_group(n_clicks, name, desc):
    if not n_clicks:
        raise PreventUpdate
    name = (name or '').strip()
    if not name:
        return dbc.Alert('Name required', color='danger'), dash.no_update, dash.no_update
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO sign_groups (name, description) VALUES (?,?)
            ON CONFLICT(name) DO UPDATE SET description=excluded.description
        ''', (name, (desc or '')[:255]))
        conn.commit()
        groups_df = pd.read_sql_query('SELECT id, name FROM sign_groups ORDER BY name', conn)
        conn.close()
        options = [{'label': r.name, 'value': r.id} for r in groups_df.itertuples()]
        return dbc.Alert(f"Group '{name}' saved", color='success'), options, options
    except Exception as e:
        conn.close()
        return dbc.Alert(f'Error: {e}', color='danger'), dash.no_update, dash.no_update

@app.callback(
    Output('group-members-table','data'),
    Output('group-members-feedback','children', allow_duplicate=True),
    Input('group-select-dropdown','value'),
    Input('group-add-sign-btn','n_clicks'),
    Input('group-save-members-btn','n_clicks'),
    State('group-add-sign-dropdown','value'),
    State('group-add-sign-qty','value'),
    State('group-members-table','data'),
    prevent_initial_call=True
)
def manage_group_members(group_id, add_clicks, save_clicks, sign_type_id, qty, rows):
    triggered = [t['prop_id'].split('.')[0] for t in callback_context.triggered] if callback_context.triggered else []
    if not group_id:
        raise PreventUpdate
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    feedback = dash.no_update
    if 'group-add-sign-btn' in triggered and sign_type_id:
        cur.execute('SELECT id FROM sign_group_members WHERE group_id=? AND sign_type_id=?', (group_id, sign_type_id))
        ex = cur.fetchone()
        q = max(1, int(qty or 1))
        if ex:
            cur.execute('UPDATE sign_group_members SET quantity=? WHERE id=?', (q, ex[0]))
        else:
            cur.execute('INSERT INTO sign_group_members (group_id, sign_type_id, quantity) VALUES (?,?,?)', (group_id, sign_type_id, q))
        conn.commit()
        feedback = 'Member added/updated'
    elif 'group-save-members-btn' in triggered and rows:
        for r in rows:
            name = r.get('sign_name')
            q = max(0, int(r.get('quantity') or 0))
            cur.execute('SELECT id FROM sign_types WHERE name=?', (name,))
            st = cur.fetchone()
            if not st:
                continue
            cur.execute('SELECT id FROM sign_group_members WHERE group_id=? AND sign_type_id=?', (group_id, st[0]))
            ex = cur.fetchone()
            if ex:
                cur.execute('UPDATE sign_group_members SET quantity=? WHERE id=?', (q, ex[0]))
        conn.commit()
        feedback = 'Member quantities saved'
    # Load
    df = pd.read_sql_query('''SELECT st.name as sign_name, sgm.quantity FROM sign_group_members sgm JOIN sign_types st ON sgm.sign_type_id=st.id WHERE sgm.group_id=? ORDER BY st.name''', conn, params=(group_id,))
    conn.close()
    return df.to_dict('records'), feedback

# ------------------ Assign Groups to Buildings ------------------ #
@app.callback(
    Output('group-assign-project-dropdown','options'),
    Input('main-tabs','active_tab')
)
def populate_group_project_options(active_tab):
    if active_tab != 'groups-tab':
        raise PreventUpdate
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query('SELECT id, name FROM projects ORDER BY name', conn)
    conn.close()
    return [{'label': r.name, 'value': r.id} for r in df.itertuples()]

@app.callback(
    Output('group-assign-building-dropdown','options'),
    Output('group-assign-building-dropdown','value'),
    Input('group-assign-project-dropdown','value')
)
def populate_group_buildings(project_id):
    if not project_id:
        return [], None
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query('SELECT id, name FROM buildings WHERE project_id=? ORDER BY name', conn, params=(project_id,))
    conn.close()
    opts = [{'label': r.name,'value': r.id} for r in df.itertuples()]
    return opts, (opts[0]['value'] if opts else None)

@app.callback(
    Output('building-groups-table','data'),
    Output('group-assign-feedback','children'),
    Input('group-assign-building-dropdown','value'),
    Input('group-assign-btn','n_clicks'),
    Input('building-save-group-qty-btn','n_clicks'),
    State('group-assign-group-dropdown','value'),
    State('group-assign-qty','value'),
    State('building-groups-table','data'),
    prevent_initial_call=True
)
def manage_building_groups(building_id, add_clicks, save_clicks, group_id, qty, rows):
    triggered = [t['prop_id'].split('.')[0] for t in callback_context.triggered] if callback_context.triggered else []
    if not building_id:
        raise PreventUpdate
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    feedback = dash.no_update
    if 'group-assign-btn' in triggered and group_id:
        cur.execute('SELECT id FROM building_sign_groups WHERE building_id=? AND group_id=?', (building_id, group_id))
        ex = cur.fetchone()
        q = max(1, int(qty or 1))
        if ex:
            cur.execute('UPDATE building_sign_groups SET quantity=? WHERE id=?', (q, ex[0]))
        else:
            cur.execute('INSERT INTO building_sign_groups (building_id, group_id, quantity) VALUES (?,?,?)', (building_id, group_id, q))
        conn.commit()
        feedback = 'Group assigned'
    elif 'building-save-group-qty-btn' in triggered and rows:
        for r in rows:
            name = r.get('group_name')
            q = max(0, int(r.get('quantity') or 0))
            cur.execute('SELECT id FROM sign_groups WHERE name=?', (name,))
            gr = cur.fetchone()
            if not gr: continue
            cur.execute('SELECT id FROM building_sign_groups WHERE building_id=? AND group_id=?', (building_id, gr[0]))
            ex = cur.fetchone()
            if ex:
                cur.execute('UPDATE building_sign_groups SET quantity=? WHERE id=?', (q, ex[0]))
        conn.commit(); feedback='Group quantities saved'
    df = pd.read_sql_query('''SELECT sg.name as group_name, bsg.quantity FROM building_sign_groups bsg JOIN sign_groups sg ON bsg.group_id=sg.id WHERE bsg.building_id=? ORDER BY sg.name''', conn, params=(building_id,))
    conn.close()
    return df.to_dict('records'), feedback

# ------------------ Building View Tab Callbacks ------------------ #
@app.callback(
    Output('bv-building-dropdown','options'),
    Output('bv-building-dropdown','value'),
    Input('bv-project-dropdown','value'),
    prevent_initial_call=True
)
def bv_load_buildings(project_id):
    if not project_id:
        raise PreventUpdate
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query('SELECT id, name FROM buildings WHERE project_id=? ORDER BY name', conn, params=(project_id,))
    conn.close()
    opts = [{'label': r.name, 'value': r.id} for r in df.itertuples()]
    return opts, (opts[0]['value'] if opts else None)

@app.callback(
    Output('bv-sign-type-dropdown','options'),
    Output('bv-signs-table','data'),
    Output('bv-delete-sign-dropdown','options'),
    Output('bv-delete-group-dropdown','options'),
    Output('bv-building-meta','children'),
    Output('bv-summary','children'),
    Input('bv-building-dropdown','value'),
    prevent_initial_call=True
)
def bv_load_building(building_id):
    if not building_id:
        raise PreventUpdate
    conn = sqlite3.connect(DATABASE_PATH)
    st_df = pd.read_sql_query('SELECT id, name, unit_price FROM sign_types ORDER BY name', conn)
    b_df = pd.read_sql_query('SELECT name, description FROM buildings WHERE id=?', conn, params=(building_id,))
    rows_df = pd.read_sql_query('''SELECT st.name as sign_name, bs.quantity, st.unit_price, (bs.quantity*st.unit_price) as total
                                   FROM building_signs bs JOIN sign_types st ON bs.sign_type_id=st.id
                                   WHERE bs.building_id=? ORDER BY st.name''', conn, params=(building_id,))
    grp_df = pd.read_sql_query('''SELECT sg.name, bsg.quantity FROM building_sign_groups bsg JOIN sign_groups sg ON bsg.group_id=sg.id WHERE bsg.building_id=? ORDER BY sg.name''', conn, params=(building_id,))
    conn.close()
    st_opts = [{'label': f"{r.name} (${r.unit_price})", 'value': r.id} for r in st_df.itertuples()]
    table_rows = rows_df.to_dict('records')
    del_opts = [{'label': r['sign_name'], 'value': r['sign_name']} for r in table_rows]
    group_del_opts = [{'label': r.name, 'value': r.name} for r in grp_df.itertuples()] if not grp_df.empty else []
    meta = '' if b_df.empty else f"{b_df.iloc[0]['name']} - {b_df.iloc[0].get('description','')}"
    subtotal = sum(r['total'] for r in table_rows) if table_rows else 0
    group_count = 0 if grp_df.empty else grp_df.shape[0]
    summary = f"Subtotal: ${subtotal:,.2f} | Signs: {len(table_rows)} | Groups: {group_count}"
    return st_opts, table_rows, del_opts, group_del_opts, meta, summary

@app.callback(
    Output('bv-signs-table','data', allow_duplicate=True),
    Output('bv-delete-sign-dropdown','options', allow_duplicate=True),
    Output('bv-delete-group-dropdown','options', allow_duplicate=True),
    Output('bv-summary','children', allow_duplicate=True),
    Output('bv-feedback','children', allow_duplicate=True),
    Input('bv-add-sign-btn','n_clicks'),
    Input('bv-save-signs-btn','n_clicks'),
    Input('bv-delete-sign-btn','n_clicks'),
    Input('bv-delete-group-btn','n_clicks'),
    State('bv-building-dropdown','value'),
    State('bv-sign-type-dropdown','value'),
    State('bv-sign-qty-input','value'),
    State('bv-delete-sign-dropdown','value'),
    State('bv-delete-group-dropdown','value'),
    State('bv-signs-table','data'),
    prevent_initial_call=True
)
def bv_manage_signs(add_clicks, save_clicks, delete_clicks, delete_group_clicks, building_id, sign_type_id, qty, delete_name, delete_group_name, current_rows):
    triggered = [t['prop_id'].split('.')[0] for t in callback_context.triggered] if callback_context.triggered else []
    if not building_id:
        raise PreventUpdate
    msg = dash.no_update
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    if 'bv-add-sign-btn' in triggered and sign_type_id:
        q = max(1, int(qty or 1))
        cur.execute('SELECT id, quantity FROM building_signs WHERE building_id=? AND sign_type_id=?', (building_id, sign_type_id))
        ex = cur.fetchone()
        if ex:
            cur.execute('UPDATE building_signs SET quantity=? WHERE id=?', (q, ex[0]))
        else:
            cur.execute('INSERT INTO building_signs (building_id, sign_type_id, quantity) VALUES (?,?,?)', (building_id, sign_type_id, q))
        msg = 'Sign added/updated'
    elif 'bv-save-signs-btn' in triggered and current_rows:
        for r in current_rows:
            name = r.get('sign_name')
            q = max(0, int(r.get('quantity') or 0))
            cur.execute('SELECT id FROM sign_types WHERE name=?', (name,))
            st = cur.fetchone()
            if not st: continue
            cur.execute('SELECT id FROM building_signs WHERE building_id=? AND sign_type_id=?', (building_id, st[0]))
            ex = cur.fetchone()
            if ex:
                cur.execute('UPDATE building_signs SET quantity=? WHERE id=?', (q, ex[0]))
        msg = 'Quantities saved'
    elif 'bv-delete-sign-btn' in triggered and delete_name:
        cur.execute('SELECT id FROM sign_types WHERE name=?', (delete_name,))
        st = cur.fetchone()
        if st:
            cur.execute('DELETE FROM building_signs WHERE building_id=? AND sign_type_id=?', (building_id, st[0]))
            msg = 'Sign removed'
    elif 'bv-delete-group-btn' in triggered and delete_group_name:
        # Remove group assignment
        cur.execute('SELECT id FROM sign_groups WHERE name=?', (delete_group_name,))
        g = cur.fetchone()
        if g:
            cur.execute('DELETE FROM building_sign_groups WHERE building_id=? AND group_id=?', (building_id, g[0]))
            msg = 'Group removed'
    if msg is not dash.no_update:
        conn.commit()
    # Reload
    rows_df = pd.read_sql_query('''SELECT st.name as sign_name, bs.quantity, st.unit_price, (bs.quantity*st.unit_price) as total
                                   FROM building_signs bs JOIN sign_types st ON bs.sign_type_id=st.id
                                   WHERE bs.building_id=? ORDER BY st.name''', conn, params=(building_id,))
    grp_df = pd.read_sql_query('''SELECT sg.name, bsg.quantity FROM building_sign_groups bsg JOIN sign_groups sg ON bsg.group_id=sg.id WHERE bsg.building_id=? ORDER BY sg.name''', conn, params=(building_id,))
    conn.close()
    table_rows = rows_df.to_dict('records')
    del_opts = [{'label': r['sign_name'], 'value': r['sign_name']} for r in table_rows]
    group_del_opts = [{'label': r.name, 'value': r.name} for r in grp_df.itertuples()] if not grp_df.empty else []
    subtotal = sum(r['total'] for r in table_rows) if table_rows else 0
    summary = f"Subtotal: ${subtotal:,.2f} | Signs: {len(table_rows)} | Groups: {0 if grp_df.empty else grp_df.shape[0]}"
    return table_rows, del_opts, group_del_opts, summary, msg

@app.callback(
    Output('bv-building-dropdown','options', allow_duplicate=True),
    Output('bv-building-dropdown','value', allow_duplicate=True),
    Output('bv-building-meta','children', allow_duplicate=True),
    Input('bv-rename-building-btn','n_clicks'),
    State('bv-project-dropdown','value'),
    State('bv-building-dropdown','value'),
    State('bv-rename-building-input','value'),
    prevent_initial_call=True
)
def bv_rename_building(n_clicks, project_id, building_id, new_name):
    if not n_clicks:
        raise PreventUpdate
    if not (project_id and building_id and new_name and new_name.strip()):
        raise PreventUpdate
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM buildings WHERE project_id=? AND LOWER(name)=LOWER(?) AND id<>?', (project_id, new_name.strip(), building_id))
    if cur.fetchone():
        conn.close()
        raise PreventUpdate
    cur.execute('UPDATE buildings SET name=?, last_modified=CURRENT_TIMESTAMP WHERE id=?', (new_name.strip(), building_id))
    conn.commit()
    bdf = pd.read_sql_query('SELECT id, name, description FROM buildings WHERE project_id=? ORDER BY name', conn, params=(project_id,))
    conn.close()
    opts = [{'label': r.name, 'value': r.id} for r in bdf.itertuples()]
    meta = ''
    for r in bdf.itertuples():
        if r.id == building_id:
            meta = f"{r.name} - {getattr(r,'description','')}"
            break
    return opts, building_id, meta

# ------------------ Health Endpoint ------------------ #
@app.server.route('/health')
def health():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute('SELECT 1')
        conn.close()
        return {"status": "ok", "db": "reachable"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}, 500

# ------------------ Port Selection Helper ------------------ #
def find_free_port(preferred: int) -> int:
    port = preferred
    for _ in range(15):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                port += 1
    return preferred  # fallback

if __name__ == "__main__":
    ensure_backup_dir()
    preferred = APP_PORT
    free_port = find_free_port(preferred)
    if free_port != preferred:
        print(f"[startup] Port {preferred} in use, switching to {free_port}")
    print("[startup] Starting Dash server ...")
    print(f"[startup] Database path: {DATABASE_PATH}")
    print(f"[startup] Open browser at: http://{APP_HOST}:{free_port}")
    if AUTO_BACKUP_INTERVAL_SEC > 0:
        print(f"[startup] Auto backup every {AUTO_BACKUP_INTERVAL_SEC}s -> {BACKUP_DIR}")
        import threading, time, shutil
        def _auto_backup_loop():
            while True:
                try:
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    target = BACKUP_DIR / f'sign_estimation_{ts}.db'
                    shutil.copy2(DATABASE_PATH, target)
                except Exception as e:
                    print(f"[backup][warn] {e}")
                time.sleep(AUTO_BACKUP_INTERVAL_SEC)
        threading.Thread(target=_auto_backup_loop, daemon=True).start()
    app.run(debug=DASH_DEBUG, port=free_port, host=APP_HOST, use_reloader=False)
