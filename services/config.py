# services.config.py

import socket
import sys, io
from contextlib import contextmanager
from pathlib import Path
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Qwen3VLChatHandler
from services.db_get import GetDB

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
        # File exists but import failed
        raise
    print("[Authenticate] passkeys.py not found. Starting init.")
    print("[Authenticate] These keys control API/web access.")

    # Prompt for input
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

@contextmanager
def suppress_stdout_stderr():
    """Redirect stdout/stderr to a dummy buffer temporarily."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

########################################################################################
"""############################       TXT LLM          ##############################"""
########################################################################################
llm = None
MODEL_PATH = BASE_PATH / "Qwen3-8B-UD-Q6_K_XL.gguf"
MAX_CONTEXT = 8192

def init_qwen():
    """
    Initialize Qwen3 into VRAM at Flask startup.
    """
    mode = GetDB.get_llm_mode()
    print(f"[LLM] Model initializing on {mode}...")
    if mode == "cpu":
        gpu_layers = 0
    else:
        gpu_layers = -1

    global llm

    with suppress_stdout_stderr():
        llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=MAX_CONTEXT,
            n_threads=16,
            n_gpu_layers=gpu_layers,
            temperature=0.68,
            top_p=0.95,
            top_k=20,
            repeat_penalty=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            use_mmap=False,
            verbose=True, # unwrap the with suppress for full log console
            chat_format="chatml",
        )
    print("[LLM] Model initialized and warmed up.")

########################################################################################
"""############################        VL LLM          ##############################"""
########################################################################################
llm_vl = None
MODEL_PATH_VL = BASE_PATH / "Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf"
MMPROJ_PATH = BASE_PATH / "Qwen3-VL-8B-Instruct-mmproj-F16.gguf"

def init_qwen_vl():
    """
    Initialize Qwen3-VL into RAM at Flask startup.
    """
    mode = GetDB.get_llm_vl_mode()
    print(f"[LLM VL] Model initializing on {mode}...")
    if mode == "cpu":
        gpu_layers = 0
    else:
        gpu_layers = -1
    global llm_vl

    with suppress_stdout_stderr():
        llm_vl = Llama(
            model_path=str(MODEL_PATH_VL),
            chat_handler=Qwen3VLChatHandler(
                clip_model_path=str(MMPROJ_PATH),
                force_reasoning=False,
            ),
            n_gpu_layers=gpu_layers,
            n_ctx=2048,
            n_threads=16,
            swa_full=True,
            verbose=True,  # unwrap the with suppress for full log console
        )
    print("[LLM VL] Model initialized and warmed up.")

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

class FileSupport:
    # LibreOffice can turn to PDF
    LIBRE_EXTENSIONS = {
        ".doc", ".docx", ".odt", ".rtf",
        ".xls", ".xlsx", ".ods", ".csv",
        ".ppt", ".pptx", ".odp",
        ".html", ".pdf", ".txt"
    }
    # Already text
    PLAIN_TEXT_EXTENSIONS = {
        ".py", ".js", ".ts", ".css", ".html", ".md",
        ".json", ".xml", ".yaml", ".yml", ".toml",
        ".sh", ".c", ".cpp", ".java", ".rb", ".go", ".rs"
    }
    # Pictures
    IMAGE_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".svg", ".webp"
    }

    @classmethod
    def is_supported(cls, file_path: Path) -> bool:
        ext = file_path.suffix.lower()
        return (
            ext in cls.LIBRE_EXTENSIONS
            or ext in cls.PLAIN_TEXT_EXTENSIONS
            or ext in cls.IMAGE_EXTENSIONS
        )

    @classmethod
    def is_image(cls, file_path: Path) -> bool:
        return file_path.suffix.lower() in cls.IMAGE_EXTENSIONS

########################################################################################
"""############################        Various         ##############################"""
########################################################################################

# music
PLAYLIST_STEM = []
PLAYLIST_FILENAMES = {}  # Dict of stem → filename
# Tasmota plugs
PLUGS = {}