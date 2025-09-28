"""
Cost calculation utilities for the Sign Estimation Application.
Handles various pricing models and estimation calculations.
"""

import pandas as pd
import sqlite3
from typing import Dict, List, Tuple, Optional

class CostCalculator:
    def __init__(self, db_path="sign_estimation.db"):
        self.db_path = db_path
    
    def calculate_sign_cost(self, sign_type_id: int, quantity: int = 1, 
                           custom_dimensions: Optional[Tuple[float, float]] = None,
                           custom_material: Optional[str] = None) -> Dict:
        """
        Calculate cost for individual signs with multiple pricing methods.
        
        Args:
            sign_type_id: ID of the sign type
            quantity: Number of signs
            custom_dimensions: Optional (width, height) for custom sizing
            custom_material: Optional custom material override
            
        Returns:
            Dictionary with cost breakdown
        """
        conn = sqlite3.connect(self.db_path)
        
        # Get sign type details
        sign_query = "SELECT * FROM sign_types WHERE id = ?"
        sign_df = pd.read_sql_query(sign_query, conn, params=(sign_type_id,))
        
        if sign_df.empty:
            conn.close()
            return {"error": "Sign type not found"}
        
        sign = sign_df.iloc[0]
        
        # Determine dimensions
        if custom_dimensions:
            width, height = custom_dimensions
        else:
            width, height = sign['width'], sign['height']
        
        area = width * height if width and height else 0
        
        # Determine material
        material = custom_material if custom_material else sign['material']
        
        # Calculate costs using different methods
        cost_methods = {}
        
        # Method 1: Unit price
        if sign['unit_price']:
            cost_methods['unit_price'] = {
                'method': 'Unit Price',
                'unit_cost': sign['unit_price'],
                'quantity': quantity,
                'total_cost': sign['unit_price'] * quantity,
                'details': f"${sign['unit_price']:.2f} per unit × {quantity} units"
            }
        
        # Method 2: Price per square foot (from sign type)
        if sign['price_per_sq_ft'] and area > 0:
            cost_methods['sq_ft_sign'] = {
                'method': 'Square Foot (Sign Type)',
                'price_per_sq_ft': sign['price_per_sq_ft'],
                'area': area,
                'quantity': quantity,
                'total_cost': sign['price_per_sq_ft'] * area * quantity,
                'details': f"${sign['price_per_sq_ft']:.2f}/sq ft × {area:.2f} sq ft × {quantity} units"
            }
        
        # Method 3: Price per square foot (from material pricing)
        if material and area > 0:
            material_query = "SELECT price_per_sq_ft FROM material_pricing WHERE material_name = ?"
            material_df = pd.read_sql_query(material_query, conn, params=(material,))
            
            if not material_df.empty:
                material_price = material_df.iloc[0]['price_per_sq_ft']
                cost_methods['sq_ft_material'] = {
                    'method': 'Square Foot (Material)',
                    'price_per_sq_ft': material_price,
                    'area': area,
                    'quantity': quantity,
                    'total_cost': material_price * area * quantity,
                    'details': f"${material_price:.2f}/sq ft × {area:.2f} sq ft × {quantity} units"
                }
        
        conn.close()
        
        return {
            'sign_name': sign['name'],
            'material': material,
            'dimensions': f"{width} × {height}" if width and height else "Not specified",
            'area': area,
            'quantity': quantity,
            'cost_methods': cost_methods
        }

    def get_best_cost_method(self, cost_methods: Dict) -> Optional[Dict]:
        """Return the preferred cost method from a cost_methods mapping.

        Priority order (business rule):
            1. unit_price (explicit stored price)
            2. sq_ft_material (material pricing table)
            3. sq_ft_sign (price_per_sq_ft stored on sign)
        Falls back to first available if none of the priority keys present.
        Returns None if mapping empty.
        """
        priority = ['unit_price', 'sq_ft_material', 'sq_ft_sign']
        for key in priority:
            if key in cost_methods:
                return cost_methods[key]
        # Fallback
        if cost_methods:
            # Return deterministic first (sorted by key for stability)
            first_key = sorted(cost_methods.keys())[0]
            return cost_methods[first_key]
        return None

