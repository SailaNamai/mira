# services.db_get.py

import sqlite3
import json
from datetime import date
from services.db_access import connect, BASE

# Path to reduced USDA dataset
REDUCED_FOUNDATION_FOODS = BASE / "static" / "nutrition" / "FoundationFoods.json"
REDUCED_BRANDED_FOODS = BASE / "static" / "nutrition" / "BrandedFoods.json"

# Load once at import, keep separate
def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        print(f"Warning: could not parse {path}: {e}")
        return []

foundation_foods = _load_json(REDUCED_FOUNDATION_FOODS)
branded_foods = _load_json(REDUCED_BRANDED_FOODS)

# json search helper
def _search_json(term: str, foods: list, source_id: int):
    """Search a single JSON dataset and tag with source_id."""
    results = []
    term_lower = term.lower()
    for food in foods:
        desc = food.get("description", "").lower()
        if term_lower in desc:
            results.append({
                "id": source_id,
                "barcode": None,
                "product_name": food.get("description"),
                "quantity": None,
                "serving_size": None,
                "product_quantity": None,
                "nutriments": {
                    "energy_kcal_100g": food.get("kcal_100g"),
                    "carbohydrates_100g": food.get("carbs_100g"),
                    "fat_100g": food.get("fat_100g"),
                    "proteins_100g": food.get("protein_100g"),
                }
            })
    return results

def food_search(term: str):
    results = []

    # Local DB
    with connect(readonly=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM nutrition_items WHERE product_name LIKE ? ORDER BY id DESC",
            (f"%{term}%",)
        ).fetchall()
        for row in rows:
            r = dict(row)
            results.append({
                "id": r["id"],  # keep DB IDs as-is
                "barcode": r["barcode"],
                "product_name": r["product_name"],
                "quantity": r["quantity"],
                "serving_size": r["serving_size"],
                "product_quantity": r["product_quantity"],
                "nutriments": {
                    "energy_kcal_100g": r.get("energy_kcal_100g"),
                    "carbohydrates_100g": r.get("carbohydrates_100g"),
                    "fat_100g": r.get("fat_100g"),
                    "proteins_100g": r.get("proteins_100g"),
                }
            })

    # JSON datasets separately
    if foundation_foods: results.extend(_search_json(term, foundation_foods, source_id=0))
    if branded_foods: results.extend(_search_json(term, branded_foods, source_id=-1))

    # Sort by ID (DB entries first, then FoundationFoods, then BrandedFoods)
    # DB entries have positive ID starting with 1, Foundation as 0, Branded as -1
    # Frontend displays from highest to lowest ID: 1. DB, 2. FF, 3. BF
    results.sort(key=lambda r: r["id"], reverse=False) # False=ASC, True=DSC
    return results

def get_settings():
    # repopulate the settings-modal
    with connect(readonly=True) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        return dict(row) if row else {}

