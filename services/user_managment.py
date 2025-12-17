# services.user_management.py

import threading
import time
from contextlib import contextmanager
from pathlib import Path
from services.config import BASE_PATH

########################################################################################
"""############################       APP-Lock         ##############################"""
########################################################################################
class AppState:
    """
    Global mutex manager for critical sections with timeout support
    TODO: Evaluate if this is good enough for 5-10 people at max, which use it occasionally per day.
        - Tendency: Yes, sufficient, but make divide between RAM/VRAM
    """
    _lock = threading.Lock()  # Global lock object
    _holder = None  # Current lock holder identifier
    _start_time = None  # Timestamp when lock was acquired

    @classmethod
    @contextmanager
    def acquire(cls, user_id, timeout=60.0):
        """
        Acquire global lock with timeout protection.
        Blocks until lock is acquired or timeout expires.

        :param timeout: Max wait time in seconds (float)
        :param user_id: int
        :raises TimeoutError: If lock not acquired within timeout
        """
        start_wait = time.time()
        print(f"[AppState] User {user_id} waiting for global lock (timeout={timeout}s)")

        # Try to acquire lock with timeout
        acquired = cls._lock.acquire(timeout=timeout)

        if not acquired:
            wait_time = time.time() - start_wait
            print(f"[AppState] TIMEOUT after {wait_time:.1f}s for User {user_id}")
            raise TimeoutError(
                f"System busy. Please try again."
            )

        # Lock acquired successfully
        cls._holder = user_id
        cls._start_time = time.time()
        hold_time = time.time() - start_wait
        print(f"[AppState] User {user_id} acquired lock after {hold_time:.1f}s")

        try:
            yield  # Executes here
        finally:
            # Always release lock and reset diagnostics
            duration = time.time() - cls._start_time if cls._start_time else 0
            print(f"[AppState] Released lock (held for {duration:.1f}s by User {user_id})")

            cls._holder = None
            cls._start_time = None
            cls._lock.release()

    @classmethod
    def is_busy(cls) -> bool:
        """Check if lock is currently held (non-blocking)"""
        return cls._lock.locked()

    @classmethod
    def get_status(cls) -> dict:
        """Get diagnostic status (for monitoring endpoints)"""
        return {
            "busy": cls.is_busy(),
            "current_holder": cls._holder,
            "hold_duration": (time.time() - cls._start_time) if cls._start_time else 0
        }

########################################################################################
"""############################         Chat           ##############################"""
########################################################################################
from flask import session
from collections import defaultdict

# Thread lock for thread-safe state management
_state_lock = threading.Lock()

class ChatState:
    def __init__(self):
        self.intent = None
        self.user_msg = None
        self.weather = None
        self.picture = None

class ChatStateManager:
    """Manages per-user ChatState instances. This allows us to maintain separate state
    for each authenticated user."""
    _instances = defaultdict(ChatState)

    @classmethod
    def get_state(cls, user_id=None):
        """Get the ChatState instance for the specified user_id.
        If no user_id is provided, attempts to get it from the Flask session.
        This is the main interface that replaces direct access to the old global ChatState."""
        if user_id is None:
            # Get user_id from session if not provided explicitly
            user_id = session.get('user_id')

        with _state_lock:  # Ensure thread safety
            return cls._instances[user_id]

    # TODO: Think about if we need logout or not. Tendency: no
    @classmethod
    def clear_state(cls, user_id=None):
        """Clear the state for a specific user. Useful for logout or cleanup."""
        if user_id is None:
            user_id = session.get('user_id')
        if user_id:
            with _state_lock:
                if user_id in cls._instances:
                    del cls._instances[user_id]

# Helper function to get the current user's ChatState
def get_chat_state():
    """Get the ChatState instance for the current user from session.
    This function serves as a drop-in replacement for the old global ChatState class."""
    return ChatStateManager.get_state()

