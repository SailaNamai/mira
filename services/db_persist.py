# services.db_persist.py

from services.db_access import write_connection, connect
from datetime import datetime

def update_package_item_count(barcode, package_item_count):
    return

def add_nutrition_intake(grams: float, nutriments: dict):
    """
    Adds intake for today.
    nutriments keys expected:
      'energy_kcal_100g', 'carbohydrates_100g', 'fat_100g', 'proteins_100g'
    """
    factor = grams / 100.0
    kcal = round((nutriments.get('energy_kcal_100g') or 0) * factor)
    carbs = round(((nutriments.get('carbohydrates_100g') or 0) * factor) * 10) / 10  # keep 1 decimal
    fat = round(((nutriments.get('fat_100g') or 0) * factor) * 10) / 10
    protein = round(((nutriments.get('proteins_100g') or 0) * factor) * 10) / 10

    with write_connection() as conn:
        cur = conn.cursor()
        today = conn.execute("SELECT strftime('%Y-%m-%d', 'now')").fetchone()[0]

        # Get current intake (could be NULL)
        cur.execute("""
            SELECT kcal_total, carbs_total, fat_total, protein_total
            FROM nutrition_intake
            WHERE the_date = ?
        """, (today,))
        row = cur.fetchone()

        if row:
            # Update
            kcal += row[0] or 0
            carbs += row[1] or 0
            fat += row[2] or 0
            protein += row[3] or 0

            cur.execute("""
                UPDATE nutrition_intake
                SET kcal_total = ?, carbs_total = ?, fat_total = ?, protein_total = ?
                WHERE the_date = ?
            """, (kcal, carbs, fat, protein, today))
        else:
            # Insert new
            cur.execute("""
                INSERT INTO nutrition_intake (the_date, kcal_total, carbs_total, fat_total, protein_total)
                VALUES (?, ?, ?, ?, ?)
            """, (today, kcal, carbs, fat, protein))

        conn.commit()

        return {
            "kcal_total": kcal,
            "carbs_total": carbs,
            "fat_total": fat,
            "protein_total": protein,
            "date": today
        }

def save_nutrition_user_values(data: dict):
    """
    Validates and persists the singleton row in nutrition_user_values.
    """
    try:
        kcal = int(data.get("kcal", 0))
        carbs = int(data.get("carbs", 0))
        fat = int(data.get("fat", 0))
        protein = int(data.get("protein", 0))
    except (TypeError, ValueError):
        raise ValueError("Invalid input types")

    if not all([kcal, carbs, fat, protein]):
        raise ValueError("Missing or zero values")

    with write_connection() as conn:
        conn.execute("DELETE FROM nutrition_user_values WHERE id = 1")
        conn.execute("""
            INSERT INTO nutrition_user_values (
                id, kcal_allowed, carbs_allowed, fat_allowed, protein_allowed
            ) VALUES (1, ?, ?, ?, ?)
        """, (kcal, carbs, fat, protein))

def persist_nutri_item_values(nutri_data: dict) -> None:
    if not nutri_data or not nutri_data.get("barcode"):
        print("[DB] No valid nutrition data to persist.")
        return

    barcode = nutri_data["barcode"]

    try:
        with write_connection() as conn:
            # Check if barcode already exists
            existing = conn.execute(
                "SELECT 1 FROM nutrition_items WHERE barcode = ? LIMIT 1", (barcode,)
            ).fetchone()
            if existing:
                print(f"[DB] Barcode already exists: {barcode}")
                return

            fields = [
                "barcode", "product_name", "quantity", "product_quantity", "serving_size",
                "energy_kcal_100g", "energy_kcal_serving",
                "carbohydrates_100g", "carbohydrates_serving",
                "fat_100g", "fat_serving",
                "proteins_100g", "proteins_serving"
            ]

            nut = nutri_data.get("nutriments", {})
            values = [
                nutri_data.get("barcode"),
                nutri_data.get("product_name"),
                nutri_data.get("quantity"),
                # product_quantity might be numeric in some sources; coerce if you want:
                nutri_data.get("product_quantity"),
                nutri_data.get("serving_size"),

                # nutriments:
                nut.get("energy_kcal_100g"),
                nut.get("energy_kcal_serving"),
                nut.get("carbohydrates_100g"),
                nut.get("carbohydrates_serving"),
                nut.get("fat_100g"),
                nut.get("fat_serving"),
                nut.get("proteins_100g"),
                nut.get("proteins_serving"),
            ]

            placeholders = ", ".join(["?" for _ in fields])
            query = f"INSERT INTO nutrition_items ({', '.join(fields)}) VALUES ({placeholders})"
            conn.execute(query, values)
            print(f"[DB] Nutrition data persisted for barcode: {barcode}")

    except Exception as e:
        print(f"[DB] Error persisting nutrition data: {e}")


def save_settings(data: dict):
    """
    Overwrites the singleton settings row with normalized data.
    """
    # Normalize specific fields
    data['user_birthday'] = _normalize_birthday(data.get('user_birthday', ''))
    data['location_latitude'] = _normalize_coordinate(data.get('location_latitude', ''))
    data['location_longitude'] = _normalize_coordinate(data.get('location_longitude', ''))

    with write_connection() as conn:
        conn.execute("DELETE FROM settings WHERE id = 1")

        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        values = list(data.values())

        conn.execute(
            f"INSERT INTO settings (id, {columns}) VALUES (1, {placeholders})",
            values
        )

def _normalize_birthday(value: str) -> str:
    """
    Normalize birthday to dd.mm.YYYY format.
    Accepts common formats like YYYY-mm-dd, dd/mm/YYYY, etc.
    """
    if not value.strip():
        return ''
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            continue
    return value.strip()  # fallback if parsing fails

def _normalize_coordinate(value: str) -> str:
    """
    Replace comma with dot in latitude/longitude values.
    """
    return value.strip().replace(',', '.') if value else ''
