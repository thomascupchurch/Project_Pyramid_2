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

# Import custom utilities
try:
    from database import DatabaseManager
    from calculations import CostCalculator
    from onedrive import OneDriveManager
except ImportError as e:
    print(f"Warning: Could not import utilities: {e}")
    # Create fallback classes
    class DatabaseManager:
        def __init__(self, db_path):
            self.db_path = db_path
        def init_database(self):
            pass
        def get_project_estimate(self, project_id):
            return []
    class CostCalculator:
        def __init__(self, db_path): pass
    class OneDriveManager:
        def __init__(self, local_path): pass

# Initialize Dash app
print("[startup] Import phase complete. Initializing Dash app...", flush=True)
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
app.title = "Sign Estimation Tool"

DATABASE_PATH = os.getenv("SIGN_APP_DB", "sign_estimation.db")
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

print("[startup] Ensuring database schema...", flush=True)
try:
    db_manager.init_database()
    print("[startup] Schema ensured.", flush=True)
except Exception as e:
    print(f"[startup][error] init_database failed: {e}", flush=True)
    raise

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
    """Generate tree visualization data for projects, buildings, and signs."""
    conn = sqlite3.connect(DATABASE_PATH)
    
    # Get projects
    projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
    
    nodes = []
    edges = []
    
    for _, project in projects_df.iterrows():
        # Add project node
        project_node = {
            'id': f"project_{project['id']}",
            'label': project['name'],
            'type': 'project',
            'level': 0
        }
        nodes.append(project_node)
        
        # Get buildings for this project
        buildings_df = pd.read_sql_query(
            "SELECT * FROM buildings WHERE project_id = ?", 
            conn, params=(project['id'],)
        )
        
        for _, building in buildings_df.iterrows():
            # Add building node
            building_node = {
                'id': f"building_{building['id']}",
                'label': building['name'],
                'type': 'building',
                'level': 1,
                'parent': f"project_{project['id']}"
            }
            nodes.append(building_node)
            
            # Get signs for this building
            signs_df = pd.read_sql_query('''
                SELECT st.name, bs.quantity 
                FROM building_signs bs
                JOIN sign_types st ON bs.sign_type_id = st.id
                WHERE bs.building_id = ?
            ''', conn, params=(building['id'],))
            
            for _, sign in signs_df.iterrows():
                sign_node = {
                    'id': f"sign_{building['id']}_{sign['name']}",
                    'label': f"{sign['name']} ({sign['quantity']})",
                    'type': 'sign',
                    'level': 2,
                    'parent': f"building_{building['id']}"
                }
                nodes.append(sign_node)
    
    conn.close()
    return nodes

def create_tree_visualization():
    """Create Plotly tree visualization."""
    nodes = get_project_tree_data()
    
    if not nodes:
        return go.Figure()
    
    fig = go.Figure()
    
    # Color mapping for different node types
    colors = {
        'project': '#1f77b4',
        'building': '#ff7f0e', 
        'sign': '#2ca02c'
    }
    
    # Position nodes in a tree layout
    level_x = {0: [], 1: [], 2: []}
    level_y = {0: [], 1: [], 2: []}
    
    for i, node in enumerate(nodes):
        level = node['level']
        level_x[level].append(level * 300)
        level_y[level].append(i * 50)
    
    for level in [0, 1, 2]:
        if level_x[level]:
            fig.add_trace(go.Scatter(
                x=level_x[level],
                y=level_y[level],
                mode='markers+text',
                marker=dict(size=15, color=colors.get(nodes[0]['type'], '#1f77b4')),
                text=[node['label'] for node in nodes if node['level'] == level],
                textposition="middle right",
                name=f"Level {level}"
            ))
    
    fig.update_layout(
        title="Project Tree Visualization",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=600,
        showlegend=False
    )
    
    return fig

# Database already initialized above

