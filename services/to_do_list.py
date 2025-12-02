# services.to_do_list.py

import json
from services.config import BASE_PATH

to_do_list_path = BASE_PATH / "static" / "lists" / "to_do_list.json"

def new_to_do_list(to_do_items):
    """
    Create a new to_do list, overwriting any existing list.

    :param to_do_items: List of to_do items (each item is a string)
    :return: The created to_do list
    """
    # If to_do_items is a string (from LLM output), split it
    if isinstance(to_do_items, str):
        # Split by comma and strip whitespace
        to_do_items = [item.strip() for item in to_do_items.split(',')]

    # Prepare the to_do list with each item as a bullet point
    formatted_list = [f"• {item.strip()}" for item in to_do_items if item.strip()]

    # Write to JSON file
    with open(to_do_list_path, 'w', encoding='utf-8') as f:
        json.dump(formatted_list, f, indent=2, ensure_ascii=False)

    return formatted_list

def append_to_do_list(new_items):
    """
    Append new items to the existing to_do list.

    :param new_items: List of new items to append or a comma-separated string
    :return: Updated to_do list
    """
    # If new_items is a string (from LLM output), split it
    if isinstance(new_items, str):
        # Split by comma and strip whitespace
        new_items = [item.strip() for item in new_items.split(',')]

    # Read existing list or create empty list if file doesn't exist
    try:
        with open(to_do_list_path, 'r', encoding='utf-8') as f:
            current_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        current_list = []

    # Append new items with bullet points
    formatted_new_items = [f"• {item.strip()}" for item in new_items if item.strip()]
    updated_list = current_list + formatted_new_items

    # Write updated list back to file
    with open(to_do_list_path, 'w', encoding='utf-8') as f:
        json.dump(updated_list, f, indent=2, ensure_ascii=False)

    return updated_list
