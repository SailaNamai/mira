# services.llm_chat.py

import re
import json
import uuid
from typing import Optional
from datetime import datetime
from flask import session
from services.user_managment import HasAttachment
from services.prompts_system import get_system_prompt_chat, get_system_prompt_weather
from services.db_access import write_connection
import services.config as config

logs = config.BASE_PATH / "logs"
log_chat = logs / "chat.log"

def ask_weather(user_id: int, user_msg: str) -> str:
    system_prompt = get_system_prompt_weather(user_id)
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

class ChatContext:
    sessions = {}

    @classmethod
    def get_session(cls, user_id: int) -> "ChatSession":
        # Return existing session or create a new one
        if user_id not in cls.sessions:
            cls.sessions[user_id] = ChatSession(user_id)
        return cls.sessions[user_id]

    @classmethod
    def create_session(cls, user_id: int):
        # Always replace with a fresh ChatSession
        cls.sessions[user_id] = ChatSession(user_id)
        HasAttachment.clear(user_id)
        print(f"[ChatContext] Created new ChatSession for user_id={user_id}")

class ChatSession:
    def __init__(self, user_id: int):
        self.llm = config.llm
        self.user_id = user_id
        self.conv_id = uuid.uuid4().hex  # unique per session

        system_prompt = get_system_prompt_chat(user_id)
        self.history = [{"role": "system", "content": system_prompt}]

    def trim_history(self):
        """
        Ensure history fits within N_CTX by keeping system prompt + the newest messages.
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
        user_id = session.get('user_id')

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

            # Persist to DB
            # inside ChatSession.ask, before chat_persist_db(...)
            # print(f"[Mira] Persisting: user_id={user_id!r}, session_obj_id={id(self)}, session_conv_id={self.conv_id}")
            chat_persist_db(self, user_msg, user_id, reply_pure, think)

            return reply_pure

        except Exception as e:
            print(f"[Mira] Error: {e}")
            raise


def chat_persist_db(self, user_msg, user_id, reply, think):
    """
    Persist chat exchanges into intent_chat table.
    -- CHAT
    CREATE TABLE IF NOT EXISTS intent_chat (
      id                  INTEGER PRIMARY KEY AUTOINCREMENT,   -- unique identifier
      user_id             INT,
      conv_id             INTEGER,                             -- unique chat id
      user_msg            TEXT,                                -- the user query
      response            TEXT,                                -- mira's response
      think               TEXT,                                -- reasoning process
      token_cost          INTEGER,                             -- token cost query+response
      created_at TEXT DEFAULT (strftime('%Y-%m-%d at %H:%M','now','localtime')) -- timestamp of insertion
    );
    """
    try:
        # id(self) as a lightweight unique session identifier
        conv_id = self.conv_id
        print(f"[ChatSession] Created session for user_id={user_id} with conv_id={self.conv_id}")

        # Compute token cost
        try: token_cost = count_tokens(user_msg + reply)
        except Exception: token_cost = 0

        with write_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO intent_chat (conv_id, user_msg, user_id, response, think, token_cost)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (conv_id, user_msg, user_id, reply, think, token_cost),
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
