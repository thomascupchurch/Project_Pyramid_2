"""
Database utilities for the Sign Estimation Application.
Handles database initialization, data import/export, and OneDrive optimization.
"""

import sqlite3
import pandas as pd
import json
import os
from datetime import datetime
import shutil
from pathlib import Path

class DatabaseManager:
    def __init__(self, db_path="sign_estimation.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_date DATE DEFAULT CURRENT_DATE,
                sales_tax_rate REAL DEFAULT 0.0,
                installation_rate REAL DEFAULT 0.0,
                include_installation BOOLEAN DEFAULT 1,
                include_sales_tax BOOLEAN DEFAULT 1,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Buildings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS buildings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )
        ''')
        
        # Sign types master table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sign_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                unit_price REAL DEFAULT 0.0,
                material TEXT,
                price_per_sq_ft REAL DEFAULT 0.0,
                width REAL DEFAULT 0.0,
                height REAL DEFAULT 0.0,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sign groups table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sign_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sign group members (which signs are in which groups)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sign_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                sign_type_id INTEGER,
                quantity INTEGER DEFAULT 1,
                FOREIGN KEY (group_id) REFERENCES sign_groups (id) ON DELETE CASCADE,
                FOREIGN KEY (sign_type_id) REFERENCES sign_types (id) ON DELETE CASCADE
            )
        ''')
        
        # Building signs (individual signs assigned to buildings)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS building_signs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building_id INTEGER,
                sign_type_id INTEGER,
                quantity INTEGER DEFAULT 1,
                custom_price REAL,
                FOREIGN KEY (building_id) REFERENCES buildings (id) ON DELETE CASCADE,
                FOREIGN KEY (sign_type_id) REFERENCES sign_types (id) ON DELETE CASCADE
            )
        ''')
        
        # Building sign groups (sign groups assigned to buildings)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS building_sign_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building_id INTEGER,
                group_id INTEGER,
                quantity INTEGER DEFAULT 1,
                FOREIGN KEY (building_id) REFERENCES buildings (id) ON DELETE CASCADE,
                FOREIGN KEY (group_id) REFERENCES sign_groups (id) ON DELETE CASCADE
            )
        ''')
        
        # Material pricing table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS material_pricing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_name TEXT NOT NULL UNIQUE,
                price_per_sq_ft REAL NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
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
    
    def get_project_estimate(self, project_id):
        """Calculate comprehensive project estimate."""
        conn = sqlite3.connect(self.db_path)
        
        # Get project info
        project = pd.read_sql_query(
            "SELECT * FROM projects WHERE id = ?", 
            conn, params=(project_id,)
        ).iloc[0] if pd.read_sql_query("SELECT * FROM projects WHERE id = ?", conn, params=(project_id,)).shape[0] > 0 else None
        
        if not project:
            conn.close()
            return None
        
        estimate_data = []
        total_cost = 0.0
        
        # Get buildings for this project
        buildings = pd.read_sql_query(
            "SELECT * FROM buildings WHERE project_id = ?",
            conn, params=(project_id,)
        )
        
        for _, building in buildings.iterrows():
            building_cost = 0.0
            
            # Individual signs
            signs = pd.read_sql_query('''
                SELECT st.name, st.unit_price, st.material, st.width, st.height, 
                       bs.quantity, bs.custom_price
                FROM building_signs bs
                JOIN sign_types st ON bs.sign_type_id = st.id
                WHERE bs.building_id = ?
            ''', conn, params=(building['id'],))
            
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
            
            # Sign groups
            groups = pd.read_sql_query('''
                SELECT sg.name as group_name, bsg.quantity as group_quantity
                FROM building_sign_groups bsg
                JOIN sign_groups sg ON bsg.group_id = sg.id
                WHERE bsg.building_id = ?
            ''', conn, params=(building['id'],))
            
            for _, group in groups.iterrows():
                # Get signs in this group
                group_signs = pd.read_sql_query('''
                    SELECT st.name, st.unit_price, sgm.quantity
                    FROM sign_group_members sgm
                    JOIN sign_types st ON sgm.sign_type_id = st.id
                    JOIN sign_groups sg ON sgm.group_id = sg.id
                    WHERE sg.name = ?
                ''', conn, params=(group['group_name'],))
                
                group_total = sum(row['unit_price'] * row['quantity'] for _, row in group_signs.iterrows())
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
        
        # Add installation and tax if applicable
        if project['include_installation'] and project['installation_rate']:
            installation_cost = total_cost * project['installation_rate']
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
        
        if project['include_sales_tax'] and project['sales_tax_rate']:
            tax_cost = total_cost * project['sales_tax_rate']
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
