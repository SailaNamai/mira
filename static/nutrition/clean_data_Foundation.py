#!/usr/bin/env python3
"""
Correctly parse the FULL current USDA Foundation Foods JSON (2025 version)
and extract fat, protein, carbs, kcal per 100g for ALL foods — including new ones.
"""

import json
from pathlib import Path

INPUT_FILE = Path("FoodData_Central_branded_food_json_2025-04-24.json")
OUTPUT_FILE = Path("BrandedFoods.json")

# Priority order for energy (kcal) – newer foods use 957/958, old ones use 208
ENERGY_SOURCES = ["208", "958", "957"]   # kcal in that order of preference

# Core macronutrients we want
MACRO_NUTRIENTS = {
    "204": "fat_100g",       # Total lipid (fat)
    "203": "protein_100g",   # Protein
    "205": "carbs_100g",     # Carbohydrate, by difference
}

def extract_macros(food):
    result = {
        "fdcId": food.get("fdcId"),
        "description": food.get("description"),
        "fat_100g": 0.0,
        "protein_100g": 0.0,
        "carbs_100g": 0.0,
        "kcal_100g": 0,
    }

    kcal_found = False

    for nutrient in food.get("foodNutrients", []):
        n = nutrient.get("nutrient", {})
        number = str(n.get("number", ""))
        amount = nutrient.get("amount")

        if amount is None:
            continue

        # === Energy (kcal) ===
        if number in ENERGY_SOURCES and not kcal_found:
            result["kcal_100g"] = int(round(float(amount)))
            kcal_found = True
            if number == "208":
                break  # 208 is most authoritative when present

        # === Macros ===
        if number in MACRO_NUTRIENTS:
            key = MACRO_NUTRIENTS[number]
            result[key] = round(float(amount), 2)

    return result

def main():
    if not INPUT_FILE.exists():
        print(f"Error: {INPUT_FILE} not found!")
        return

    print(f"Loading {INPUT_FILE.name} ...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    foods = data.get("FoundationFoods", [])
    print(f"Found {len(foods)} foods in FoundationFoods array")

    trimmed = []
    skipped = 0

    for food in foods:
        entry = extract_macros(food)
        # Keep only foods that have at least some caloric value
        if entry["kcal_100g"] > 0 or any(entry[k] > 0 for k in ["fat_100g", "protein_100g", "carbs_100g"]):
            trimmed.append(entry)
        else:
            skipped += 1

    print(f"Writing {len(trimmed)} valid entries (skipped {skipped} empty ones)")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, indent=2, ensure_ascii=False)

    print(f"Done! → {OUTPUT_FILE}")

    # Show pineapple as proof
    pineapple = next((x for x in trimmed if x["fdcId"] == 2346398), None)
    if pineapple:
        print("\nPineapple found and correctly parsed:")
        print(json.dumps(pineapple, indent=2))

if __name__ == "__main__":
    main()