# App layout
app.layout = dbc.Container([
    # Header with logo
    dbc.Row([
        dbc.Col([
            html.Div([
                html.Img(src="/assets/LSI_Logo.svg", height="60px", className="me-3"),
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
                dbc.Tab(label="Estimates", tab_id="estimates-tab"),
                dbc.Tab(label="Import Data", tab_id="import-tab")
            ], id="main-tabs", active_tab="projects-tab")
        ])
    ], className="mb-4"),
    
    # Main content area
    dcc.Store(id='app-state', data={}),
    html.Div(id="tab-content")
    
], fluid=True)

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
                    html.Div(id='project-tree-wrapper', children=dcc.Graph(id='project-tree', figure=create_tree_visualization()))
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
                    html.Div(id='save-building-signs-feedback', className='mt-2')
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
                            dbc.Col(dcc.Dropdown(id='project-edit-dropdown', placeholder='Select project to edit'), width=8)
                        ], className="mb-3"),
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
                    ])
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
                            {"name": "Unit Price", "id": "unit_price", "type": "numeric", "editable": True},
                            {"name": "Material", "id": "material", "editable": True},
                            {"name": "Price/Sq Ft", "id": "price_per_sq_ft", "type": "numeric", "editable": True},
                            {"name": "Width", "id": "width", "type": "numeric", "editable": True},
                            {"name": "Height", "id": "height", "type": "numeric", "editable": True}
                        ],
                        data=[],
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
                        data=[], editable=True, row_deletable=True, page_size=8, style_table={'overflowX':'auto'}
                    ),
                    dbc.Button('Add Material', id='add-material-btn', color='secondary', className='mt-2 me-2'),
                    dbc.Button('Save Materials', id='save-materials-btn', color='primary', className='mt-2 me-2'),
                    dbc.Button('Recalculate Sign Prices', id='recalc-sign-prices-btn', color='warning', className='mt-2'),
                    html.Div(id='material-pricing-feedback', className='mt-2')
                ])
            ], className='mt-3')
        ])
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
                        data=[], editable=True, row_deletable=False, page_size=8, className='mt-2'
                    ),
                    dbc.Button('Save Group Quantities', id='building-save-group-qty-btn', color='primary', className='mt-2'),
                    html.Div(id='building-group-save-feedback', className='mt-2')
                ])
            ])
        ], width=6)
    ])

def render_estimates_tab():
    """Render the cost estimation and export tab."""
    # Populate project options fresh on each render
    conn = sqlite3.connect(DATABASE_PATH)
    df = pd.read_sql_query("SELECT id, name FROM projects ORDER BY name", conn)
    conn.close()
    project_options = [{"label": r.name, "value": r.id} for r in df.itertuples()] if not df.empty else []
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
                            dbc.Button("Generate Estimate", id='generate-estimate-btn', color='primary', className='mt-4 w-100')
                        ], md=3),
                        dbc.Col([
                            dbc.Button("Export to Excel", id='export-estimate-btn', color='success', className='mt-4 w-100', disabled=True)
                        ], md=3),
                        dbc.Col([
                            dcc.Download(id='estimate-download')
                        ], md=2)
                    ], className='mb-3 g-2'),
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
                    html.Div(id='upload-output')
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

