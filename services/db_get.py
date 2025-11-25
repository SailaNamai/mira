# services.db_get.py

from services.db_access import connect
import sqlite3

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
                    "carbohydrates_100g": raw.get("carbohydrates_100g"),
                    "carbohydrates_serving": raw.get("carbohydrates_serving"),
                    "fat_100g": raw.get("fat_100g"),
                    "fat_serving": raw.get("fat_serving"),
                    "proteins_100g": raw.get("proteins_100g"),
                    "proteins_serving": raw.get("proteins_serving"),
                },
                "quantity": raw.get("quantity"), # how many single items
                "serving_size": raw.get("serving_size"),
                "packaging_text": raw.get("packaging_text"),
                "product_quantity": raw.get("product_quantity"), # how much product in total
                "portion_description": raw.get("portion_description")
            }

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
