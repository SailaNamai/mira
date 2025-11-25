# services.globals.py

"""
GlobalVars
"""
import socket
from pathlib import Path

BASE_PATH = Path(__file__).resolve().parent.parent
DEBUG = True
PLAYLIST_STEM = []
PLAYLIST_FILENAMES = {}  # Dict of stem → filename
PLUGS = {}
PASSKEYS_PATH = BASE_PATH / "services" / "passkeys.py"

try:
    from .passkeys import ALLOWED_KEYS, SECRET_KEY
except ImportError:
    if PASSKEYS_PATH.exists():
        # File exists but import failed (e.g. syntax error) — don't override
        raise
    print("[Authenticate] passkeys.py not found. Starting init.")
    print("[Authenticate] These keys control API/web access")

    # Prompt for input (won't echo SECRET_KEY if you want extra safety, but let's keep it simple)
    allowed_input = input("[Authenticate] Enter ALLOWED_KEYS (comma-separated, e.g. 'key1,key2'): ").strip()
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

class HasAttachment:
    _has_attachment = False
    @classmethod
    def set_attachment(cls, value: bool):
        cls._has_attachment = value
    @classmethod
    def has_attachment(cls) -> bool:
        return cls._has_attachment

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