# ------------------ Helper Functions Used by App Callbacks ------------------ #
def compute_unit_price(row: Dict, price_mode: str) -> float:
    """Compute unit price for a sign or group member based on pricing mode.

    Precedence for per_area mode: price_per_sq_ft > material_multiplier.
    Falls back to unit_price if per_area requirements not satisfied.
    """
    def _f(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0
    if price_mode == 'per_area':
        width = _f(row.get('width'))
        height = _f(row.get('height'))
        area = width * height if width and height else 0
        if area > 0:
            ppsf = _f(row.get('price_per_sq_ft'))
            if ppsf <= 0:
                # fallback to material_multiplier if provided
                ppsf = _f(row.get('material_multiplier'))
            if ppsf > 0:
                return area * ppsf
    return _f(row.get('unit_price'))

def compute_install_cost(install_mode: str,
                         grand_subtotal: float,
                         total_sign_count: float,
                         total_area: float,
                         inst_percent: float,
                         inst_per_sign: float,
                         inst_per_area: float,
                         inst_hours: float,
                         inst_hourly: float,
                         auto_enabled: bool,
                         auto_install_amount_per_sign: float,
                         auto_install_hours: float) -> float:
    """Centralized installation cost computation with auto fallback handling."""
    install_cost = 0.0
    if install_mode == 'percent':
        install_cost = grand_subtotal * (inst_percent/100.0)
    elif install_mode == 'per_sign':
        if inst_per_sign > 0:
            install_cost = total_sign_count * inst_per_sign
        elif auto_enabled and auto_install_amount_per_sign > 0:
            install_cost = auto_install_amount_per_sign
    elif install_mode == 'per_area':
        install_cost = total_area * inst_per_area
    elif install_mode == 'hours':
        if inst_hours > 0:
            install_cost = inst_hours * inst_hourly
        elif auto_enabled and auto_install_hours > 0:
            install_cost = auto_install_hours * inst_hourly
    return install_cost
    
    def calculate_group_cost(self, group_id: int, quantity: int = 1) -> Dict:
        """Calculate cost for sign groups."""
        conn = sqlite3.connect(self.db_path)
        
        # Get group details
        group_query = "SELECT * FROM sign_groups WHERE id = ?"
        group_df = pd.read_sql_query(group_query, conn, params=(group_id,))
        
        if group_df.empty:
            conn.close()
            return {"error": "Sign group not found"}
        
        group = group_df.iloc[0]
        
        # Get signs in the group
        members_query = '''
            SELECT st.*, sgm.quantity as group_quantity
            FROM sign_group_members sgm
            JOIN sign_types st ON sgm.sign_type_id = st.id
            WHERE sgm.group_id = ?
        '''
        members_df = pd.read_sql_query(members_query, conn, params=(group_id,))
        
        group_cost_breakdown = []
        total_group_cost = 0
        
        for _, member in members_df.iterrows():
            sign_cost = self.calculate_sign_cost(
                member['id'], 
                member['group_quantity']
            )
            
            if 'error' not in sign_cost:
                # Use the best available pricing method
                best_cost = self.get_best_cost_method(sign_cost['cost_methods'])
                if best_cost:
                    group_cost_breakdown.append({
                        'sign_name': sign_cost['sign_name'],
                        'quantity_in_group': member['group_quantity'],
                        'cost_per_unit': best_cost['total_cost'] / member['group_quantity'],
                        'total_cost': best_cost['total_cost'],
                        'method_used': best_cost['method']
                    })
                    total_group_cost += best_cost['total_cost']
        
        conn.close()
        
        return {
            'group_name': group['name'],
            'group_description': group['description'],
            'signs_in_group': group_cost_breakdown,
            'cost_per_group': total_group_cost,
            'total_quantity': quantity,
            'total_cost': total_group_cost * quantity
        }
    
    def get_best_cost_method(self, cost_methods: Dict) -> Optional[Dict]:
        """Determine the best cost method from available options."""
        # Priority order: unit_price, sq_ft_material, sq_ft_sign
        priority_order = ['unit_price', 'sq_ft_material', 'sq_ft_sign']
        
        for method in priority_order:
            if method in cost_methods:
                return cost_methods[method]
        
        # If no priority method found, return the first available
        if cost_methods:
            return list(cost_methods.values())[0]
        
        return None
    
    def calculate_building_cost(self, building_id: int) -> Dict:
        """Calculate total cost for all signs in a building."""
        conn = sqlite3.connect(self.db_path)
        
        # Get building info
        building_query = "SELECT * FROM buildings WHERE id = ?"
        building_df = pd.read_sql_query(building_query, conn, params=(building_id,))
        
        if building_df.empty:
            conn.close()
            return {"error": "Building not found"}
        
        building = building_df.iloc[0]
        
        # Calculate individual signs
        individual_signs = []
        individual_total = 0
        
        signs_query = '''
            SELECT bs.*, st.name as sign_name
            FROM building_signs bs
            JOIN sign_types st ON bs.sign_type_id = st.id
            WHERE bs.building_id = ?
        '''
        signs_df = pd.read_sql_query(signs_query, conn, params=(building_id,))
        
        for _, sign_row in signs_df.iterrows():
            if sign_row['custom_price']:
                # Use custom price
                line_total = sign_row['custom_price'] * sign_row['quantity']
                individual_signs.append({
                    'sign_name': sign_row['sign_name'],
                    'quantity': sign_row['quantity'],
                    'unit_cost': sign_row['custom_price'],
                    'total_cost': line_total,
                    'pricing_method': 'Custom Price'
                })
            else:
                # Use calculated price
                sign_cost = self.calculate_sign_cost(
                    sign_row['sign_type_id'],
                    sign_row['quantity']
                )
                
                if 'error' not in sign_cost:
                    best_cost = self.get_best_cost_method(sign_cost['cost_methods'])
                    if best_cost:
                        individual_signs.append({
                            'sign_name': sign_cost['sign_name'],
                            'quantity': sign_row['quantity'],
                            'unit_cost': best_cost['total_cost'] / sign_row['quantity'],
                            'total_cost': best_cost['total_cost'],
                            'pricing_method': best_cost['method']
                        })
                        line_total = best_cost['total_cost']
            
            individual_total += line_total
        
        # Calculate sign groups
        group_signs = []
        group_total = 0
        
        groups_query = '''
            SELECT bsg.*, sg.name as group_name
            FROM building_sign_groups bsg
            JOIN sign_groups sg ON bsg.group_id = sg.id
            WHERE bsg.building_id = ?
        '''
        groups_df = pd.read_sql_query(groups_query, conn, params=(building_id,))
        
        for _, group_row in groups_df.iterrows():
            group_cost = self.calculate_group_cost(
                group_row['group_id'],
                group_row['quantity']
            )
            
            if 'error' not in group_cost:
                group_signs.append({
                    'group_name': group_cost['group_name'],
                    'quantity': group_row['quantity'],
                    'cost_per_group': group_cost['cost_per_group'],
                    'total_cost': group_cost['total_cost'],
                    'signs_breakdown': group_cost['signs_in_group']
                })
                group_total += group_cost['total_cost']
        
        conn.close()
        
        return {
            'building_name': building['name'],
            'building_description': building['description'],
            'individual_signs': individual_signs,
            'individual_signs_total': individual_total,
            'sign_groups': group_signs,
            'sign_groups_total': group_total,
            'building_subtotal': individual_total + group_total
        }
    
    def calculate_project_cost(self, project_id: int, 
                              include_installation: bool = None,
                              include_sales_tax: bool = None) -> Dict:
        """Calculate comprehensive project cost with all options."""
        conn = sqlite3.connect(self.db_path)
        
        # Get project details
        project_query = "SELECT * FROM projects WHERE id = ?"
        project_df = pd.read_sql_query(project_query, conn, params=(project_id,))
        
        if project_df.empty:
            conn.close()
            return {"error": "Project not found"}
        
        project = project_df.iloc[0]
        
        # Use project settings if not overridden
        if include_installation is None:
            include_installation = bool(project['include_installation'])
        if include_sales_tax is None:
            include_sales_tax = bool(project['include_sales_tax'])
        
        # Calculate costs for all buildings
        buildings_query = "SELECT id FROM buildings WHERE project_id = ?"
        buildings_df = pd.read_sql_query(buildings_query, conn, params=(project_id,))
        
        buildings_costs = []
        subtotal = 0
        
        for _, building_row in buildings_df.iterrows():
            building_cost = self.calculate_building_cost(building_row['id'])
            if 'error' not in building_cost:
                buildings_costs.append(building_cost)
                subtotal += building_cost['building_subtotal']
        
        # Calculate additional costs
        installation_cost = 0
        if include_installation and project['installation_rate']:
            installation_cost = subtotal * project['installation_rate']
        
        pretax_total = subtotal + installation_cost
        
        sales_tax = 0
        if include_sales_tax and project['sales_tax_rate']:
            sales_tax = pretax_total * project['sales_tax_rate']
        
        final_total = pretax_total + sales_tax
        
        conn.close()
        
        return {
            'project_name': project['name'],
            'project_description': project['description'],
            'buildings': buildings_costs,
            'signs_subtotal': subtotal,
            'installation_cost': installation_cost,
            'installation_rate': project['installation_rate'],
            'pretax_total': pretax_total,
            'sales_tax': sales_tax,
            'sales_tax_rate': project['sales_tax_rate'],
            'final_total': final_total,
            'cost_breakdown': {
                'signs': subtotal,
                'installation': installation_cost,
                'tax': sales_tax,
                'total': final_total
            }
        }
