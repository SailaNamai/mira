# services.smart_plugs.py

import requests
from services.db_get import GetDB
from services.globals import PLUGS

def load_plugs_from_db():
    """
    Populate the PLUGS dictionary from the database.
    """
    plug_data = GetDB.get_smart_plugs()
    PLUGS.clear()  # Clear any existing entries

    for i in range(1, 5):
        name_key = f"smart_plug{i}_name"
        ip_key = f"smart_plug{i}_ip"
        name = plug_data.get(name_key)
        ip = plug_data.get(ip_key)
        if name:
            PLUGS[name.lower()] = ip or None

def _send_command(name: str, action: str):
    """Internal helper."""
    ip = PLUGS.get(name.lower())
    if not ip:
        print(f"[SmartPlug] No IP configured for plug '{name}'")
        return

    url = f"http://{ip}/cm?cmnd=Power%20{action.capitalize()}"
    try:
        requests.get(url)
    except Exception as e:
        print(f"[SmartPlug] Error sending command to '{name}': {e}")

def turn_on(name: str):
    """Turn ON the plug with the given name."""
    _send_command(name, "On")

def turn_off(name: str):
    """Turn OFF the plug with the given name."""
    _send_command(name, "Off")