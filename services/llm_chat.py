# services.llm_chat.py

import re
import json
from typing import Optional
from datetime import datetime
from services.prompts_system import get_system_prompt_chat, get_system_prompt_weather
from services.db_access import write_connection
import services.config as config

logs = config.BASE_PATH / "logs"
log_chat = logs / "chat.log"

def ask_weather(user_msg: str) -> str:
    system_prompt = get_system_prompt_weather()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg + "\n/no_think"}
    ]
    try:
        print("[Weather] Generating response...")
        response = config.llm.create_chat_completion(
            messages=messages
        )
        raw_text = response["choices"][0]["message"]["content"]
        # Clean the response
        clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
        clean_text = (clean_text
                      .replace("°C", " degree celsius")
                      .replace("km/h", "kilometer per hour")
                      .replace("mm", " millimeter")
                      .replace("cm", " centimeter")
                      )
        print(f"[Weather] Result: {clean_text}")
        return clean_text
    except Exception as e:
        print(f"[Weather] Error: {e}")
        raise

class ChatSession:
    def __init__(self):
        system_prompt = get_system_prompt_chat()
        self.llm = config.llm
        self.history = [{"role": "system", "content": system_prompt}]

    def trim_history(self):
        """
        Ensure history fits within N_CTX by keeping system prompt + newest messages.
        """
        system_prompt = self.history[0]
        messages = self.history[1:]

        # Token budget: leave room for system prompt
        max_tokens = config.MAX_CONTEXT - count_tokens(system_prompt["content"])

        trimmed = []
        total_tokens = 0
        # iterate backwards (newest first)
        for msg in reversed(messages):
            msg_tokens = count_tokens(msg["content"])
            if total_tokens + msg_tokens <= max_tokens:
                trimmed.insert(0, msg)  # prepend to maintain order
                total_tokens += msg_tokens
            else:
                break

        self.history = [system_prompt] + trimmed

    def ask(self, user_msg: str) -> str:
        print(f"[User] {user_msg}")

        time = datetime.now().strftime("%d.%m.%Y, Time: %H:%M")
        weekday = datetime.now().strftime("%A")
        timestamp = weekday + ", " + time

        try:
            tag = "/think" if user_msg.strip().endswith("/think") else "/no think"
            print(f"[Mira] Using {tag}")

            self.history.append({"role": "user", "content": timestamp + "\n" + user_msg + "\n" + tag})

            # Trim before sending to model
            self.trim_history()

            print("[Mira] Generating response...")
            response = self.llm.create_chat_completion(messages=self.history)
            reply = response["choices"][0]["message"]["content"]
            self.history.append({"role": "assistant", "content": reply})
            print(f"[Mira] {reply}")

            # log trimmed history (what model saw)
            with open(log_chat, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)

            # Extract <think>...</think> block if present
            think_match = re.search(r"<think>(.*?)</think>", reply, re.DOTALL)
            think = think_match.group(1).strip() if think_match else None
            if think: print(f"[Mira] Reasoning:\n{think}")

            # Remove the <think> block from the reply to get the pure response
            reply_pure = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()

            # Persist full exchange (not trimmed) to DB
            chat_persist_db(self, user_msg, reply_pure, think)
            return reply_pure

        except Exception as e:
            print(f"[Mira] Error: {e}")
            raise


def chat_persist_db(self, user_msg, reply, think):
    """
    Persist chat exchanges into intent_chat table.

    Parameters
    - self: ChatSession instance
    - user_msg: user's message (str)
    - reply: assistant reply (str)
    """
    try:
        # Determine conv_id: use id(self) as a lightweight unique session identifier
        conv_id = id(self)

        # Compute token cost
        try: token_cost = count_tokens(user_msg + reply)
        except Exception: token_cost = 0

        with write_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO intent_chat (conv_id, user_msg, response, think, token_cost)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conv_id, user_msg, reply, think, token_cost),
            )
    except Exception as e:
        # Log but do not raise to avoid breaking chat flow
        print(f"[DB Persist Error] failed to write chat: {e}")

def count_tokens(text: Optional[str]) -> int:
    """
    Returns how many tokens llama.cpp would consume for `text`.
    """
    if not text:
        return 0

    if isinstance(text, bytes):
        b = text
    else:
        b = str(text).encode('utf-8')

    try:
        token_ids = config.llm.tokenize(b, add_bos=False)
    except Exception:
        return 0

    return len(token_ids)
