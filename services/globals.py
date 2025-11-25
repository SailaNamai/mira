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
ALLOWED_KEYS = {"leon_darf_rein", "secret_key_a1b2c3"}
SECRET_KEY = 'i_shall_pass'

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

