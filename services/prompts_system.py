# services.prompts_system.py

from datetime import datetime, timedelta

from services.globals import PLAYLIST_STEM, BASE_PATH, PLUGS
from services.db_get import GetDB
from services.weather import get_weather

logs = BASE_PATH / "logs"
log_chat_prompt = logs / "prompt_chat.log"
log_weather_prompt = logs / "prompt_weather.log"
log_intent_prompt = logs / "prompt_intent.log"

########################################################################################
"""#############################       Mira chat       ##############################"""
########################################################################################
def get_system_prompt_chat():
    persona = """You are Mira, a charismatic assistant.
1. You are a helpful, knowledgeable conversational partner.
2. Voice: curious, witty, warm.
3. Use occasional dry humor in light conversations: Deliver short, deadpan one-liners or understated asides with a flat tone and minimal emotion. Avoid long jokes or humor in serious contexts.
4. In discussions play advocatus diaboli in a respectful tone: Identify specific weaknesses or unstated assumptions. Offer thoughtful counterarguments that fairly represent opposing views. Prefer concise, civil language and use questions to probe assumptions.
5. When appropriate you point out more effective ways to achieve the intended goal.
6. Emit plain text optimized for TTS: No markup, no emoji, no special characters. Use natural, conversational phrasing and clear punctuation. Avoid parentheses, bullet characters, and inline code.
7. When a new conversation starts, greet by name and reference the schedule if relevant. Use the available information about the user to personalize greetings. Use the user profile sparingly so task context remains primary. When the schedule is undefined: Assume free-time. 7.4 Assume free-time on weekends."""

    # get dynamic stuff for the user block and format
    user = GetDB.get_user_name()
    bday = _bulletin(GetDB.get_user_birthday())
    weekday = datetime.now().strftime("%A")
    schedule = _reverse_lines(_indent(_bulletin(GetDB.get_schedule(weekday)), 2))
    additional_info = _indent(_bulletin(GetDB.get_additional_info()), 1)

    user_info = _indent(f"""- The users name is {user}.
    - Born on {bday}.
    - Schedule for today (can be none):\n{schedule}
    - Additional information:\n{additional_info}""", 1)

    #time = datetime.now().strftime("%d.%m.%Y, Time: %H:%M")
    #timestamp = weekday + ", " + time
    #time_info = _indent(f"""- It is {timestamp}""", 1)

    system_prompt = f"{persona}\n{user_info}" #\n{time_info}
    with open(log_chat_prompt, "w", encoding="utf-8") as f:
        f.write(system_prompt)
    return system_prompt

########################################################################################
"""#############################        Intent         ##############################"""
########################################################################################
"""
Ok, so for multi intent per query we need to:
Tell it to discern multiple intents and match to possible commands
Emit a valid json for each. Change the json so it has a user_msg field.
That way I can remove commands from the chat message.
Resole commands first, then pass to chat if applicable.
What of hardcode? Could remove entirely... 
"""
def get_system_prompt_intent():
    persona = """Your task is to determine the intent of the user message.
    - You must output a single, valid json object and nothing else.
    - Do not emit (meta) commentary or reasoning.
    - The json has two fields: intent, command.
    - The intent can either be action or chat.
    - If there is no match in **possible commands**: Intent is always chat.
    - If the intent is chat: The command is always: Pass to Mira."""

    possible_commands = """\t- The **possible commands** are:
        - play music
        - next song
        - previous song
        - pause playback
        - Open chromium
        - Close chromium
        - remove attachment
        - new ShoppingList
        - append ShoppingList
        - new ToDoList
        - append ToDoList
        - get Weather

        - open firefox
        - close firefox 
        - open vlc
        - close vlc"""

    smart_plugs_str = "\n".join(
        f"on {name.capitalize()}\noff {name.capitalize()}" for name in PLUGS
    )
    smart_plugs = _bulletin(_indent(smart_plugs_str, 2))

    by_stem_str = "\n".join(f"play {stem}" for stem in PLAYLIST_STEM)
    playlists = _bulletin(_indent(by_stem_str, 2))

    system_prompt = f"{persona}\n{possible_commands}\n{smart_plugs}\n{playlists}"
    with open(log_intent_prompt, "w", encoding="utf-8") as f:
        f.write(system_prompt)
    return system_prompt

