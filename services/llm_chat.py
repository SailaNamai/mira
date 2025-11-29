# services.llm_chat.py

import re
import json
from typing import Optional
from datetime import datetime
from llama_cpp import Llama
#from llama_cpp.llama_chat_format import Qwen3VLChatHandler
from services.llm_config import Config
from services.prompts_system import get_system_prompt_chat, get_system_prompt_weather
from services.db_access import write_connection
from services.globals import BASE_PATH

logs = BASE_PATH / "logs"
log_chat = logs / "chat.log"

_llm = Llama(
    model_path=str(Config.MODEL_PATH),
    n_ctx=Config.N_CTX,
    n_threads=Config.N_THREADS,
    n_gpu_layers=Config.N_GPU_LAYERS,
    temperature=0.68,
    top_p=0.95,
    top_k=20,
    repeat_penalty=1.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    use_mmap=False,
    chat_format="chatml", #jinja for qwen3 VL
)

"""_llm_vl = Llama(
    model_path=str(Config.MODEL_PATH_VL),  # Qwen3-VL GGUF path
    chat_handler=Qwen3VLChatHandler(
        clip_model_path="/home/sailanamai/mira/mmproj-F16.gguf",
        force_reasoning=False,  # Instruct variant
    ),
    n_ctx=Config.N_CTX,               # e.g. 1024–10240
    n_threads=Config.N_THREADS,
    n_gpu_layers=Config.N_GPU_LAYERS, # e.g. 20–40
    temperature=0.7,
    top_p=0.8,
    top_k=20,
    repeat_penalty=1.0,
    presence_penalty=1.5,
    frequency_penalty=0.0,
    use_mmap=False,
    swa_full=True,
)"""

def ask_weather(user_msg: str) -> str:
    system_prompt = get_system_prompt_weather()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg + "\n/no_think"}
    ]
    try:
        print("[Weather] Generating response...")
        response = _llm.create_chat_completion(
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
        self.llm = _llm
        self.history = [{"role": "system", "content": system_prompt}]

    def trim_history(self):
        """
        Ensure history fits within N_CTX by keeping system prompt + newest messages.
        """
        system_prompt = self.history[0]
        messages = self.history[1:]

        # Token budget: leave room for system prompt
        max_tokens = Config.N_CTX - count_tokens(system_prompt["content"])

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
        token_ids = _llm.tokenize(b, add_bos=False)
    except Exception:
        return 0

    return len(token_ids)
