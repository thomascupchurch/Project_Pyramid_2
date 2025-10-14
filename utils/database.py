"""Database utilities for the Sign Estimation Application.

Now supports pluggable backends (initially SQLite + experimental MSSQL).

Design notes:
 - The original implementation was tightly coupled to SQLite (PRAGMAs, ON CONFLICT
     clauses, AUTOINCREMENT, etc.). To enable migration toward SQL Server without
     immediately refactoring every call site, we keep the full original class body
     (renamed to ``SQLiteDatabaseManager``) and introduce a lightweight
     ``MssqlDatabaseManager`` implementing only the core subset of behaviors used
     by primary app features (project + sign structures, import, estimate, pricing
     recalculation, image association, and audit logging).
 - A runtime alias ``DatabaseManager`` is exported that resolves to the proper
     concrete class based on environment variable SIGN_APP_DB_BACKEND (see config).
 - Advanced/less‑critical feature methods raise ``NotImplementedError`` for the
     MSSQL backend until incrementally ported. This allows staged adoption while
     keeping SQLite as the default fully‑featured backend.

IMPORTANT: The MSSQL path is intentionally conservative and avoids vendor‑
specific advanced SQL. Schema creation sticks to NVARCHAR(MAX)/FLOAT/INT/BIT
and DATETIME2. JSON columns are stored as NVARCHAR(MAX). Future enhancements
may leverage native JSON (if migrating to Azure SQL edge cases) or computed
columns.
"""

import sqlite3
import pandas as pd
import json
import os
from datetime import datetime
import shutil
from pathlib import Path

try:  # optional dependency only when MSSQL backend selected
    import pyodbc  # noqa: F401
except Exception:  # pragma: no cover
    pyodbc = None  # type: ignore

from config import DB_BACKEND, MSSQL_CONN_STRING, DATABASE_PATH


