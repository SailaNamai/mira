# services.globals.py

import socket
from pathlib import Path
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Qwen3VLChatHandler

########################################################################################
"""############################        System          ##############################"""
########################################################################################
BASE_PATH = Path(__file__).resolve().parent.parent
PASSKEYS_PATH = BASE_PATH / "services" / "passkeys.py"
DEBUG = True

# Query for keys on first init
try:
    from .passkeys import ALLOWED_KEYS, SECRET_KEY
except ImportError:
    if PASSKEYS_PATH.exists():
        # File exists but import failed (e.g. syntax error) — don't override
        raise
    print("[Authenticate] passkeys.py not found. Starting init.")
    print("[Authenticate] These keys control API/web access")

    # Prompt for input (won't echo SECRET_KEY if you want extra safety, but let's keep it simple)
    allowed_input = input("[Authenticate] Enter ALLOWED_KEYS (user passwords, comma-separated, e.g. 'key1,key2'): ").strip()
    secret_input = input("[Authenticate] Enter SECRET_KEY (single string): ").strip()

    if not allowed_input or not secret_input:
        print("[Authenticate] Empty input — using dummy keys (insecure!)")
        ALLOWED_KEYS = {"dummy_key_1", "dummy_key_2"}
        SECRET_KEY = "dummy_secret"
    else:
        # Parse & sanitize
        ALLOWED_KEYS = {k.strip() for k in allowed_input.split(",") if k.strip()}
        SECRET_KEY = secret_input

        # Generate passkeys.py
        content = f'''"""
Local authentication keys — NEVER COMMIT THIS FILE.
Generated automatically by services/globals.py on first run.
"""

ALLOWED_KEYS = {ALLOWED_KEYS}
SECRET_KEY = "{SECRET_KEY}"
'''
        PASSKEYS_PATH.write_text(content)
        print(f"[Authenticate]passkeys.py created at: {PASSKEYS_PATH}")
        print("[Authenticate] Dev? Added to .gitignore?")

# Returns host IP
def get_local_ip():
    """Returns the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable—just used to determine the local IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

########################################################################################
"""############################        VL LLM          ##############################"""
########################################################################################
llm_vl = None
MODEL_PATH = BASE_PATH / "Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf"
MMPROJ_PATH = BASE_PATH / "Qwen3-VL-8B-Instruct-mmproj-F16.gguf"

def init_qwen_vl():
    """
    Initialize Qwen3-VL model into RAM at Flask startup.
    """
    print("[VL] Model initializing...")
    global llm_vl
    llm_vl = Llama(
        model_path=str(MODEL_PATH),
        chat_handler=Qwen3VLChatHandler(
            clip_model_path=str(MMPROJ_PATH),
            force_reasoning=False,  # barcode task is simple, no need to force reasoning
        ),
        n_gpu_layers=0,   # offload no layers to GPU
        n_ctx=2048,        # context size; barcode prompt is short
        n_threads=16,       # use 16 CPU threads
        swa_full=True,
    )
    print("[VL] Model initialized and warmed up.")

########################################################################################
"""############################         Chat           ##############################"""
########################################################################################
# Rolling context window for chat
class ChatContext:
    chat_session = None

class ChatState:
    intent = None
    user_msg = None
    weather = None
    picture = None

########################################################################################
"""############################        Files           ##############################"""
########################################################################################
# Attachment state handler
class HasAttachment:
    _has_attachment = False
    _is_picture = False

    @classmethod
    def set_attachment(cls, value: bool):
        cls._has_attachment = value

    @classmethod
    def set_picture(cls, value: bool):
        cls._is_picture = value

    @classmethod
    def has_attachment(cls) -> bool:
        return cls._has_attachment

    @classmethod
    def is_picture(cls) -> bool:
        return cls._is_picture

    @classmethod
    def clear(cls):
        cls._has_attachment = False
        cls._is_picture = False

########################################################################################
"""############################        Various         ##############################"""
########################################################################################

# music
PLAYLIST_STEM = []
PLAYLIST_FILENAMES = {}  # Dict of stem → filename
# Tasmota plugs
PLUGS = {}