class GetDB:
    @staticmethod
    def _get_single_value(column: str):
        with connect(readonly=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(f"SELECT {column} FROM settings WHERE id = 1").fetchone()
            return row[column] if row and column in row.keys() else None

    @staticmethod
    def get_smart_plugs():
        with connect(readonly=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT smart_plug1_name, smart_plug1_ip,
                       smart_plug2_name, smart_plug2_ip,
                       smart_plug3_name, smart_plug3_ip,
                       smart_plug4_name, smart_plug4_ip
                FROM settings WHERE id = 1
            """).fetchone()
            return dict(row) if row else {}

    @staticmethod
    def get_stt():
        return GetDB._get_single_value("stt")

    @staticmethod
    def get_stt_mode():
        return GetDB._get_single_value("stt_mode")

    @staticmethod
    def get_llm():
        return GetDB._get_single_value("llm")

    @staticmethod
    def get_llm_mode():
        return GetDB._get_single_value("llm_mode")

    @staticmethod
    def get_llm_vl():
        return GetDB._get_single_value("llm_vl")

    @staticmethod
    def get_llm_vl_mode():
        return GetDB._get_single_value("llm_vl_mode")

    @staticmethod
    def get_tts():
        return GetDB._get_single_value("tts")

    @staticmethod
    def get_tts_mode():
        return GetDB._get_single_value("tts_mode")

    @staticmethod
    def get_user_name():
        return GetDB._get_single_value("user_name")

    @staticmethod
    def get_user_birthday():
        return GetDB._get_single_value("user_birthday")

    @staticmethod
    def get_location():
        with connect(readonly=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT location_city, location_latitude, location_longitude
                FROM settings WHERE id = 1
            """).fetchone()
            return dict(row) if row else {}

    @staticmethod
    def get_schedule(day: str):
        column = f"schedule_{day.lower()}"
        return GetDB._get_single_value(column)

    @staticmethod
    def get_additional_info():
        return GetDB._get_single_value("additional_info")

    @staticmethod
    def get_nutri_item(barcode: str):
        if not barcode:
            return None

        with connect(readonly=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT *
                FROM nutrition_items
                WHERE barcode = ?
                ORDER BY last_update DESC
                LIMIT 1
            """, (barcode,)).fetchone()

            if not row:
                return None

            raw = dict(row)

            return {
                "barcode": raw.get("barcode"),
                "product_name": raw.get("product_name"),
                "nutriments": {
                    "energy_kcal_100g": raw.get("energy_kcal_100g"),
                    "energy_kcal_serving": raw.get("energy_kcal_serving"),
                    "energy_kcal_unit": raw.get("energy_kcal_unit"),
                    "carbohydrates_100g": raw.get("carbohydrates_100g"),
                    "fat_100g": raw.get("fat_100g"),
                    "proteins_100g": raw.get("proteins_100g"),
                },
                "quantity": raw.get("quantity"), # how many single items
                "serving_size": raw.get("serving_size"),
                "product_quantity": raw.get("product_quantity"), # how much product in total
            }

    @staticmethod
    def get_today_nutrition_totals(date_str: str = None) -> dict:
        """
        Returns summed nutrition totals for a given date (defaults to today).
        Only kcal, carbs, fat, protein — no individual rows or product names.

        Example return:
        {
            "kcal": 2140,
            "carbs": 282,
            "fat": 78,
            "protein": 134
        }
        """
        if date_str is None:
            # Today in YYYY-MM-DD format (matches your DB default)
            date_str = date.today().isoformat()

        try:
            with connect(readonly=True) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("""
                    SELECT 
                        COALESCE(SUM(kcal_consumed), 0)     AS total_kcal,
                        COALESCE(SUM(carbs_consumed), 0)    AS total_carbs,
                        COALESCE(SUM(fat_consumed), 0)      AS total_fat,
                        COALESCE(SUM(protein_consumed), 0)  AS total_protein
                    FROM nutrition_intake
                    WHERE the_date = ?
                """, (date_str,)).fetchone()

            totals = {
                "kcal": int(row["total_kcal"]),
                "carbs": int(row["total_carbs"]),
                "fat": int(row["total_fat"]),
                "protein": int(row["total_protein"])
            }

            print(f"[DB] Today ({date_str}) nutrition totals: {totals}")
            return totals

        except Exception as e:
            print(f"[DB] Failed to get today nutrition totals: {e}")
            import traceback
            traceback.print_exc()
            # Return zeros on error — UI stays safe
            return {"kcal": 0, "carbs": 0, "fat": 0, "protein": 0}

    @staticmethod
    def get_today_consumed_items(date_str: str = None) -> list[dict]:
        """
        Returns the full list of individual items consumed today.
        Used by the log history dialog to display and edit entries.

        Expected return format:
        [
            {
                "id": 1,
                "product_name": "Banana",
                "quantity_consumed": 150
            },
            {
                "id": 2,
                "product_name": "Whole Milk",
                "quantity_consumed": 250
            },
            ...
        ]
        """
        if date_str is None:
            date_str = date.today().isoformat()  # YYYY-MM-DD

        try:
            with connect(readonly=True) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT 
                        id,
                        product_name,
                        quantity_consumed
                    FROM nutrition_intake
                    WHERE the_date = ?
                      AND quantity_consumed > 0  -- optional: hide zeroed entries
                    ORDER BY id DESC
                """, (date_str,)).fetchall()

            items = [
                {
                    "id": int(row["id"]),
                    "product_name": row["product_name"] or "Unknown Item",
                    "quantity_consumed": int(row["quantity_consumed"])
                }
                for row in rows
            ]

            print(f"[DB] Loaded {len(items)} consumed items for {date_str}")
            return items

        except Exception as e:
            print(f"[DB] Failed to get today's consumed items: {e}")
            import traceback
            traceback.print_exc()
            return []  # Return empty list on error — UI shows "No items"

    @staticmethod
    def get_nutrition_user_values():
        with connect(readonly=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT *
                FROM nutrition_user_values
                WHERE id = 1
            """).fetchone()

            if not row:
                return {}

            raw = dict(row)
            return {
                k: (v if isinstance(v, int) and v is not None else 0)
                for k, v in raw.items()
            }

    @staticmethod
    def get_nutrition_intake_today():
        with connect(readonly=True) as conn:
            today = conn.execute("SELECT strftime('%Y-%m-%d', 'now')").fetchone()[0]
            row = conn.execute("""
                SELECT kcal_total, carbs_total, fat_total, protein_total
                FROM nutrition_intake
                WHERE the_date = ?
            """, (today,)).fetchone()
            if not row:
                return {"kcal": 0, "carbs": 0, "fat": 0, "protein": 0}
            return {
                "kcal": row[0] or 0,
                "carbs": row[1] or 0,
                "fat": row[2] or 0,
                "protein": row[3] or 0
            }
