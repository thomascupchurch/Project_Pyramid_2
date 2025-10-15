"""
Cost calculation utilities for the Sign Estimation Application.
Handles various pricing models and estimation calculations.
"""

from typing import Dict, List, Tuple, Optional
import sqlite3
import pandas as pd


class CostCalculator:
    def __init__(self, db_path: str = "sign_estimation.db"):
        self.db_path = db_path

    def calculate_sign_cost(
        self,
        sign_type_id: int,
        quantity: int = 1,
        custom_dimensions: Optional[Tuple[float, float]] = None,
        custom_material: Optional[str] = None,
    ) -> Dict:
        """Calculate cost for individual signs with multiple pricing methods."""
        conn = sqlite3.connect(self.db_path)
        try:
            sign_df = pd.read_sql_query(
                "SELECT * FROM sign_types WHERE id = ?",
                conn,
                params=(sign_type_id,),
            )
            if sign_df.empty:
                return {"error": "Sign type not found"}
            sign = sign_df.iloc[0]

            # Dimensions and area
            if custom_dimensions:
                width, height = custom_dimensions
            else:
                width, height = sign.get("width"), sign.get("height")
            area = (width or 0) * (height or 0)

            material = custom_material if custom_material else sign.get("material")

            cost_methods: Dict[str, Dict] = {}
            # 1) Unit price
            unit_price = float(sign.get("unit_price") or 0)
            if unit_price:
                cost_methods["unit_price"] = {
                    "method": "Unit Price",
                    "unit_cost": unit_price,
                    "quantity": quantity,
                    "total_cost": unit_price * quantity,
                    "details": f"${unit_price:.2f} per unit × {quantity} units",
                }

            # 2) Sign's own ppsf
            ppsf_sign = float(sign.get("price_per_sq_ft") or 0)
            if ppsf_sign and area > 0:
                cost_methods["sq_ft_sign"] = {
                    "method": "Square Foot (Sign Type)",
                    "price_per_sq_ft": ppsf_sign,
                    "area": area,
                    "quantity": quantity,
                    "total_cost": ppsf_sign * area * quantity,
                    "details": f"${ppsf_sign:.2f}/sq ft × {area:.2f} sq ft × {quantity} units",
                }

            # 3) Material pricing table
            if material and area > 0:
                mat_df = pd.read_sql_query(
                    "SELECT price_per_sq_ft FROM material_pricing WHERE material_name = ?",
                    conn,
                    params=(material,),
                )
                if not mat_df.empty:
                    mat_ppsf = float(mat_df.iloc[0]["price_per_sq_ft"] or 0)
                    cost_methods["sq_ft_material"] = {
                        "method": "Square Foot (Material)",
                        "price_per_sq_ft": mat_ppsf,
                        "area": area,
                        "quantity": quantity,
                        "total_cost": mat_ppsf * area * quantity,
                        "details": f"${mat_ppsf:.2f}/sq ft × {area:.2f} sq ft × {quantity} units",
                    }

            return {
                "sign_name": sign.get("name"),
                "material": material,
                "dimensions": f"{width} × {height}" if width and height else "Not specified",
                "area": area,
                "quantity": quantity,
                "cost_methods": cost_methods,
            }
        finally:
            conn.close()

    def get_best_cost_method(self, cost_methods: Dict) -> Optional[Dict]:
        """Pick the preferred method in priority order."""
        priority = ["unit_price", "sq_ft_material", "sq_ft_sign"]
        for key in priority:
            if key in cost_methods:
                return cost_methods[key]
        if cost_methods:
            first_key = sorted(cost_methods.keys())[0]
            return cost_methods[first_key]
        return None

    # Additional helpers kept for completeness; not used by current tests
    def calculate_group_cost(self, group_id: int, quantity: int = 1) -> Dict:
        conn = sqlite3.connect(self.db_path)
        try:
            group_df = pd.read_sql_query(
                "SELECT * FROM sign_groups WHERE id = ?", conn, params=(group_id,)
            )
            if group_df.empty:
                return {"error": "Sign group not found"}
            group = group_df.iloc[0]
            members_df = pd.read_sql_query(
                """
                SELECT st.*, sgm.quantity as group_quantity
                FROM sign_group_members sgm
                JOIN sign_types st ON sgm.sign_type_id = st.id
                WHERE sgm.group_id = ?
                """,
                conn,
                params=(group_id,),
            )
            group_cost_breakdown = []
            total_group_cost = 0.0
            for _, member in members_df.iterrows():
                sign_cost = self.calculate_sign_cost(member["id"], member["group_quantity"])  # type: ignore[index]
                if "error" not in sign_cost:
                    best = self.get_best_cost_method(sign_cost["cost_methods"])  # type: ignore[index]
                    if best:
                        group_cost_breakdown.append(
                            {
                                "sign_name": sign_cost["sign_name"],
                                "quantity_in_group": member["group_quantity"],
                                "cost_per_unit": best["total_cost"] / member["group_quantity"],
                                "total_cost": best["total_cost"],
                                "method_used": best["method"],
                            }
                        )
                        total_group_cost += best["total_cost"]
            return {
                "group_name": group["name"],
                "group_description": group["description"],
                "signs_in_group": group_cost_breakdown,
                "cost_per_group": total_group_cost,
                "total_quantity": quantity,
                "total_cost": total_group_cost * quantity,
            }
        finally:
            conn.close()

    def calculate_building_cost(self, building_id: int) -> Dict:
        conn = sqlite3.connect(self.db_path)
        try:
            building_df = pd.read_sql_query(
                "SELECT * FROM buildings WHERE id = ?", conn, params=(building_id,)
            )
            if building_df.empty:
                return {"error": "Building not found"}
            building = building_df.iloc[0]
            individual_signs: List[Dict] = []
            individual_total = 0.0
            signs_df = pd.read_sql_query(
                """
                SELECT bs.*, st.name as sign_name
                FROM building_signs bs
                JOIN sign_types st ON bs.sign_type_id = st.id
                WHERE bs.building_id = ?
                """,
                conn,
                params=(building_id,),
            )
            for _, sign_row in signs_df.iterrows():
                if sign_row["custom_price"]:
                    line_total = sign_row["custom_price"] * sign_row["quantity"]
                    individual_signs.append(
                        {
                            "sign_name": sign_row["sign_name"],
                            "quantity": sign_row["quantity"],
                            "unit_cost": sign_row["custom_price"],
                            "total_cost": line_total,
                            "pricing_method": "Custom Price",
                        }
                    )
                else:
                    sign_cost = self.calculate_sign_cost(
                        sign_row["sign_type_id"], sign_row["quantity"]
                    )
                    if "error" not in sign_cost:
                        best = self.get_best_cost_method(sign_cost["cost_methods"])  # type: ignore[index]
                        if best:
                            individual_signs.append(
                                {
                                    "sign_name": sign_cost["sign_name"],
                                    "quantity": sign_row["quantity"],
                                    "unit_cost": best["total_cost"] / sign_row["quantity"],
                                    "total_cost": best["total_cost"],
                                    "pricing_method": best["method"],
                                }
                            )
                            line_total = best["total_cost"]
                            individual_total += line_total

            # Groups
            group_signs: List[Dict] = []
            group_total = 0.0
            groups_df = pd.read_sql_query(
                """
                SELECT bsg.*, sg.name as group_name
                FROM building_sign_groups bsg
                JOIN sign_groups sg ON bsg.group_id = sg.id
                WHERE bsg.building_id = ?
                """,
                conn,
                params=(building_id,),
            )
            for _, group_row in groups_df.iterrows():
                group_cost = self.calculate_group_cost(
                    group_row["group_id"], group_row["quantity"]
                )
                if "error" not in group_cost:
                    group_signs.append(
                        {
                            "group_name": group_cost["group_name"],
                            "quantity": group_row["quantity"],
                            "cost_per_group": group_cost["cost_per_group"],
                            "total_cost": group_cost["total_cost"],
                            "signs_breakdown": group_cost["signs_in_group"],
                        }
                    )
                    group_total += group_cost["total_cost"]

            return {
                "building_name": building["name"],
                "building_description": building["description"],
                "individual_signs": individual_signs,
                "individual_signs_total": individual_total,
                "sign_groups": group_signs,
                "sign_groups_total": group_total,
                "building_subtotal": individual_total + group_total,
            }
        finally:
            conn.close()

    def calculate_project_cost(
        self, project_id: int, include_installation: bool = None, include_sales_tax: bool = None
    ) -> Dict:
        conn = sqlite3.connect(self.db_path)
        try:
            project_df = pd.read_sql_query(
                "SELECT * FROM projects WHERE id = ?", conn, params=(project_id,)
            )
            if project_df.empty:
                return {"error": "Project not found"}
            project = project_df.iloc[0]
            if include_installation is None:
                include_installation = bool(project["include_installation"])
            if include_sales_tax is None:
                include_sales_tax = bool(project["include_sales_tax"])
            buildings_df = pd.read_sql_query(
                "SELECT id FROM buildings WHERE project_id = ?", conn, params=(project_id,)
            )
            buildings_costs: List[Dict] = []
            subtotal = 0.0
            for _, br in buildings_df.iterrows():
                bc = self.calculate_building_cost(br["id"])  # type: ignore[index]
                if "error" not in bc:
                    buildings_costs.append(bc)
                    subtotal += bc["building_subtotal"]
            installation_cost = 0.0
            if include_installation and project["installation_rate"]:
                installation_cost = subtotal * project["installation_rate"]
            pretax_total = subtotal + installation_cost
            sales_tax = 0.0
            if include_sales_tax and project["sales_tax_rate"]:
                sales_tax = pretax_total * project["sales_tax_rate"]
            final_total = pretax_total + sales_tax
            return {
                "project_name": project["name"],
                "project_description": project["description"],
                "buildings": buildings_costs,
                "signs_subtotal": subtotal,
                "installation_cost": installation_cost,
                "installation_rate": project["installation_rate"],
                "pretax_total": pretax_total,
                "sales_tax": sales_tax,
                "sales_tax_rate": project["sales_tax_rate"],
                "final_total": final_total,
                "cost_breakdown": {
                    "signs": subtotal,
                    "installation": installation_cost,
                    "tax": sales_tax,
                    "total": final_total,
                },
            }
        finally:
            conn.close()