########################################################################################
"""############################        Files           ##############################"""
########################################################################################
class FilePool:
    """Manages user-specific file paths in the temp directory"""

    # Common file patterns that need user separation
    FILE_PATTERNS = {
        'picture': {'base': 'picture', 'ext': '.jpeg'},
        'output': {'base': 'output', 'ext': '.txt'},
        'barcode': {'base': 'barcode', 'ext': '.jpeg'},
        'input_webm': {'base': 'input', 'ext': '.webm'},
        'input_wav': {'base': 'input', 'ext': '.wav'},
        'voice_chunk': {'base': 'voice_chunk', 'ext': '.wav'}
    }

    @classmethod
    def get_path(cls, file_type, user_id):
        """Get user-specific path for a file type"""
        if file_type not in cls.FILE_PATTERNS:
            raise ValueError(f"Unknown file type: {file_type}")

        pattern = cls.FILE_PATTERNS[file_type]
        filename = f"{pattern['base']}_{user_id}{pattern['ext']}"
        return BASE_PATH / "temp" / filename

    @classmethod
    def get_picture_path(cls, user_id):
        """Convenience method for picture path"""
        return cls.get_path('picture', user_id)

    @classmethod
    def get_output_path(cls, user_id):
        """Convenience method for output.txt path"""
        return cls.get_path('output', user_id)

    @classmethod
    def get_barcode_path(cls, user_id):
        """Convenience method for barcode path"""
        return cls.get_path('barcode', user_id)

    @classmethod
    def get_audio_paths(cls, user_id):
        """Get both audio paths for STT"""
        return (
            cls.get_path('input_webm', user_id),
            cls.get_path('input_wav', user_id)
        )

    @classmethod
    def get_voice_chunk_path(cls, user_id, timestamp, index):
        """Get path for a specific voice chunk"""
        filename = f"voice_chunk_{user_id}_{timestamp}_{index}.wav"
        return BASE_PATH / "static" / "temp" / filename

    @classmethod
    def cleanup_user_files(cls, user_id):
        """Clean up all temporary files for a user"""
        temp_dir = BASE_PATH / "temp"
        static_temp_dir = BASE_PATH / "static" / "temp"

        # Clean temp directory files
        for pattern in cls.FILE_PATTERNS.values():
            filename = f"{pattern['base']}_{user_id}{pattern['ext']}"
            file_path = temp_dir / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                    print(f"[FilePool] Cleaned up: {file_path}")
                except Exception as e:
                    print(f"[FilePool] Cleanup failed for {file_path}: {e}")

        # Clean static temp directory (voice chunks)
        for file in static_temp_dir.glob(f"voice_chunk_{user_id}_*.wav"):
            try:
                file.unlink()
                print(f"[FilePool] Cleaned up voice chunk: {file}")
            except Exception as e:
                print(f"[FilePool] Cleanup failed for {file}: {e}")

    @classmethod
    def ensure_directories(cls):
        """Ensure required directories exist"""
        (BASE_PATH / "temp").mkdir(parents=True, exist_ok=True)
        (BASE_PATH / "static" / "temp").mkdir(parents=True, exist_ok=True)
        (BASE_PATH / "logs").mkdir(parents=True, exist_ok=True)
        (BASE_PATH / "playlists").mkdir(parents=True, exist_ok=True)

# Attachment state handler
class HasAttachment:
    """Manages attachment state per user session"""
    _user_attachments = {}  # {user_id: {'has_attachment': bool, 'is_picture': bool}}

    @classmethod
    def _get_user_state(cls, user_id):
        """Get or initialize attachment state for a user"""
        if user_id not in cls._user_attachments:
            cls._user_attachments[user_id] = {
                'has_attachment': False,
                'is_picture': False
            }
        return cls._user_attachments[user_id]

    @classmethod
    def set_attachment(cls, user_id, value: bool):
        """Set attachment state for specific user"""
        state = cls._get_user_state(user_id)
        state['has_attachment'] = value

    @classmethod
    def set_picture(cls, user_id, value: bool):
        """Set picture state for specific user"""
        state = cls._get_user_state(user_id)
        state['is_picture'] = value

    @classmethod
    def has_attachment(cls, user_id) -> bool:
        """Check if user has attachment"""
        state = cls._get_user_state(user_id)
        return state['has_attachment']

    @classmethod
    def is_picture(cls, user_id) -> bool:
        """Check if user's attachment is a picture"""
        state = cls._get_user_state(user_id)
        return state['is_picture']

    @classmethod
    def clear(cls, user_id):
        """Clear attachment state for user"""
        if user_id in cls._user_attachments:
            del cls._user_attachments[user_id]

    @classmethod
    def clear_all(cls):
        """Clear all attachment states (for cleanup)"""
        cls._user_attachments.clear()

""" Supported Files """
class FileSupport:
    # .rtf we convert with a small function ourselves, PDF by pdfminer.six
    BASE_EXTENSIONS = {
        ".rtf", ".pdf"
    }
    # Already text
    PLAIN_TEXT_EXTENSIONS = {
        ".txt", ".py", ".js", ".ts", ".css", ".html", ".md",
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
            ext in cls.BASE_EXTENSIONS
            or ext in cls.PLAIN_TEXT_EXTENSIONS
            or ext in cls.IMAGE_EXTENSIONS
        )

    @classmethod
    def is_image(cls, file_path: Path) -> bool:
        return file_path.suffix.lower() in cls.IMAGE_EXTENSIONS