# ------------------ Project Creation & Listing ------------------ #
@app.callback(
    Output('projects-list', 'children'),
    Output('project-create-feedback', 'children'),
    Output('project-tree', 'figure', allow_duplicate=True),
    Output('assign-project-dropdown', 'options'),
    Output('project-edit-dropdown', 'options'),
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
            dash.no_update,
            dbc.Alert("Project name required", color='danger'),
            dash.no_update,
            dash.no_update,
            dash.no_update,
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
        tree_fig = create_tree_visualization()
        feedback = dbc.Alert(f"Project '{name}' created", color='success', dismissable=True)
        return list_children, feedback, tree_fig, project_options, project_options
    except sqlite3.IntegrityError:
        return dash.no_update, dbc.Alert(f"Project '{name}' already exists", color='warning'), dash.no_update, dash.no_update, dash.no_update
    except Exception as e:
        return dash.no_update, dbc.Alert(f"Error: {e}", color='danger'), dash.no_update, dash.no_update, dash.no_update

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
    return dbc.Alert('Project updated', color='success'), create_tree_visualization()

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
    tree_fig = create_tree_visualization()
    return options, f"Building '{name}' added", tree_fig

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
    tree_fig = create_tree_visualization()
    return data, action_msg, tree_fig

# ------------------ Estimate Generation & Export ------------------ #
@app.callback(
    Output('estimate-table', 'data'),
    Output('estimate-summary', 'children'),
    Output('export-estimate-btn', 'disabled'),
    Input('generate-estimate-btn', 'n_clicks'),
    State('estimate-project-dropdown', 'value'),
    prevent_initial_call=True
)
def generate_estimate(n_clicks, project_id):
    if not n_clicks:
        raise PreventUpdate
    if not project_id:
        return [], "Select project", True
    estimate_data = db_manager.get_project_estimate(project_id) or []
    if not estimate_data:
        return [], "No data for project", True
    df = pd.DataFrame(estimate_data)
    total = df['Total'].sum() if 'Total' in df else 0
    summary = dbc.Alert(f"Total Estimate: ${total:,.2f}", color='info')
    return df.to_dict('records'), summary, False

@app.callback(
    Output('estimate-download', 'data'),
    Input('export-estimate-btn', 'n_clicks'),
    State('estimate-project-dropdown', 'value'),
    prevent_initial_call=True
)
def export_estimate(n_clicks, project_id):
    if not n_clicks:
        raise PreventUpdate
    if not project_id:
        return dash.no_update
    try:
        estimate_data = db_manager.get_project_estimate(project_id) or []
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
        return dict(content=base64.b64encode(buffer.read()).decode(), filename=f'project_{project_id}_estimate.xlsx', type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
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
        # Build Cytoscape elements
        elements = []
        id_map = {}
        for n in nodes:
            elements.append({'data': {'id': n['id'], 'label': n['label']}, 'classes': n['type']})
            id_map[n['id']] = n
        # Add edges based on parent field
        for n in nodes:
            parent = n.get('parent')
            if parent and parent in id_map:
                elements.append({'data': {'source': parent, 'target': n['id']}})
        stylesheet = [
            {'selector': 'node','style': {'content':'data(label)','text-valign':'center','color':'#fff','font-size':'10px','background-color':'#4a90e2'}},
            {'selector': '.project','style': {'background-color':'#1f77b4'}},
            {'selector': '.building','style': {'background-color':'#ff7f0e'}},
            {'selector': '.sign','style': {'background-color':'#2ca02c'}},
            {'selector': 'edge','style': {'width':2,'line-color':'#ccc'}}
        ]
        return cyto.Cytoscape(id='project-tree-cyto', elements=elements, layout={'name':'breadthfirst','directed':True,'spacingFactor':1.2}, style={'width':'100%','height':'600px'}, stylesheet=stylesheet)
    return dcc.Graph(id='project-tree', figure=create_tree_visualization())

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
    # Load on tab switch
    if 'main-tabs' in triggered and active_tab == 'signs-tab':
        conn = sqlite3.connect(DATABASE_PATH)
        df = pd.read_sql_query("SELECT name, description, unit_price, material, price_per_sq_ft, width, height FROM sign_types ORDER BY name", conn)
        conn.close()
        return df.to_dict('records'), ''
    # Add row
    if 'add-sign-btn' in triggered:
        rows = data_rows or []
        rows.append({"name": "", "description": "", "unit_price": 0, "material": "", "price_per_sq_ft": 0, "width": 0, "height": 0})
        return rows, 'New row added'
    # Persist edits (data_timestamp fires after user edits) -> identify via 'signs-table'
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
    # Allow overriding port via env var SIGN_APP_PORT
    preferred = int(os.getenv("SIGN_APP_PORT", "8050"))
    free_port = find_free_port(preferred)
    if free_port != preferred:
        print(f"Port {preferred} in use, switching to {free_port}")
    print("Starting Dash server...")
    print(f"Database path: {DATABASE_PATH}")
    print(f"Open browser at: http://127.0.0.1:{free_port}")
    # Disable reloader to avoid silent double-fork confusion
    app.run(debug=True, port=free_port, use_reloader=False)
