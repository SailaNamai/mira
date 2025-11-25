# services.command_library.py

from services.globals import HasAttachment, PLAYLIST_STEM, PLUGS
from services.music import music_play, music_pause, music_next, music_previous, music_load
from services.browser.chromium import chromium_start, chromium_terminate
from services.shopping_list import new_shopping_list, append_shopping_list
from services.to_do_list import new_to_do_list, append_to_do_list
from services.smart_plugs import turn_on, turn_off

def command_lookup(command, list_items):
    # music
    if command == "play music": music_play()
    if command in ("pause playback", "stop playback"): music_pause()
    if command == "next song": music_next()
    if command == "previous song": music_previous()
    if command.startswith("play "):
        stem = command.removeprefix("play ").strip()
        if stem in PLAYLIST_STEM: music_load(command)
    # chromium
    if command == "open Chromium": chromium_start()
    if command == "close Chromium": chromium_terminate()
    # gui
    if command == "remove attachment": HasAttachment.set_attachment(False)
    # ShoppingList
    if command == "new ShoppingList": new_shopping_list(list_items)
    if command == "append ShoppingList": append_shopping_list(list_items)
    # To-Do List
    if command == "new ToDoList": new_to_do_list(list_items)
    if command == "append ToDoList": append_to_do_list(list_items)
    # Smart plugs
    for plug_name in PLUGS:
        if command == f"on {plug_name.capitalize()}":
            turn_on(plug_name)
        elif command == f"off {plug_name.capitalize()}":
            turn_off(plug_name)
    return