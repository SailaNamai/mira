# services.shopping_list.py

import json
from services.globals import BASE_PATH

shopping_list_path = BASE_PATH / "static" / "lists" / "shopping_list.json"

def new_shopping_list(shopping_items):
    """
    Create a new shopping list, overwriting any existing list.

    :param shopping_items: List of shopping items (each item is a string)
    :return: The created shopping list
    """
    # If shopping_items is a string (from LLM output), split it
    if isinstance(shopping_items, str):
        # Split by comma and strip whitespace
        shopping_items = [item.strip() for item in shopping_items.split(',')]

    # Prepare the shopping list with each item as a bullet point
    formatted_list = [f"• {item.strip()}" for item in shopping_items if item.strip()]

    # Write to JSON file
    with open(shopping_list_path, 'w', encoding='utf-8') as f:
        json.dump(formatted_list, f, indent=2, ensure_ascii=False)

    return formatted_list

def append_shopping_list(new_items):
    """
    Append new items to the existing shopping list.

    :param new_items: List of new items to append or a comma-separated string
    :return: Updated shopping list
    """
    # If new_items is a string (from LLM output), split it
    if isinstance(new_items, str):
        # Split by comma and strip whitespace
        new_items = [item.strip() for item in new_items.split(',')]

    # Read existing list or create empty list if file doesn't exist
    try:
        with open(shopping_list_path, 'r', encoding='utf-8') as f:
            current_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        current_list = []

    # Append new items with bullet points
    formatted_new_items = [f"• {item.strip()}" for item in new_items if item.strip()]
    updated_list = current_list + formatted_new_items

    # Write updated list back to file
    with open(shopping_list_path, 'w', encoding='utf-8') as f:
        json.dump(updated_list, f, indent=2, ensure_ascii=False)

    return updated_list
