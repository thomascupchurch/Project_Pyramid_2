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
    # Compute price_per_sq_ft if absent but width/height/unit_price present
    calc_mask = (norm_df['price_per_sq_ft']==0) & (norm_df['width']>0) & (norm_df['height']>0) & (norm_df['unit_price']>0)
    norm_df.loc[calc_mask,'price_per_sq_ft'] = norm_df.loc[calc_mask].apply(lambda r: (r['unit_price'] / (r['width']*r['height'])) if r['width']*r['height'] else 0, axis=1)
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
                    dcc.Graph(
                        id="project-tree",
                        figure=create_tree_visualization()
                    )
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
                        dbc.Button("Create Project", id="create-project-btn", color="primary", className="w-100")
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
            ])
        ])
    ])

def render_groups_tab():
    """Render the sign groups management tab."""
    return dbc.Row([
        dbc.Col([
            html.H4("Sign Groups Management"),
            html.P("Create and manage sign groups here.")
        ])
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
    if not name:
        return dash.no_update, dbc.Alert("Project name required", color='danger'), dash.no_update, dash.no_update
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
        return list_children, feedback, tree_fig, project_options
    except sqlite3.IntegrityError:
        return dash.no_update, dbc.Alert(f"Project '{name}' already exists", color='warning'), dash.no_update, dash.no_update
    except Exception as e:
        return dash.no_update, dbc.Alert(f"Error: {e}", color='danger'), dash.no_update, dash.no_update

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
        qty = int(qty or 1)
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
            q = int(row.get('quantity') or 0)
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
    estimate_data = db_manager.get_project_estimate(project_id) or []
    if not estimate_data:
        return dash.no_update
    df = pd.DataFrame(estimate_data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Estimate')
    buffer.seek(0)
    return dict(content=base64.b64encode(buffer.read()).decode(), filename=f'project_{project_id}_estimate.xlsx', type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

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
        df = pd.read_sql_query("SELECT name, description, unit_price, material, price_per_sq_ft, width, height FROM sign_types ORDER BY name", conn)
        conn.close()
        return df.to_dict('records'), "Loaded"
    # Add a blank row
    if 'add-sign-btn' in triggered:
        rows = data_rows or []
        rows.append({"name": "", "description": "", "unit_price": 0, "material": "", "price_per_sq_ft": 0, "width": 0, "height": 0})
        return rows, "Row added"
    # Persist edits
    if 'signs-table' in triggered and active_tab == 'signs-tab':
        rows = data_rows or []
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        saved = 0
        for row in rows:
            name = (row.get('name') or '').strip()
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
                row.get('description') or '',
                float(row.get('unit_price') or 0),
                row.get('material') or '',
                float(row.get('price_per_sq_ft') or 0),
                float(row.get('width') or 0),
                float(row.get('height') or 0)
            ))
            saved += 1
        conn.commit()
        conn.close()
        return rows, f"Saved {saved}" if saved else "No changes"
    raise PreventUpdate

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
