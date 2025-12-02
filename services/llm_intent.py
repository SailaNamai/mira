# services.llm_intent.py

import re
import json
from services.prompts_system import get_system_prompt_intent, SYSTEM_PROMPT_WIKIPEDIA, SYSTEM_PROMPT_LISTIFY, SYSTEM_PROMPT_WEB
from services.db_access import write_connection
from services.wikipedia import wikipedia_lucky_search
from services.url_to_txt import save_url_text, save_multiple_urls_text, trim_output_txt
from services.web_search import web_search
import services.config as config

def ask_intent(user_msg: str) -> str:
    system_prompt = get_system_prompt_intent()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg + "\n/no_think"}
    ]
    print(f"[Intent] User Message: {user_msg}")
    try:
        print("[Intent] Generating response...")
        response = config.llm.create_chat_completion(messages=messages)
        print("[Intent] Response:")
        print(json.dumps(response, indent=2))
        raw_text = clean_response_text_json(response["choices"][0]["message"]["content"])
        _persist_db(user_msg, raw_text, raw_text)
        print(f"[Intent] Returning: {raw_text}")
        return raw_text
    except Exception as e:
        print(f"[Intent] Error: {e}")
        raise

def ask_wikipedia(user_msg: str) -> str:
    system_prompt = SYSTEM_PROMPT_WIKIPEDIA
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg + "\n/no_think"}
    ]
    print(f"[Wikipedia] User Message: {user_msg}")
    try:
        print("[Wikipedia] Generating response...")
        response = config.llm.create_chat_completion(messages=messages)
        raw_text = clean_response_text_plain(response["choices"][0]["message"]["content"])
        raw_text = raw_text.replace(" ", "_")
        print(f"[Wikipedia] search key: {raw_text}")
        api_return = wikipedia_lucky_search(user_msg, raw_text)
        save_url_text(api_return["url"])
        trim_output_txt()
        return f"Found an entry for {raw_text}."
    except Exception as e:
        print(f"[Error] {e}")
        raise

def ask_web(user_msg: str) -> str:
    system_prompt = SYSTEM_PROMPT_WEB
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg + "\n/no_think"}
    ]
    print(f"[WEB search] User Message: {user_msg}")
    try:
        print("[WEB search] Generating response...")
        response = config.llm.create_chat_completion(messages=messages)
        raw_text = clean_response_text_plain(response["choices"][0]["message"]["content"])
        print(f"[WEB search] search key: {raw_text}")
        search = web_search(raw_text)
        to_text = save_multiple_urls_text(search)
        return to_text
    except Exception as e:
        print(f"[Error] {e}")
        raise

def ask_listify(user_msg: str) -> str:
    system_prompt = SYSTEM_PROMPT_LISTIFY
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg + "\n/no_think"}
    ]
    print(f"[Listify] User Message: {user_msg}")
    try:
        print("[Listify] Generating response...")
        response = config.llm.create_chat_completion(messages=messages)
        raw_text = clean_response_text_plain(response["choices"][0]["message"]["content"])
        print(f"[Listify] Result: {raw_text}")
        return raw_text
    except Exception as e:
        print(f"[Error] {e}")
        raise

def clean_response_text_json(text: str) -> str:
    """Cleaner for intent responses (expects JSON or JSONL)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        compact_lines = []
        buffer = []
        for line in lines:
            buffer.append(line)
            if line.endswith("}"):
                try:
                    obj = json.loads("\n".join(buffer))
                    compact_lines.append(json.dumps(obj, ensure_ascii=False))
                    buffer = []
                except Exception:
                    pass
        return "\n".join(compact_lines)


def clean_response_text_plain(text: str) -> str:
    """Cleaner for wikipedia/web/listify responses (expects plain text)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _persist_db(user_msg, raw_text, truncated_resp):
    """
    Persist intent detection results into the intent_action table.

    Parameters
    - user_msg: original user message (str)
    - truncated_resp: JSON-ish string returned by the model (str)

    This function is tolerant of DB errors and will print errors instead of raising,
    to avoid breaking the calling flow.
    """
    try:
        # Try to extract a "command" field if truncated_resp is JSON-like.
        try:
            import json
            parsed = json.loads(truncated_resp)
            # Prefer 'command' key if present, otherwise store entire JSON as text.
            if isinstance(parsed, dict) and "command" in parsed:
                command = parsed["command"]
            else:
                # store compact JSON string
                command = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            # If not valid JSON, keep raw truncated_resp
            command = truncated_resp

        with write_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO intent_action (user_msg, assistant_resp, command)
                VALUES (?, ?, ?)
                """,
                (user_msg, raw_text, command),
            )
    except Exception as e:
        # Log the error but don't raise to avoid breaking upstream logic
        print(f"[DB Persist Error] failed to write intent action: {e}")