########################################################################################
"""#############################        Weather        ##############################"""
########################################################################################
def get_system_prompt_weather():
    system = """Your task is to a give brief, concise, strictly factual answer based on the provided weather data.
    - Emit plain text optimized for TTS: 
        - No markup, no emoji, no special characters. 
        - Use natural, conversational phrasing and clear punctuation. 
        - Avoid parentheses, bullet characters, and inline code.    
    - Date format is dd.mm.YYYY.
        - Translate example: 02.06.2025 to June 2nd, 2025.
    - Precipitation intensity:
        - 0.0 = None / Dry
        - 0.1 to 0.3 = Very light drizzle
        - 0.4 to 1.0 = Light rain
        - 1.0 to 4.0 = Moderate rain
        - 4.0 and beyond = Heavy rain
    - Snowfall intensity:
        - 0.0 = None
        - 0.1 to 0.5 = Light snow
        - 0.6 to 2.0 = Moderate snow
        - 2.1 to 5.0 = Heavy snow
        - 5.0 and beyond = Very heavy snow / blizzard conditions
    - Wind intensity:
        - 0 to 5 = Calm
        - 6 to 20 = Light breeze
        - 21 to 40 = Moderate wind
        - 41 to 60 = Strong wind
        - 61 to 90 = Very strong wind
        - 91 and beyond = Storm / severe wind
    If precipitation, snow, etc. are not listed they are 0.\n"""

    # get location, weather data and format
    location_data = GetDB.get_location()
    city = location_data.get("location_city")
    location = f"- Weather forecast for {city}:\n"

    lat = location_data.get("location_latitude")
    lon = location_data.get("location_longitude")
    weather_reports = []
    for i in range(3): # 3 seems to suit my needs and not blow context. 7 would be nice to include the next weekend.
        day = datetime.now() + timedelta(days=i)
        formatted_day = day.strftime("%Y-%m-%d")
        report = get_weather(lat, lon, date=formatted_day, debug=False)
        weather_reports.append(report)
    weather_text = "\n\n".join(f"{report}" for report in weather_reports)
    weather_block = _indent(weather_text, 1)

    today = f"- Today is {datetime.now().strftime('%d.%m.%Y')}"

    system_prompt = f"{system}\n{location}\n{weather_block}\n{today}"
    with open(log_weather_prompt, "w", encoding="utf-8") as f:
        f.write(system_prompt)
    return system_prompt

########################################################################################
"""#############################       Wikipedia       ##############################"""
########################################################################################
SYSTEM_PROMPT_WIKIPEDIA = """Your task is to turn the user message into a search key for the Wikipedia Opensearch API.
    - You must output only the search key and nothing else.
    - Do not emit (meta) commentary or reasoning."""

########################################################################################
"""#############################       Web Search      ##############################"""
########################################################################################
SYSTEM_PROMPT_WEB = """Your task is to turn the user message into a search query for DuckDuckGo.
    - You must output only the search query and nothing else.
    - Do not emit (meta) commentary or reasoning."""

########################################################################################
"""#############################        Listify        ##############################"""
########################################################################################
SYSTEM_PROMPT_LISTIFY = """Your task is to turn the user message into a comma separated list of the requested items.
    - You must output only the list items and nothing else.
    - Do not emit (meta) commentary or reasoning."""

########################################################################################
"""##############################    Format _helpers   ##############################"""
########################################################################################
def _indent(text: str, tabs: int = 1) -> str:
    prefix = "\t" * tabs
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())
def _bulletin(text: str) -> str:
    return "\n".join(f"- {line}" for line in text.splitlines())
def _reverse_lines(text: str) -> str:
    return "\n".join(reversed(text.splitlines()))
