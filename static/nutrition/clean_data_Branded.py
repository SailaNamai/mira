#!/usr/bin/env python3
import ijson
import json
from pathlib import Path

INPUT_FILE = Path("FoodData_Central_branded_food_json_2025-04-24.json")
OUTPUT_FILE = Path("BrandedFoods_trimmed.json")

# Nutrient IDs we care about (USDA nutrient numbers)
MACROS = {
    "208": "kcal_100g",   # Energy in kcal (preferred)
    "204": "fat_100g",    # Total lipid (fat)
    "203": "protein_100g",
    "205": "carbs_100g",  # Carbohydrate, by difference
}

# Fallback keys in labelNutrients
LABEL_FALLBACK = {
    "calories": "kcal_100g",
    "fat": "fat_100g",
    "protein": "protein_100g",
    "carbohydrates": "carbs_100g",
}

def safe_float(x):
    """Convert to float safely, return 0.0 if None/invalid"""
    try:
        return float(x) if x is not None else 0.0
    except (TypeError, ValueError):
        return 0.0

def normalize_to_100g(amount_per_serving: float, serving_size_g: float) -> float:
    """Convert nutrient per serving: per 100g"""
    if not serving_size_g or serving_size_g <= 0:
        return round(amount_per_serving, 2)
    return round((amount_per_serving / serving_size_g) * 100, 2)

def extract_food_entry(food):
    entry = {
        "fdcId": food.get("fdcId"),
        "description": food.get("description", "").strip(),
        "fat_100g": 0.0,
        "protein_100g": 0.0,
        "carbs_100g": 0.0,
        "kcal_100g": 0,
    }

    # Get serving size in grams
    serving_size = safe_float(food.get("servingSize"))
    if serving_size <= 0:
        serving_size = 100  # fallback

    # Primary source: foodNutrients
    nutrients = food.get("foodNutrients", [])
    found_kcal = False

    for nutrient in nutrients:
        # Some entries have nutrient directly, others nested under "nutrient"
        nut = nutrient if isinstance(nutrient, dict) and "nutrient" not in nutrient else nutrient.get("nutrient", {})
        number = str(nut.get("number", ""))
        amount = safe_float(nutrient.get("amount"))

        if not number or amount == 0:
            continue

        if number == "208" and not found_kcal:  # kcal – prefer this
            entry["kcal_100g"] = int(round(normalize_to_100g(amount, serving_size)))
            found_kcal = True
        elif number in MACROS:
            key = MACROS[number]
            entry[key] = normalize_to_100g(amount, serving_size)

    # --- Fallback: labelNutrients (common in branded foods) ---
    label = food.get("labelNutrients", {})

    if entry["kcal_100g"] == 0 and "calories" in label:
        cal_val = safe_float(label["calories"].get("value"))
        if cal_val > 0:
            entry["kcal_100g"] = int(round(normalize_to_100g(cal_val, serving_size)))

    for label_key, target_key in [("fat", "fat_100g"), ("protein", "protein_100g"), ("carbohydrates", "carbs_100g")]:
        if entry[target_key] == 0.0 and label_key in label:
            val = safe_float(label[label_key].get("value"))
            if val > 0:
                entry[target_key] = normalize_to_100g(val, serving_size)

    return entry

def main():
    if not INPUT_FILE.exists():
        print(f"Error: {INPUT_FILE} not found!")
        return

    print(f"Parsing {INPUT_FILE.name} – this may take a while...")
    trimmed = []
    skipped = 0
    total = 0

    with open(INPUT_FILE, "rb") as f:  # binary mode for ijson stability
        parser = ijson.items(f, "BrandedFoods.item")

        for food in parser:
            total += 1
            entry = extract_food_entry(food)

            # Keep only entries with at least some meaningful data
            has_data = (
                entry["kcal_100g"] > 0 or
                entry["fat_100g"] > 0 or
                entry["protein_100g"] > 0 or
                entry["carbs_100g"] > 0
            )

            if has_data:
                trimmed.append(entry)
            else:
                skipped += 1

            if total % 5000 == 0:
                print(f"Processed {total:,} items → {len(trimmed):,} kept, {skipped:,} skipped")

    print(f"\nFinished!")
    print(f"   Total processed : {total:,}")
    print(f"   Valid entries   : {len(trimmed):,}")
    print(f"   Skipped (no data): {skipped:,}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(trimmed, out, indent=2, ensure_ascii=False)

    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()