# ------------------ Helper functions used elsewhere ------------------ #
def compute_unit_price(row: Dict, price_mode: str) -> float:
    """Compute unit price for a sign or group member based on pricing mode."""
    def _f(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    if price_mode == "per_area":
        width = _f(row.get("width"))
        height = _f(row.get("height"))
        area = width * height if width and height else 0
        if area > 0:
            ppsf = _f(row.get("price_per_sq_ft"))
            if ppsf <= 0:
                ppsf = _f(row.get("material_multiplier"))
            if ppsf > 0:
                return area * ppsf
    return _f(row.get("unit_price"))


def compute_install_cost(
    install_mode: str,
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
    auto_install_hours: float,
) -> float:
    """Centralized installation cost computation with auto fallback handling."""
    install_cost = 0.0
    if install_mode == "percent":
        install_cost = grand_subtotal * (inst_percent / 100.0)
    elif install_mode == "per_sign":
        if inst_per_sign > 0:
            install_cost = total_sign_count * inst_per_sign
        elif auto_enabled and auto_install_amount_per_sign > 0:
            install_cost = auto_install_amount_per_sign
    elif install_mode == "per_area":
        install_cost = total_area * inst_per_area
    elif install_mode == "hours":
        if inst_hours > 0:
            install_cost = inst_hours * inst_hourly
        elif auto_enabled and auto_install_hours > 0:
            install_cost = auto_install_hours * inst_hourly
    return install_cost
