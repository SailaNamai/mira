# services.command_library.py

from services.config import HasAttachment, PLAYLIST_STEM, PLUGS, ChatContext
from services.llm_chat import ChatSession
from services.llm_intent import ask_listify
from services.media import media_play, media_pause, media_next, media_previous, playlist_load
from services.shopping_list import new_shopping_list, append_shopping_list
from services.to_do_list import new_to_do_list, append_to_do_list
from services.smart_plugs import turn_on, turn_off

def command_lookup(command: str, user_msg: str) -> bool:
    # system
    if command in ("new chat", "new conversation"):
        ChatContext.chat_session = ChatSession()
        return True
    elif command == "remove attachment":
        HasAttachment.set_attachment(False)
        return True

    # music
    elif command in ("play music", "play media"):
        media_play()
        return True
    elif command in ("pause playback", "stop playback"):
        media_pause()
        return True
    elif command in ("next song", "next episode"):
        media_next()
        return True
    elif command in ("previous song", "previous episode"):
        media_previous()
        return True
    elif command.startswith("play "):
        stem = command.removeprefix("play ").strip()
        if stem in PLAYLIST_STEM:
            playlist_load(command)
            return True

    # Lists
    elif command in ("new ShoppingList", "append ShoppingList", "new ToDoList", "append ToDoList"):
        list_items = ask_listify(user_msg)
        if command == "new ShoppingList":
            new_shopping_list(list_items)
        elif command == "append ShoppingList":
            append_shopping_list(list_items)
        elif command == "new ToDoList":
            new_to_do_list(list_items)
        elif command == "append ToDoList":
            append_to_do_list(list_items)
        return True

    # Smart plugs
    else:
        for plug_name in PLUGS:
            if command == f"on {plug_name.capitalize()}":
                turn_on(plug_name)
                return True
            elif command == f"off {plug_name.capitalize()}":
                turn_off(plug_name)
                return True

    # If nothing matched
    return False
