# services.barcode.py

import requests
import hashlib
import platform
import uuid

from services.db_persist import persist_nutri_item_values

def generate_machine_uid():
    """
    Generates a stable, anonymous machine identifier.
    This UID is derived from system attributes (hostname, MAC address, OS, release),
    hashed with SHA-256 and truncated to 12 hex characters.
    It is:
      - Deterministic per machine
      - Effectively irreversible due to SHA-256 and truncation
      - Free of personal identifiers, suitable for privacy-conscious API usage
    Example output: '9f3a1c2b7e4d'
    """
    fingerprint = f"{platform.node()}|{uuid.getnode()}|{platform.system()}|{platform.release()}"
    uid = hashlib.sha256(fingerprint.encode()).hexdigest()[:12]
    return uid


def lookup_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    headers = {
        "User-Agent": f"MiraNutritionScanner/UID: {generate_machine_uid()} - Python Script"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 1:
            print(f"[OpenFoodFacts] Product not found for barcode: {barcode}")
            return None

        product = data.get("product", {})
        nutriments = product.get("nutriments", {})

        return {
            "barcode": barcode,
            "product_name": product.get("product_name"),
            "nutriments": {
                "energy_kcal_100g": nutriments.get("energy-kcal_100g"),
                "energy_kcal_serving": nutriments.get("energy-kcal_serving"),
                "carbohydrates_100g": nutriments.get("carbohydrates_100g"),
                "carbohydrates_serving": nutriments.get("carbohydrates_serving"),
                "fat_100g": nutriments.get("fat_100g"),
                "fat_serving": nutriments.get("fat_serving"),
                "proteins_100g": nutriments.get("proteins_100g"),
                "proteins_serving": nutriments.get("proteins_serving"),
            },
            "quantity": product.get("quantity"),
            "serving_size": product.get("serving_size"),
            "packaging_text": product.get("packaging_text"),
            "product_quantity": product.get("product_quantity"),
            "portion_description": product.get("portion_description")
        }

    except requests.RequestException as e:
        print(f"[OpenFoodFacts] Error fetching data: {e}")
        return None

if __name__ == "__main__":
    import json
    import sys

    test_barcode = sys.argv[1] if len(sys.argv) > 1 else "4000405002070"
    print(f"Testing lookup for barcode: {test_barcode}")

    result = lookup_barcode(test_barcode)
    persist_nutri_item_values(result)

    print(json.dumps(result, indent=2, ensure_ascii=False))
