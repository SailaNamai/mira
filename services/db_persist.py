# services.db_persist.py

import sqlite3
from services.db_access import write_connection, connect
from services.passkeys import ALLOWED_KEYS
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

########################################################################################
"""##########################     Settings-Modal/User    ############################"""
########################################################################################
def init_users():
    """
    Initialize users from services/passkeys.py:
    1. Overwrite default user (ID=1) if its name is still 'Default User'
    2. Check all user_names from passkeys.py against existing users in DB
        2.1. Create users that doesn't exist in DB
        2.2. Remove users from DB that are not in passkeys.py
    3. Allowed keys data structure:
        ALLOWED_KEYS = [
        {"user_name": "whatever_you_like", "password": "your_password_here"},
        {"user_name": "how_many_you_like", "password": "another_password_here"},
        ]
    4. Schema.sql excerpt:
        -- User Info
        CREATE TABLE IF NOT EXISTS user_info (
          id                  INTEGER PRIMARY KEY AUTOINCREMENT,
          user_name           TEXT,
          user_birthday       TEXT,
          location_city       TEXT,
          location_latitude   TEXT,
          location_longitude  TEXT,
          schedule_monday     TEXT,
          schedule_tuesday    TEXT,
          schedule_wednesday  TEXT,
          schedule_thursday   TEXT,
          schedule_friday     TEXT,
          schedule_saturday   TEXT,
          schedule_sunday     TEXT,
          additional_info     TEXT
        );
    5. Since passkeys only holds a username we initialize the remaining fields as '' but birthday = 01.01.2000, city = Default, latitude = 0.0, longitude = 0.0
    """
    print("[DB] Importing users from services.passkeys.py...")

    try:
        with write_connection() as conn:
            # Set row factory to access columns by name
            conn.row_factory = sqlite3.Row

            # Step 1: Handle default user (ID=1)
            default_user = conn.execute("""
                                        SELECT id, user_name
                                        FROM user_info
                                        WHERE id = 1
                                        """).fetchone()

            if default_user and default_user['user_name'] == 'Default User':
                print("[DB] Overwriting default user (ID=1) with first allowed key")
                if ALLOWED_KEYS:
                    first_user = ALLOWED_KEYS[0]
                    conn.execute("""
                                 UPDATE user_info
                                 SET user_name          = ?,
                                     user_birthday      = '01.01.2000',
                                     location_city      = 'Default',
                                     location_latitude  = '0.0',
                                     location_longitude = '0.0',
                                     schedule_monday    = '',
                                     schedule_tuesday   = '',
                                     schedule_wednesday = '',
                                     schedule_thursday  = '',
                                     schedule_friday    = '',
                                     schedule_saturday  = '',
                                     schedule_sunday    = '',
                                     additional_info    = ''
                                 WHERE id = 1
                                 """, (first_user['user_name'],))
                    print(f"[DB] Default user updated to: {first_user['user_name']}")

            # Step 2: Get existing users from DB
            existing_users = conn.execute("""
                                          SELECT id, user_name
                                          FROM user_info
                                          """).fetchall()

            existing_user_names = {row['user_name'] for row in existing_users}
            existing_user_ids = {row['user_name']: row['id'] for row in existing_users}

            # Step 3: Get allowed usernames from passkeys
            allowed_user_names = {user['user_name'] for user in ALLOWED_KEYS}

            # Step 4: Create users that don't exist in DB
            for user_data in ALLOWED_KEYS:
                user_name = user_data['user_name']
                if user_name not in existing_user_names:
                    print(f"[DB] Creating new user: {user_name}")
                    conn.execute("""
                                 INSERT INTO user_info (user_name, user_birthday, location_city,
                                                        location_latitude, location_longitude,
                                                        schedule_monday, schedule_tuesday, schedule_wednesday,
                                                        schedule_thursday, schedule_friday, schedule_saturday,
                                                        schedule_sunday, additional_info)
                                 VALUES (?, '01.01.2000', 'Default',
                                         '0.0', '0.0',
                                         '', '', '',
                                         '', '', '',
                                         '', '')
                                 """, (user_name,))

            # Step 5: Remove users from DB that are not in passkeys.py
            users_to_remove = existing_user_names - allowed_user_names
            for user_name in users_to_remove:
                if user_name != 'Default User':  # Don't remove the default user if it was overwritten
                    user_id = existing_user_ids[user_name]
                    print(f"[DB] Removing user not in passkeys: {user_name} (ID: {user_id})")
                    conn.execute("""
                                 DELETE
                                 FROM user_info
                                 WHERE id = ?
                                 """, (user_id,))

            conn.commit()
            print("[DB] User initialization completed successfully")
            final_count_row = conn.execute('SELECT COUNT(*) as count FROM user_info').fetchone()
            final_count = final_count_row['count'] if final_count_row else 0
            print(f"[DB] Total users in database: {final_count}")

    except Exception as e:
        print(f"[DB] Failed to initialize users: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: ensure at least one user exists
        try:
            with write_connection() as conn:
                conn.row_factory = sqlite3.Row
                user_count_row = conn.execute("SELECT COUNT(*) as count FROM user_info").fetchone()
                user_count = user_count_row['count'] if user_count_row else 0

                if user_count == 0:
                    print("[DB] Creating fallback default user")
                    conn.execute("""
                                 INSERT INTO user_info (id, user_name, user_birthday, location_city,
                                                        location_latitude, location_longitude)
                                 VALUES (1, 'Default User', '01.01.2000', 'Default',
                                         '0.0', '0.0')
                                 """)
                    conn.commit()
        except Exception as fallback_e:
            print(f"[DB] Fallback user creation also failed: {fallback_e}")

def save_settings(user_id: int, data: dict):
    """
    Save settings for a specific user.
    Updates both system settings and user-specific information.
    """
    # Normalize specific fields
    if 'user_birthday' in data:
        data['user_birthday'] = _normalize_birthday(data.get('user_birthday', ''))
    if 'location_latitude' in data:
        data['location_latitude'] = _normalize_coordinate(data.get('location_latitude', ''))
    if 'location_longitude' in data:
        data['location_longitude'] = _normalize_coordinate(data.get('location_longitude', ''))

    # Split data into settings-related and user_info-related fields
    settings_fields = {
        'stt', 'stt_mode', 'llm', 'llm_mode', 'llm_vl', 'llm_vl_mode',
        'tts', 'tts_mode',
        'smart_plug1_name', 'smart_plug1_ip',
        'smart_plug2_name', 'smart_plug2_ip',
        'smart_plug3_name', 'smart_plug3_ip',
        'smart_plug4_name', 'smart_plug4_ip'
    }

    user_info_fields = {
        'user_name', 'user_birthday',
        'location_city', 'location_latitude', 'location_longitude',
        'schedule_monday', 'schedule_tuesday', 'schedule_wednesday',
        'schedule_thursday', 'schedule_friday', 'schedule_saturday',
        'schedule_sunday', 'additional_info'
    }

    settings_data = {k: v for k, v in data.items() if k in settings_fields}
    user_info_data = {k: v for k, v in data.items() if k in user_info_fields}

    with write_connection() as conn:
        # Update system settings (singleton)
        if settings_data:
            columns = ', '.join(settings_data.keys())
            placeholders = ', '.join(['?'] * len(settings_data))
            values = list(settings_data.values())

            conn.execute(
                f"UPDATE settings SET {', '.join([f'{col} = ?' for col in settings_data.keys()])} WHERE id = 1",
                values
            )

        # Update or insert user info
        if user_info_data:
            # Check if user exists
            existing_user = conn.execute("SELECT id FROM user_info WHERE id = ?", (user_id,)).fetchone()

            if existing_user:
                # Update existing user
                columns = ', '.join(user_info_data.keys())
                placeholders = ', '.join([f'{col} = ?' for col in user_info_data.keys()])
                values = list(user_info_data.values()) + [user_id]

                conn.execute(
                    f"UPDATE user_info SET {placeholders} WHERE id = ?",
                    values
                )
            else:
                # Insert new user (shouldn't happen with dummy user_id=1, but handle it anyway)
                columns = ', '.join(user_info_data.keys())
                placeholders = ', '.join(['?'] * len(user_info_data))
                values = list(user_info_data.values())

                conn.execute(
                    f"INSERT INTO user_info (id, {columns}) VALUES (?, {placeholders})",
                    [user_id] + values
                )

def persist_resource_safety_overrides(recommended_overrides: dict) -> bool:
    """
    Persists resource-based safety overrides to the singleton settings row.
    Validates inputs and only updates fields that need changing.

    This follows the same pattern as save_nutrition_user_values and other
    persistence functions in this module.

    Args:
        recommended_overrides: Dictionary with keys 'llm_mode', 'llm_vl_mode', 'tts_mode'
                               and values 'gpu' or 'cpu'

    Returns:
        bool: True if updates were applied, False if no changes needed or error occurred
    """
    try:
        # Validate input structure and values
        valid_modes = {"gpu", "cpu"}
        required_keys = {"llm_mode", "llm_vl_mode", "tts_mode"}

        # Check required keys exist
        if not all(key in recommended_overrides for key in required_keys):
            raise ValueError(f"Missing required keys. Need: {required_keys}")

        # Validate mode values
        for key in required_keys:
            mode = recommended_overrides[key]
            if mode not in valid_modes:
                raise ValueError(f"Invalid mode for {key}: {mode} but must be 'gpu' or 'cpu'")

        # Get current settings to avoid unnecessary updates
        from services.db_get import GetDB

        current_settings = {}
        current_settings['llm_mode'] = GetDB.get_llm_mode()
        current_settings['llm_vl_mode'] = GetDB.get_llm_vl_mode()
        current_settings['tts_mode'] = GetDB.get_tts_mode()

        # Check if any changes are actually needed
        changes_needed = False
        changes_to_apply = {}

        for key in required_keys:
            if current_settings[key] != recommended_overrides[key]:
                changes_needed = True
                changes_to_apply[key] = recommended_overrides[key]
                print(
                    f"[DB] Resource override needed: {key} '{current_settings[key]}' to '{recommended_overrides[key]}'")

        if not changes_needed:
            return False

        # Apply the changes to the database
        with write_connection() as conn:
            # Build the UPDATE statement dynamically based on what needs to change
            set_clauses = []
            params = []

            for key, value in changes_to_apply.items():
                set_clauses.append(f"{key} = ?")
                params.append(value)

            # Add the WHERE condition for the singleton row
            params.append(1)  # id = 1

            update_sql = f"""
                UPDATE settings 
                SET {', '.join(set_clauses)}
                WHERE id = ?
            """

            cursor = conn.execute(update_sql, params)
            rows_affected = cursor.rowcount

            if rows_affected == 0:
                # No row was updated - might need to insert instead
                print("[DB] Warning: No settings row updated. Attempting to insert default row...")

                # Insert default singleton row with overrides applied
                insert_sql = """
                             INSERT INTO settings (id, stt, stt_mode, llm, llm_mode, llm_vl, llm_vl_mode, \
                                                   tts, tts_mode, \
                                                   smart_plug1_name, smart_plug1_ip, \
                                                   smart_plug2_name, smart_plug2_ip, \
                                                   smart_plug3_name, smart_plug3_ip, \
                                                   smart_plug4_name, smart_plug4_ip) \
                             VALUES (1, 'distil-whisper', 'gpu', 'qwen3', ?, 'qwen3_vl', ?, \
                                     'xtts_v2', ?, \
                                     '', '', '', '', '', '', '', '') \
                             """

                insert_params = [
                    changes_to_apply.get('llm_mode', 'cpu'),
                    changes_to_apply.get('llm_vl_mode', 'cpu'),
                    changes_to_apply.get('tts_mode', 'cpu')
                ]

                conn.execute(insert_sql, insert_params)
                print("[DB] Default settings row created with resource safety overrides")
            else:
                print(f"[DB] Updated {rows_affected} row(s) with resource safety overrides")

        return True

    except Exception as e:
        print(f"[DB] Failed to persist resource safety overrides: {e}")
        import traceback
        traceback.print_exc()
        return False

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
