# services.api_openfoodfacts.py

import requests
import hashlib
import platform
import uuid
import re

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

def search_products(query: str, page_size: int = 5):
    """
    Search OpenFoodFacts by product name or keyword using v2 API.
    """
    url = "https://world.openfoodfacts.net/api/v2/search"
    headers = {
        "User-Agent": f"MiraNutritionModule/UID: {generate_machine_uid()} - Python Script"
    }
    params = {
        "fields": "product_name,nutriments,quantity,serving_size,code,brands",
        "page_size": page_size,
        "q": query,  # <-- correct parameter
        "sort_by": "popularity_key",  # optional, helps get relevant products
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        products = []
        for product in data.get("products", []):
            nutriments = product.get("nutriments", {})
            products.append({
                "barcode": product.get("code"),
                "product_name": product.get("product_name"),
                "brands": product.get("brands"),
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
                "quantity": normalize_amount(product.get("quantity")),
                "serving_size": normalize_amount(product.get("serving_size")),
            })
        return products

    except requests.RequestException as e:
        print(f"[OpenFoodFacts] Error searching products: {e}")
        return []

def lookup_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    headers = {
        "User-Agent": f"MiraNutritionModule/UID: {generate_machine_uid()} - Python Script"
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
            "quantity": normalize_amount(product.get("quantity")),
            "serving_size": normalize_amount(product.get("serving_size")),
        }

    except requests.RequestException as e:
        print(f"[OpenFoodFacts] Error fetching data: {e}")
        return None

def normalize_amount(value: str) -> float | None:
    """
    Normalize quantity/serving_size strings into a numeric value in g/ml.
    Examples:
      "0.5l" -> 500
      "0.5 L" -> 500
      "500ml" -> 500
      "250 g" -> 250
      "1kg" -> 1000
      "2.5 kg" -> 2500
    Returns None if parsing fails.
    """
    if not value:
        return None

    s = value.strip().lower()

    # Match number + optional unit
    match = re.match(r"([\d.,]+)\s*([a-z]*)", s)
    if not match:
        return None

    num_str, unit = match.groups()
    # Normalize decimal comma to dot
    num_str = num_str.replace(",", ".")
    try:
        num = float(num_str)
    except ValueError:
        return None

    # Unit normalization
    if unit in ("g", ""):
        return num
    elif unit in ("kg",):
        return num * 1000
    elif unit in ("ml",):
        return num
    elif unit in ("l",):
        return num * 1000
    else:
        # Unknown unit → return raw number
        return num

if __name__ == "__main__":
    import json

    # Barcode lookup
    barcode_test = False
    if barcode_test:
        test_barcode = "5449000038715"
        print(f"Testing lookup for barcode: {test_barcode}")
        result = lookup_barcode(test_barcode)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    # Search term lookup
    search_test = True
    if search_test:
        test_query = "Nutella"
        print(f"Testing search for query: {test_query}")
        results = search_products(test_query, page_size=5)
        print(json.dumps(results, indent=2, ensure_ascii=False))
