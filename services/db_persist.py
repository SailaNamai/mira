# services.db_persist.py

import sqlite3
from services.db_access import write_connection, connect
from datetime import datetime, date

def update_today_consumed_items(updated_items: list[dict], date_str: str = None) -> bool:
    """
    Updates quantity and proportionally recalculates consumed macros.
    Items not in updated_items are deleted.
    """
    if date_str is None:
        date_str = date.today().isoformat()

    try:
        # Step 1: Fetch current items with full nutrient data
        with connect(readonly=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, quantity_consumed,
                       kcal_consumed, carbs_consumed, fat_consumed, protein_consumed
                FROM nutrition_intake
                WHERE the_date = ?
            """, (date_str,)).fetchall()

            current_items = {
                row["id"]: {
                    "quantity_consumed": int(row["quantity_consumed"] or 0),
                    "kcal_consumed": int(row["kcal_consumed"] or 0),
                    "carbs_consumed": int(row["carbs_consumed"] or 0),
                    "fat_consumed": int(row["fat_consumed"] or 0),
                    "protein_consumed": int(row["protein_consumed"] or 0)
                }
                for row in rows
            }
            existing_ids = set(current_items.keys())

        incoming_ids = {item["id"] for item in updated_items if "id" in item}
        ids_to_delete = existing_ids - incoming_ids
        ids_to_update = incoming_ids & existing_ids

        with write_connection() as conn:
            # Delete removed items
            if ids_to_delete:
                placeholders = ",".join("?" for _ in ids_to_delete)
                conn.execute(f"DELETE FROM nutrition_intake WHERE id IN ({placeholders})", tuple(ids_to_delete))
                print(f"[DB] Deleted {len(ids_to_delete)} item(s)")

            # Update quantities + scale macros
            for item in updated_items:
                item_id = item["id"]
                new_qty = int(item["quantity_consumed"])

                if item_id not in current_items or new_qty <= 0:
                    continue  # safety

                old = current_items[item_id]
                old_qty = old["quantity_consumed"]

                if old_qty == 0:
                    continue  # avoid divide by zero

                ratio = new_qty / old_qty

                conn.execute("""
                    UPDATE nutrition_intake
                    SET quantity_consumed = ?,
                        kcal_consumed     = ROUND(? * ?),
                        carbs_consumed    = ROUND(? * ?),
                        fat_consumed      = ROUND(? * ?),
                        protein_consumed  = ROUND(? * ?)
                    WHERE id = ?
                """, (
                    new_qty,
                    old["kcal_consumed"], ratio,
                    old["carbs_consumed"], ratio,
                    old["fat_consumed"], ratio,
                    old["protein_consumed"], ratio,
                    item_id
                ))

            print(f"[DB] Updated {len(ids_to_update)} item(s) with scaled macros")

        return True

    except Exception as e:
        print(f"[DB] Failed to update consumed items with recalc: {e}")
        import traceback
        traceback.print_exc()
        return False

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

def persist_nutrition_intake(intake_data: dict, user_id: int = None) -> bool:
    """
    Logs consumption into nutrition_intake table.
    Normalizes missing/empty/invalid values to 0 (as is standard in food DBs).
    """
    required = [
        "product_name",
        "quantity_consumed",
        "kcal_consumed",
        "carbs_consumed",
        "fat_consumed",
        "protein_consumed"
    ]

    # Check that the keys exist
    if not all(k in intake_data for k in required):
        print(f"[DB] Missing required fields for nutrition_intake: {intake_data}")
        return False

    # Helper: Normalize to 0 if None, empty, '-', or invalid
    def safe_round(value):
        if value is None or value == "" or value == "-":
            return 0
        try:
            return round(float(value))
        except (ValueError, TypeError):
            return 0  # e.g. "abc" → 0

    # Extract & normalize
    product_name = intake_data["product_name"] or "Unknown"
    quantity = max(0, safe_round(intake_data["quantity_consumed"]))
    kcal     = max(0, safe_round(intake_data["kcal_consumed"]))
    carbs    = max(0, safe_round(intake_data["carbs_consumed"]))
    fat      = max(0, safe_round(intake_data["fat_consumed"]))
    protein  = max(0, safe_round(intake_data["protein_consumed"]))

    try:
        with write_connection() as conn:
            conn.execute("""
                INSERT INTO nutrition_intake (
                    product_name,
                    the_date,
                    quantity_consumed,
                    kcal_consumed,
                    carbs_consumed,
                    fat_consumed,
                    protein_consumed
                ) VALUES (?, strftime('%Y-%m-%d', 'now'), ?, ?, ?, ?, ?)
            """, (
                product_name,
                quantity,
                kcal,
                carbs,
                fat,
                protein
            ))
            conn.commit()

        print(f"[Nutrition Intake] Logged: {product_name} | "
              f"{quantity}g | {kcal}kcal | {protein}g protein")

        return True

    except Exception as e:
        print(f"[DB] Failed to insert into nutrition_intake: {e}")
        import traceback
        traceback.print_exc()
        return False

def persist_nutri_item(nutri_data: dict) -> None:
    """
    Insert new product or UPDATE existing one only if data differs.
    Refreshes last_update on change.
    """
    if not nutri_data or not nutri_data.get("barcode"):
        print("[DB] No valid nutrition data to persist.")
        return

    barcode = nutri_data["barcode"]
    nutriments = nutri_data.get("nutriments", {})

    # Values in the exact order of the SELECT below
    new_values = (
        nutri_data.get("product_name"),
        nutri_data.get("quantity"),
        nutri_data.get("serving_size"),
        nutri_data.get("product_quantity"),
        nutriments.get("energy_kcal_100g"),
        nutriments.get("carbohydrates_100g"),
        nutriments.get("fat_100g"),
        nutriments.get("proteins_100g"),
    )

    try:
        with write_connection() as conn:
            # 1. Fetch current stored data (excluding barcode and last_update)
            current = conn.execute("""
                SELECT product_name, quantity, serving_size, product_quantity,
                       energy_kcal_100g, carbohydrates_100g, fat_100g, proteins_100g
                FROM nutrition_items
                WHERE barcode = ?
            """, (barcode,)).fetchone()

            # 2. If identical → skip entirely
            if current and current == new_values:
                print(f"[DB] Product {barcode} unchanged (last_update: {conn.execute('SELECT last_update FROM nutrition_items WHERE barcode = ?', (barcode,)).fetchone()[0]}). Skipping.")
                return

            # 3. Either INSERT (new) or UPDATE (changed)
            if current:
                # UPDATE + refresh last_update
                conn.execute("""
                    UPDATE nutrition_items SET
                        product_name = ?,
                        quantity = ?,
                        serving_size = ?,
                        product_quantity = ?,
                        energy_kcal_100g = ?,
                        carbohydrates_100g = ?,
                        fat_100g = ?,
                        proteins_100g = ?,
                        last_update = strftime('%Y-%m-%d at %H:%M','now','localtime')
                    WHERE barcode = ?
                """, (*new_values, barcode))
                action = "updated"
            else:
                # INSERT new – last_update will use DEFAULT
                conn.execute("""
                    INSERT INTO nutrition_items (
                        barcode, product_name, quantity, serving_size, product_quantity,
                        energy_kcal_100g, carbohydrates_100g, fat_100g, proteins_100g
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (barcode, *new_values))
                action = "inserted"

            conn.commit()
            print(f"[DB] Product {barcode} {action}: {nutri_data.get('product_name')} "
                  f"| last_update refreshed")

    except Exception as e:
        print(f"[DB] Failed to persist nutrition item: {e}")
        import traceback
        traceback.print_exc()


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