class SQLiteDatabaseManager:
    def __init__(self, db_path="sign_estimation.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        statements = [
            '''CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_date DATE DEFAULT CURRENT_DATE,
                sales_tax_rate REAL DEFAULT 0.0,
                installation_rate REAL DEFAULT 0.0,
                include_installation BOOLEAN DEFAULT 1,
                include_sales_tax BOOLEAN DEFAULT 1,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS buildings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE)''',
            '''CREATE UNIQUE INDEX IF NOT EXISTS idx_buildings_project_name ON buildings(project_id, name COLLATE NOCASE)''',
            '''CREATE TABLE IF NOT EXISTS sign_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                material_alt TEXT,
                unit_price REAL DEFAULT 0.0,
                material TEXT,
                price_per_sq_ft REAL DEFAULT 0.0,
                width REAL DEFAULT 0.0,
                height REAL DEFAULT 0.0,
                material_multiplier REAL DEFAULT 0.0,
                install_type TEXT,
                install_time_hours REAL DEFAULT 0.0,
                per_sign_install_rate REAL DEFAULT 0.0,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS sign_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''',
            '''CREATE TABLE IF NOT EXISTS sign_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                sign_type_id INTEGER,
                quantity INTEGER DEFAULT 1,
                FOREIGN KEY (group_id) REFERENCES sign_groups (id) ON DELETE CASCADE,
                FOREIGN KEY (sign_type_id) REFERENCES sign_types (id) ON DELETE CASCADE)''',
            '''CREATE TABLE IF NOT EXISTS building_signs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building_id INTEGER,
                sign_type_id INTEGER,
                quantity INTEGER DEFAULT 1,
                custom_price REAL,
                FOREIGN KEY (building_id) REFERENCES buildings (id) ON DELETE CASCADE,
                FOREIGN KEY (sign_type_id) REFERENCES sign_types (id) ON DELETE CASCADE)''',
            '''CREATE TABLE IF NOT EXISTS building_sign_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building_id INTEGER,
                group_id INTEGER,
                quantity INTEGER DEFAULT 1,
                FOREIGN KEY (building_id) REFERENCES buildings (id) ON DELETE CASCADE,
                FOREIGN KEY (group_id) REFERENCES sign_groups (id) ON DELETE CASCADE)''',
            '''CREATE TABLE IF NOT EXISTS material_pricing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_name TEXT NOT NULL UNIQUE,
                price_per_sq_ft REAL NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''
        ]
        for stmt in statements:
            cursor.execute(stmt)
        # Lightweight migrations: add new columns if they don't exist
        existing_cols = set()
        try:
            cursor.execute('PRAGMA table_info(sign_types)')
            for row in cursor.fetchall():
                existing_cols.add(row[1])
        except Exception:
            pass
        migrations = [
            ('material_alt','ALTER TABLE sign_types ADD COLUMN material_alt TEXT'),
            ('material_multiplier','ALTER TABLE sign_types ADD COLUMN material_multiplier REAL DEFAULT 0.0'),
            ('install_type','ALTER TABLE sign_types ADD COLUMN install_type TEXT'),
            ('install_time_hours','ALTER TABLE sign_types ADD COLUMN install_time_hours REAL DEFAULT 0.0'),
            ('per_sign_install_rate','ALTER TABLE sign_types ADD COLUMN per_sign_install_rate REAL DEFAULT 0.0'),
            ('image_path','ALTER TABLE sign_types ADD COLUMN image_path TEXT')
        ]
        for col, sql in migrations:
            if col not in existing_cols:
                try:
                    cursor.execute(sql)
                except Exception:
                    pass
        # Create multi-image table if not exists
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS sign_type_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sign_type_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                display_order INTEGER DEFAULT 0,
                file_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sign_type_id) REFERENCES sign_types(id) ON DELETE CASCADE
            )''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sign_type_images_sign_type ON sign_type_images(sign_type_id, display_order)')
        except Exception:
            pass

        # New feature tables (category one)
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('admin','estimator','sales','viewer')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
        except Exception:
            pass
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_id INTEGER,
                meta JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id)')
        except Exception:
            pass
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS estimate_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                label TEXT,
                snapshot_hash TEXT,
                data JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_project ON estimate_snapshots(project_id, created_at)')
        except Exception:
            pass
        # Pricing profiles (assignable to projects)
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS pricing_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sales_tax_rate REAL DEFAULT 0.0,
                installation_rate REAL DEFAULT 0.0,
                margin_multiplier REAL DEFAULT 1.0,
                is_default BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
        except Exception:
            pass
        # Add profile_id to projects if missing
        try:
            cursor.execute('PRAGMA table_info(projects)')
            proj_cols = [r[1] for r in cursor.fetchall()]
            if 'pricing_profile_id' not in proj_cols:
                cursor.execute('ALTER TABLE projects ADD COLUMN pricing_profile_id INTEGER REFERENCES pricing_profiles(id)')
        except Exception:
            pass
        # Tagging
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS sign_type_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS sign_type_tag_map (
                sign_type_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (sign_type_id, tag_id),
                FOREIGN KEY (sign_type_id) REFERENCES sign_types(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES sign_type_tags(id) ON DELETE CASCADE
            )''')
        except Exception:
            pass
        # Notes (generic entity notes)
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL, -- e.g. 'building','sign_type','project'
                entity_id INTEGER NOT NULL,
                note TEXT NOT NULL,
                include_in_export BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_id)')
        except Exception:
            pass
        # Bid templates
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS bid_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS bid_template_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                sign_type_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                FOREIGN KEY (template_id) REFERENCES bid_templates(id) ON DELETE CASCADE,
                FOREIGN KEY (sign_type_id) REFERENCES sign_types(id) ON DELETE CASCADE
            )''')
        except Exception:
            pass

        # Backfill: if sign_types.image_path present but no corresponding row in sign_type_images, insert it
        try:
            cursor.execute('''SELECT id, image_path FROM sign_types WHERE image_path IS NOT NULL AND TRIM(image_path) <> '' ''')
            rows = cursor.fetchall()
            for sid, ipath in rows:
                # Does a row already exist?
                cursor.execute('SELECT 1 FROM sign_type_images WHERE sign_type_id=? AND image_path=?', (sid, ipath))
                if cursor.fetchone():
                    continue
                cursor.execute('INSERT INTO sign_type_images (sign_type_id, image_path, display_order) VALUES (?,?,0)', (sid, ipath))
        except Exception:
            pass
        conn.commit(); conn.close()
    
    def import_csv_data(self, csv_file_path, table_mapping=None):
        """
        Import data from CSV file into the database.
        
        Args:
            csv_file_path: Path to the CSV file
            table_mapping: Dictionary mapping CSV columns to database fields
        """
        try:
            df = pd.read_csv(csv_file_path)
            conn = sqlite3.connect(self.db_path)
            
            # Default mapping if none provided
            if table_mapping is None:
                table_mapping = {
                    'name': 'name',
                    'description': 'description', 
                    'price': 'unit_price',
                    'material': 'material',
                    'width': 'width',
                    'height': 'height'
                }
            
            # Process CSV data and populate sign_types table
            for _, row in df.iterrows():
                cursor = conn.cursor()
                
                # Calculate price per sq ft if dimensions are provided
                price_per_sq_ft = 0.0
                width = row.get('width', 0) or row.get('Width', 0)
                height = row.get('height', 0) or row.get('Height', 0)
                unit_price = row.get('price', 0) or row.get('Price', 0) or row.get('unit_price', 0)
                
                if width and height and unit_price:
                    area = float(width) * float(height)
                    if area > 0:
                        price_per_sq_ft = float(unit_price) / area
                
                cursor.execute('''
                    INSERT OR REPLACE INTO sign_types 
                    (name, description, unit_price, material, price_per_sq_ft, width, height)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    str(row.get('name', row.iloc[0] if len(row) > 0 else '')),
                    str(row.get('description', row.iloc[1] if len(row) > 1 else '')),
                    float(unit_price or 0),
                    str(row.get('material', row.iloc[3] if len(row) > 3 else '')),
                    price_per_sq_ft,
                    float(width or 0),
                    float(height or 0)
                ))
                try:
                    self._log_audit('import_or_replace','sign_types', None, {
                        'name': str(row.get('name', '')),
                        'unit_price': float(unit_price or 0)
                    })
                except Exception:
                    pass
            
            conn.commit()
            conn.close()
            return True, f"Successfully imported {len(df)} records"
            
        except Exception as e:
            return False, f"Error importing CSV: {str(e)}"
    
    def export_to_excel(self, output_path, project_id=None):
        """Export project data to Excel format with company branding."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Export projects
                projects_df = pd.read_sql_query("SELECT * FROM projects", conn)
                projects_df.to_excel(writer, sheet_name='Projects', index=False)
                
                # Export sign types
                signs_df = pd.read_sql_query("SELECT * FROM sign_types", conn)
                signs_df.to_excel(writer, sheet_name='Sign Types', index=False)
                
                if project_id:
                    # Export specific project details
                    project_detail = self.get_project_estimate(project_id)
                    if project_detail:
                        detail_df = pd.DataFrame(project_detail)
                        detail_df.to_excel(writer, sheet_name=f'Project_{project_id}_Detail', index=False)
            
            conn.close()
            return True, f"Data exported to {output_path}"
            
        except Exception as e:
            return False, f"Error exporting to Excel: {str(e)}"

    def set_sign_image(self, sign_name: str, image_rel_path: str):
        """Associate an image (relative path) with a sign type.

        Args:
            sign_name: Name of the sign type (case-insensitive match)
            image_rel_path: Path relative to application root or dedicated images dir
        Returns: (success: bool, message: str)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("UPDATE sign_types SET image_path = ?, last_modified=CURRENT_TIMESTAMP WHERE lower(name)=lower(?)", (image_rel_path, sign_name))
            if cur.rowcount == 0:
                conn.close()
                return False, f"Sign type '{sign_name}' not found"
            conn.commit(); conn.close()
            try:
                self._log_audit('update_image','sign_types', None, {'name': sign_name, 'image_path': image_rel_path})
            except Exception:
                pass
            return True, 'Image path updated'
        except Exception as e:
            return False, f'Error setting image: {e}'
    
    def get_project_estimate(self, project_id):
        """Calculate comprehensive project estimate."""
        conn = sqlite3.connect(self.db_path)
        _proj_df = pd.read_sql_query("SELECT * FROM projects WHERE id = ?", conn, params=(project_id,))
        if _proj_df.empty:
            conn.close()
            return None
        project = _proj_df.iloc[0]
        # Optional pricing profile override
        profile = None
        if 'pricing_profile_id' in project and project['pricing_profile_id']:
            try:
                prof_df = pd.read_sql_query('SELECT * FROM pricing_profiles WHERE id=?', conn, params=(int(project['pricing_profile_id']),))
                if not prof_df.empty:
                    profile = prof_df.iloc[0]
            except Exception:
                profile = None

        estimate_data = []
        total_cost = 0.0

        buildings = pd.read_sql_query(
            "SELECT * FROM buildings WHERE project_id = ?",
            conn, params=(project_id,)
        )
        for _, building in buildings.iterrows():
            building_cost = 0.0
            signs = pd.read_sql_query('''
                SELECT st.name, st.unit_price, st.material, st.width, st.height,
                       bs.quantity, bs.custom_price
                FROM building_signs bs
                JOIN sign_types st ON bs.sign_type_id = st.id
                WHERE bs.building_id = ?
            ''', conn, params=(building['id'],))
            for _, sign in signs.iterrows():
                price = sign['custom_price'] if sign['custom_price'] else sign['unit_price']
                # Apply margin multiplier if pricing profile present
                if profile is not None and 'margin_multiplier' in profile and profile['margin_multiplier'] not in (None, 0, 1):
                    try:
                        price = float(price) * float(profile['margin_multiplier'])
                    except Exception:
                        pass
                line_total = price * sign['quantity']
                building_cost += line_total
                estimate_data.append({
                    'Building': building['name'],
                    'Item': sign['name'],
                    'Material': sign['material'],
                    'Dimensions': f"{sign['width']} x {sign['height']}" if sign['width'] and sign['height'] else '',
                    'Quantity': sign['quantity'],
                    'Unit_Price': price,
                    'Total': line_total
                })
            groups = pd.read_sql_query('''
                SELECT sg.name as group_name, bsg.quantity as group_quantity
                FROM building_sign_groups bsg
                JOIN sign_groups sg ON bsg.group_id = sg.id
                WHERE bsg.building_id = ?
            ''', conn, params=(building['id'],))
            for _, group in groups.iterrows():
                group_signs = pd.read_sql_query('''
                    SELECT st.name, st.unit_price, sgm.quantity
                    FROM sign_group_members sgm
                    JOIN sign_types st ON sgm.sign_type_id = st.id
                    JOIN sign_groups sg ON sgm.group_id = sg.id
                    WHERE sg.name = ?
                ''', conn, params=(group['group_name'],))
                group_total = 0.0
                for _, row in group_signs.iterrows():
                    gp = row['unit_price']
                    if profile is not None and 'margin_multiplier' in profile and profile['margin_multiplier'] not in (None, 0, 1):
                        try:
                            gp = float(gp) * float(profile['margin_multiplier'])
                        except Exception:
                            pass
                    group_total += gp * row['quantity']
                line_total = group_total * group['group_quantity']
                building_cost += line_total
                estimate_data.append({
                    'Building': building['name'],
                    'Item': f"Group: {group['group_name']}",
                    'Material': 'Various',
                    'Dimensions': '',
                    'Quantity': group['group_quantity'],
                    'Unit_Price': group_total,
                    'Total': line_total
                })
            total_cost += building_cost

        # Resolve effective installation & tax rates: profile overrides when present
        eff_install_rate = project['installation_rate']
        eff_tax_rate = project['sales_tax_rate']
        if profile is not None:
            try:
                if profile.get('installation_rate') not in (None, ''):
                    eff_install_rate = float(profile.get('installation_rate'))
                if profile.get('sales_tax_rate') not in (None, ''):
                    eff_tax_rate = float(profile.get('sales_tax_rate'))
            except Exception:
                pass

        if project['include_installation'] and eff_install_rate:
            installation_cost = total_cost * eff_install_rate
            total_cost += installation_cost
            estimate_data.append({
                'Building': 'ALL',
                'Item': 'Installation',
                'Material': '',
                'Dimensions': '',
                'Quantity': 1,
                'Unit_Price': installation_cost,
                'Total': installation_cost
            })
        if project['include_sales_tax'] and eff_tax_rate:
            tax_cost = total_cost * eff_tax_rate
            total_cost += tax_cost
            estimate_data.append({
                'Building': 'ALL',
                'Item': 'Sales Tax',
                'Material': '',
                'Dimensions': '',
                'Quantity': 1,
                'Unit_Price': tax_cost,
                'Total': tax_cost
            })
        conn.close()
        return estimate_data

    def recalc_prices_from_materials(self):
        """Recalculate sign type pricing from material_pricing table.

        Rules:
        - For each sign_types row with width & height > 0 and material present & matching material_pricing.material_name:
            * Set price_per_sq_ft = material_pricing.price_per_sq_ft
            * Set unit_price = width * height * price_per_sq_ft (overwrite existing)
        Returns count of rows updated.
        """
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('''
            SELECT st.id, st.width, st.height, mp.price_per_sq_ft
            FROM sign_types st
            JOIN material_pricing mp ON LOWER(st.material)=LOWER(mp.material_name)
            WHERE st.width > 0 AND st.height > 0
        ''')
        rows = cur.fetchall()
        updated = 0
        for sid, w, h, ppsf in rows:
            try:
                area = float(w) * float(h)
                unit_price = area * float(ppsf)
            except Exception:
                continue
            cur.execute('''UPDATE sign_types
                           SET price_per_sq_ft=?, unit_price=?, last_modified=CURRENT_TIMESTAMP
                           WHERE id=?''', (float(ppsf), float(unit_price), sid))
            updated += 1
        try:
            if updated:
                self._log_audit('recalc_prices','sign_types', None, {'rows_updated': updated})
        except Exception:
            pass
        conn.commit()
        conn.close()
        return updated
    
    def optimize_for_onedrive(self):
        """Optimize database for OneDrive sharing."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Set pragmas for better OneDrive compatibility
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = FULL")
        cursor.execute("PRAGMA cache_size = 10000")
        cursor.execute("VACUUM")
        
        conn.close()
    
    def backup_database(self, backup_path):
        """Create a backup of the database."""
        try:
            shutil.copy2(self.db_path, backup_path)
            return True, f"Database backed up to {backup_path}"
        except Exception as e:
            return False, f"Backup failed: {str(e)}"

    # ----------------------- Category One Feature Methods -----------------------
    def _log_audit(self, action: str, entity: str, entity_id: int | None, meta: dict | None = None):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute('INSERT INTO audit_log(action, entity, entity_id, meta) VALUES (?,?,?,?)',
                        (action, entity, entity_id, json.dumps(meta or {})))
            conn.commit(); conn.close()
        except Exception:
            pass

    # Role management (simple)
    def set_user_role(self, username: str, role: str):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('INSERT INTO user_roles(username, role) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET role=excluded.role', (username, role))
        conn.commit(); conn.close()
        self._log_audit('set_role','user_roles', None, {'username': username, 'role': role})

    def get_user_role(self, username: str) -> str | None:
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('SELECT role FROM user_roles WHERE username=?',(username,))
        row = cur.fetchone(); conn.close(); return row[0] if row else None

    # Pricing profiles
    def create_pricing_profile(self, name: str, sales_tax_rate: float = 0.0, installation_rate: float = 0.0, margin_multiplier: float = 1.0, is_default: bool = False):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('''INSERT INTO pricing_profiles(name, sales_tax_rate, installation_rate, margin_multiplier, is_default)
                       VALUES(?,?,?,?,?)''', (name, sales_tax_rate, installation_rate, margin_multiplier, 1 if is_default else 0))
        pid = cur.lastrowid
        if is_default:
            cur.execute('UPDATE pricing_profiles SET is_default=0 WHERE id<>?', (pid,))
            cur.execute('UPDATE projects SET pricing_profile_id=? WHERE pricing_profile_id IS NULL', (pid,))
        conn.commit(); conn.close()
        self._log_audit('create','pricing_profiles', pid, {'name': name})
        return pid

    def assign_pricing_profile_to_project(self, project_id: int, profile_id: int):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('UPDATE projects SET pricing_profile_id=?, last_modified=CURRENT_TIMESTAMP WHERE id=?', (profile_id, project_id))
        conn.commit(); conn.close()
        self._log_audit('assign_profile','projects', project_id, {'profile_id': profile_id})

    # Tagging
    def ensure_tag(self, name: str) -> int:
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('INSERT INTO sign_type_tags(name) VALUES(?) ON CONFLICT(name) DO NOTHING', (name,))
        conn.commit()
        cur.execute('SELECT id FROM sign_type_tags WHERE name=?',(name,))
        tid = cur.fetchone()[0]
        conn.close(); return tid

    def tag_sign_type(self, sign_type_name: str, tag_name: str):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('SELECT id FROM sign_types WHERE lower(name)=lower(?)',(sign_type_name,))
        row = cur.fetchone()
        if not row:
            conn.close(); return False, 'sign type not found'
        stid = row[0]
        tid = self.ensure_tag(tag_name)
        cur.execute('INSERT OR IGNORE INTO sign_type_tag_map(sign_type_id, tag_id) VALUES(?,?)',(stid, tid))
        conn.commit(); conn.close()
        self._log_audit('tag','sign_types', stid, {'tag': tag_name})
        return True, 'tag added'

    def list_tags_for_sign_type(self, sign_type_name: str):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('''SELECT stt.name FROM sign_type_tags stt
                       JOIN sign_type_tag_map m ON m.tag_id=stt.id
                       JOIN sign_types s ON s.id=m.sign_type_id
                       WHERE lower(s.name)=lower(?) ORDER BY stt.name''',(sign_type_name,))
        rows = [r[0] for r in cur.fetchall()]; conn.close(); return rows

    # Notes
    def add_note(self, entity_type: str, entity_id: int, note: str, include_in_export: bool = True):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('INSERT INTO notes(entity_type, entity_id, note, include_in_export) VALUES(?,?,?,?)', (entity_type, entity_id, note, 1 if include_in_export else 0))
        nid = cur.lastrowid; conn.commit(); conn.close()
        self._log_audit('add_note', entity_type, entity_id, {'note_id': nid})
        return nid

    def list_notes(self, entity_type: str, entity_id: int, export_only: bool = False):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        if export_only:
            cur.execute('SELECT id, note, created_at FROM notes WHERE entity_type=? AND entity_id=? AND include_in_export=1 ORDER BY created_at',(entity_type, entity_id))
        else:
            cur.execute('SELECT id, note, include_in_export, created_at FROM notes WHERE entity_type=? AND entity_id=? ORDER BY created_at',(entity_type, entity_id))
        rows = cur.fetchall(); conn.close(); return rows

    # Bid templates
    def create_bid_template(self, name: str, description: str = '') -> int:
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('INSERT INTO bid_templates(name, description) VALUES(?,?)',(name, description))
        tid = cur.lastrowid; conn.commit(); conn.close()
        self._log_audit('create','bid_templates', tid, {'name': name})
        return tid

    def add_item_to_template(self, template_id: int, sign_type_name: str, quantity: int = 1):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('SELECT id FROM sign_types WHERE lower(name)=lower(?)',(sign_type_name,))
        row = cur.fetchone()
        if not row:
            conn.close(); return False, 'sign type not found'
        stid = row[0]
        cur.execute('INSERT INTO bid_template_items(template_id, sign_type_id, quantity) VALUES(?,?,?)',(template_id, stid, quantity))
        conn.commit(); conn.close()
        self._log_audit('add_item','bid_templates', template_id, {'sign_type_id': stid, 'qty': quantity})
        return True, 'item added'

    def apply_template_to_building(self, template_id: int, building_id: int, group_as_single: bool = False):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('SELECT sign_type_id, quantity FROM bid_template_items WHERE template_id=?',(template_id,))
        items = cur.fetchall()
        for stid, qty in items:
            cur.execute('INSERT INTO building_signs(building_id, sign_type_id, quantity) VALUES(?,?,?)',(building_id, stid, qty))
        conn.commit(); conn.close()
        self._log_audit('apply_template','buildings', building_id, {'template_id': template_id, 'count': len(items)})
        return len(items)

    # Estimate snapshots
    def create_estimate_snapshot(self, project_id: int, label: str | None = None):
        data = self.get_project_estimate(project_id)
        if data is None:
            return False, 'project not found'
        payload = json.dumps(data, sort_keys=True)
        import hashlib
        snap_hash = hashlib.sha1(payload.encode('utf-8')).hexdigest()
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('INSERT INTO estimate_snapshots(project_id, label, snapshot_hash, data) VALUES(?,?,?,?)',(project_id, label, snap_hash, payload))
        sid = cur.lastrowid; conn.commit(); conn.close()
        self._log_audit('snapshot','projects', project_id, {'snapshot_id': sid})
        return True, sid

    def list_estimate_snapshots(self, project_id: int):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('SELECT id, label, snapshot_hash, created_at FROM estimate_snapshots WHERE project_id=? ORDER BY created_at DESC',(project_id,))
        rows = cur.fetchall(); conn.close(); return rows

    def diff_snapshots(self, snapshot_a: int, snapshot_b: int):
        conn = sqlite3.connect(self.db_path); cur = conn.cursor()
        cur.execute('SELECT data FROM estimate_snapshots WHERE id=?',(snapshot_a,)); a = cur.fetchone()
        cur.execute('SELECT data FROM estimate_snapshots WHERE id=?',(snapshot_b,)); b = cur.fetchone()
        conn.close()
        if not a or not b:
            return None
        da = {f"{r['Building']}|{r['Item']}": r for r in json.loads(a[0])}
        db = {f"{r['Building']}|{r['Item']}": r for r in json.loads(b[0])}
        added = [db[k] for k in db.keys() - da.keys()]
        removed = [da[k] for k in da.keys() - db.keys()]
        changed = []
        for k in da.keys() & db.keys():
            if da[k].get('Total') != db[k].get('Total') or da[k].get('Quantity') != db[k].get('Quantity'):
                changed.append({'key': k, 'from': da[k], 'to': db[k]})
        return {'added': added, 'removed': removed, 'changed': changed}

    # Convenience for client-facing mode: trimming sensitive fields
    def build_client_facing_estimate(self, project_id: int):
        data = self.get_project_estimate(project_id)
        if not data:
            return []
        sanitized = []
        for row in data:
            nr = dict(row)
            nr.pop('Unit_Price', None)  # remove per-sign price
            sanitized.append(nr)
        return sanitized


# ---------------------------- MSSQL Implementation ---------------------------
class MssqlDatabaseManager:
    """Experimental SQL Server backend.

    Only a subset of methods are implemented initially. Methods not yet ported
    will raise NotImplementedError to surface gaps clearly during staged
    migration. This backend expects a working ODBC driver (e.g. *ODBC Driver 18
    for SQL Server*) and a valid pyodbc style connection string supplied via
    SIGN_APP_MSSQL_CONN.
    """

    def __init__(self, conn_string: str | None = None):
        if pyodbc is None:
            raise RuntimeError("pyodbc not installed; install pyodbc and proper ODBC driver to use MSSQL backend")
        self.conn_string = conn_string or MSSQL_CONN_STRING
        if not self.conn_string:
            raise RuntimeError("MSSQL backend selected but SIGN_APP_MSSQL_CONN not set")
        self.init_database()

    # ---- Connection helper ----
    def _connect(self):
        return pyodbc.connect(self.conn_string)

    # ---- Schema initialization ----
    def init_database(self):  # noqa: C901 (complexity acceptable for bootstrap)
        conn = self._connect()
        cur = conn.cursor()

        def ensure_table(name: str, ddl: str):
            cur.execute("SELECT 1 FROM sys.tables WHERE name=?", (name,))
            if not cur.fetchone():
                cur.execute(ddl)

        # Core tables
        ensure_table('projects', (
            "CREATE TABLE projects ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "name NVARCHAR(255) NOT NULL UNIQUE,"
            "description NVARCHAR(MAX),"
            "created_date DATE DEFAULT CAST(GETDATE() AS DATE),"
            "sales_tax_rate FLOAT DEFAULT 0,"
            "installation_rate FLOAT DEFAULT 0,"
            "include_installation BIT DEFAULT 1,"
            "include_sales_tax BIT DEFAULT 1,"
            "pricing_profile_id INT NULL,"
            "last_modified DATETIME2 DEFAULT SYSUTCDATETIME()"  # profile FK added later if needed
            ")"))

        ensure_table('buildings', (
            "CREATE TABLE buildings ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "project_id INT NOT NULL,"
            "name NVARCHAR(255) NOT NULL,"
            "description NVARCHAR(MAX),"
            "last_modified DATETIME2 DEFAULT SYSUTCDATETIME(),"
            "CONSTRAINT fk_building_project FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE"
            ")"))
        # Unique composite index
        cur.execute("IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='idx_buildings_project_name') "
                    "CREATE UNIQUE INDEX idx_buildings_project_name ON buildings(project_id, name)")

        ensure_table('sign_types', (
            "CREATE TABLE sign_types ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "name NVARCHAR(255) NOT NULL UNIQUE,"
            "description NVARCHAR(MAX),"
            "material_alt NVARCHAR(255),"
            "unit_price FLOAT DEFAULT 0,"
            "material NVARCHAR(255),"
            "price_per_sq_ft FLOAT DEFAULT 0,"
            "width FLOAT DEFAULT 0,"
            "height FLOAT DEFAULT 0,"
            "material_multiplier FLOAT DEFAULT 0,"
            "install_type NVARCHAR(255),"
            "install_time_hours FLOAT DEFAULT 0,"
            "per_sign_install_rate FLOAT DEFAULT 0,"
            "image_path NVARCHAR(1024),"
            "last_modified DATETIME2 DEFAULT SYSUTCDATETIME()"
            ")"))

        ensure_table('sign_groups', (
            "CREATE TABLE sign_groups ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "name NVARCHAR(255) NOT NULL UNIQUE,"
            "description NVARCHAR(MAX),"
            "last_modified DATETIME2 DEFAULT SYSUTCDATETIME()"
            ")"))

        ensure_table('sign_group_members', (
            "CREATE TABLE sign_group_members ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "group_id INT NOT NULL,"
            "sign_type_id INT NOT NULL,"
            "quantity INT DEFAULT 1,"
            "CONSTRAINT fk_sgm_group FOREIGN KEY(group_id) REFERENCES sign_groups(id) ON DELETE CASCADE,"
            "CONSTRAINT fk_sgm_sign FOREIGN KEY(sign_type_id) REFERENCES sign_types(id) ON DELETE CASCADE"
            ")"))

        ensure_table('building_signs', (
            "CREATE TABLE building_signs ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "building_id INT NOT NULL,"
            "sign_type_id INT NOT NULL,"
            "quantity INT DEFAULT 1,"
            "custom_price FLOAT NULL,"
            "CONSTRAINT fk_bs_building FOREIGN KEY(building_id) REFERENCES buildings(id) ON DELETE CASCADE,"
            "CONSTRAINT fk_bs_sign FOREIGN KEY(sign_type_id) REFERENCES sign_types(id) ON DELETE CASCADE"
            ")"))

        ensure_table('building_sign_groups', (
            "CREATE TABLE building_sign_groups ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "building_id INT NOT NULL,"
            "group_id INT NOT NULL,"
            "quantity INT DEFAULT 1,"
            "CONSTRAINT fk_bsg_building FOREIGN KEY(building_id) REFERENCES buildings(id) ON DELETE CASCADE,"
            "CONSTRAINT fk_bsg_group FOREIGN KEY(group_id) REFERENCES sign_groups(id) ON DELETE CASCADE"
            ")"))

        ensure_table('material_pricing', (
            "CREATE TABLE material_pricing ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "material_name NVARCHAR(255) NOT NULL UNIQUE,"
            "price_per_sq_ft FLOAT NOT NULL,"
            "last_updated DATETIME2 DEFAULT SYSUTCDATETIME()"
            ")"))

        # Minimal audit + snapshots (JSON stored as text)
        ensure_table('audit_log', (
            "CREATE TABLE audit_log ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "action NVARCHAR(255) NOT NULL,"
            "entity NVARCHAR(255) NOT NULL,"
            "entity_id INT NULL,"
            "meta NVARCHAR(MAX),"
            "created_at DATETIME2 DEFAULT SYSUTCDATETIME()"
            ")"))
        ensure_table('estimate_snapshots', (
            "CREATE TABLE estimate_snapshots ("
            "id INT IDENTITY(1,1) PRIMARY KEY,"
            "project_id INT NOT NULL,"
            "label NVARCHAR(255),"
            "snapshot_hash NVARCHAR(64),"
            "data NVARCHAR(MAX) NOT NULL,"
            "created_at DATETIME2 DEFAULT SYSUTCDATETIME(),"
            "CONSTRAINT fk_snap_project FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE"
            ")"))

        conn.commit(); conn.close()

    # ---------------- Core feature methods (ported) ----------------
    def import_csv_data(self, csv_file_path, table_mapping=None):
        try:
            df = pd.read_csv(csv_file_path)
            conn = self._connect(); cur = conn.cursor()
            if table_mapping is None:
                table_mapping = {
                    'name': 'name', 'description': 'description', 'price': 'unit_price',
                    'material': 'material', 'width': 'width', 'height': 'height'
                }
            for _, row in df.iterrows():
                name = str(row.get('name', row.iloc[0] if len(row) > 0 else ''))
                description = str(row.get('description', row.iloc[1] if len(row) > 1 else ''))
                width = row.get('width', row.get('Width', 0)) or 0
                height = row.get('height', row.get('Height', 0)) or 0
                unit_price = row.get('price', row.get('Price', row.get('unit_price', 0))) or 0
                price_per_sq_ft = 0.0
                try:
                    if width and height and unit_price:
                        area = float(width) * float(height)
                        if area > 0:
                            price_per_sq_ft = float(unit_price) / area
                except Exception:
                    price_per_sq_ft = 0.0
                # Upsert logic (update then insert if missing)
                cur.execute('UPDATE sign_types SET description=?, unit_price=?, material=?, price_per_sq_ft=?, width=?, height=?, last_modified=SYSUTCDATETIME() WHERE name=?',
                            (description, float(unit_price), str(row.get('material', '')), price_per_sq_ft, float(width or 0), float(height or 0), name))
                if cur.rowcount == 0:
                    cur.execute('INSERT INTO sign_types (name, description, unit_price, material, price_per_sq_ft, width, height) VALUES (?,?,?,?,?,?,?)',
                                (name, description, float(unit_price), str(row.get('material', '')), price_per_sq_ft, float(width or 0), float(height or 0)))
                self._log_audit('import_or_replace', 'sign_types', None, {'name': name, 'unit_price': float(unit_price)})
            conn.commit(); conn.close()
            return True, f"Successfully imported {len(df)} records"
        except Exception as e:  # pragma: no cover - error path
            return False, f"Error importing CSV: {e}"

    def get_project_estimate(self, project_id):
        conn = self._connect()
        projects_df = pd.read_sql("SELECT * FROM projects WHERE id = ?", conn, params=[project_id])
        if projects_df.empty:
            conn.close(); return None
        project = projects_df.iloc[0]
        estimate_data = []
        total_cost = 0.0
        buildings = pd.read_sql("SELECT * FROM buildings WHERE project_id=?", conn, params=[project_id])
        for _, building in buildings.iterrows():
            building_cost = 0.0
            signs = pd.read_sql('''SELECT st.name, st.unit_price, st.material, st.width, st.height, bs.quantity, bs.custom_price
                                   FROM building_signs bs JOIN sign_types st ON bs.sign_type_id = st.id WHERE bs.building_id = ?''', conn, params=[building['id']])
            for _, sign in signs.iterrows():
                price = sign['custom_price'] if sign['custom_price'] else sign['unit_price']
                line_total = price * sign['quantity']
                building_cost += line_total
                estimate_data.append({
                    'Building': building['name'],
                    'Item': sign['name'],
                    'Material': sign['material'],
                    'Dimensions': f"{sign['width']} x {sign['height']}" if sign['width'] and sign['height'] else '',
                    'Quantity': sign['quantity'],
                    'Unit_Price': price,
                    'Total': line_total
                })
            total_cost += building_cost
        if project.get('include_installation') and project.get('installation_rate'):
            inst = total_cost * float(project['installation_rate'])
            total_cost += inst
            estimate_data.append({'Building': 'ALL', 'Item': 'Installation', 'Material': '', 'Dimensions': '', 'Quantity': 1, 'Unit_Price': inst, 'Total': inst})
        if project.get('include_sales_tax') and project.get('sales_tax_rate'):
            tax = total_cost * float(project['sales_tax_rate'])
            total_cost += tax
            estimate_data.append({'Building': 'ALL', 'Item': 'Sales Tax', 'Material': '', 'Dimensions': '', 'Quantity': 1, 'Unit_Price': tax, 'Total': tax})
        conn.close(); return estimate_data

    def recalc_prices_from_materials(self):
        conn = self._connect(); cur = conn.cursor()
        cur.execute('''SELECT st.id, st.width, st.height, mp.price_per_sq_ft
                       FROM sign_types st JOIN material_pricing mp ON LOWER(st.material)=LOWER(mp.material_name)
                       WHERE st.width > 0 AND st.height > 0''')
        rows = cur.fetchall(); updated = 0
        for sid, w, h, ppsf in rows:
            try:
                area = float(w) * float(h); unit_price = area * float(ppsf)
            except Exception:
                continue
            cur.execute('UPDATE sign_types SET price_per_sq_ft=?, unit_price=?, last_modified=SYSUTCDATETIME() WHERE id=?', (float(ppsf), float(unit_price), sid))
            updated += 1
        if updated:
            self._log_audit('recalc_prices', 'sign_types', None, {'rows_updated': updated})
        conn.commit(); conn.close(); return updated

    def set_sign_image(self, sign_name: str, image_rel_path: str):
        try:
            conn = self._connect(); cur = conn.cursor()
            cur.execute('UPDATE sign_types SET image_path=?, last_modified=SYSUTCDATETIME() WHERE LOWER(name)=LOWER(?)', (image_rel_path, sign_name))
            if cur.rowcount == 0:
                conn.close(); return False, f"Sign type '{sign_name}' not found"
            conn.commit(); conn.close()
            self._log_audit('update_image', 'sign_types', None, {'name': sign_name, 'image_path': image_rel_path})
            return True, 'Image path updated'
        except Exception as e:  # pragma: no cover
            return False, f'Error setting image: {e}'

    # --- Minimal audit helper ---
    def _log_audit(self, action: str, entity: str, entity_id: int | None, meta: dict | None = None):
        try:
            conn = self._connect(); cur = conn.cursor()
            cur.execute('INSERT INTO audit_log(action, entity, entity_id, meta) VALUES (?,?,?,?)', (action, entity, entity_id, json.dumps(meta or {})))
            conn.commit(); conn.close()
        except Exception:  # pragma: no cover
            pass

    # --- Unported methods ---
    def optimize_for_onedrive(self):  # pragma: no cover
        return  # not applicable

    # Remaining public API methods raise until ported
    def export_to_excel(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('export_to_excel not yet implemented for MSSQL backend')
    def create_pricing_profile(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('create_pricing_profile not yet implemented for MSSQL backend')
    def assign_pricing_profile_to_project(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('assign_pricing_profile_to_project not yet implemented for MSSQL backend')
    def ensure_tag(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('tagging not yet implemented for MSSQL backend')
    def tag_sign_type(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('tagging not yet implemented for MSSQL backend')
    def list_tags_for_sign_type(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('tagging not yet implemented for MSSQL backend')
    def add_note(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('notes not yet implemented for MSSQL backend')
    def list_notes(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('notes not yet implemented for MSSQL backend')
    def create_bid_template(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('bid templates not yet implemented for MSSQL backend')
    def add_item_to_template(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('bid templates not yet implemented for MSSQL backend')
    def apply_template_to_building(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('bid templates not yet implemented for MSSQL backend')
    def create_estimate_snapshot(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('snapshots not yet implemented for MSSQL backend')
    def list_estimate_snapshots(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('snapshots not yet implemented for MSSQL backend')
    def diff_snapshots(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('snapshots not yet implemented for MSSQL backend')
    def build_client_facing_estimate(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError('client facing estimate not yet implemented for MSSQL backend')


# Public alias matching selected backend
if DB_BACKEND == 'mssql':  # pragma: no cover - selection logic
    DatabaseManager = MssqlDatabaseManager  # type: ignore
else:
    DatabaseManager = SQLiteDatabaseManager  # type: ignore

