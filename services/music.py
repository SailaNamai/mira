# services.music.py

import subprocess
from PyQt6.QtDBus import QDBusInterface, QDBusConnection
from services import config as g
from services.config import BASE_PATH

PLAYLIST_DIR = BASE_PATH / "playlists"
_clementine_process = None  # Track the subprocess globally

"""
Basic Controls
"""
def _send_mpris_command(method: str):
    """
    Send a command to Clementine via MPRIS using QtDBus.
    """
    try:
        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(
            "org.mpris.MediaPlayer2.clementine",
            "/org/mpris/MediaPlayer2",
            "org.mpris.MediaPlayer2.Player",
            bus
        )
        if iface.isValid():
            iface.call(method)
            print(f"[Music] Sent '{method}' command to Clementine.")
        else:
            print("[Music] Clementine DBus interface not available.")
    except Exception as e:
        print(f"[Music] Failed to send DBus command '{method}': {e}")

def music_play():
    """
    Start Clementine on Ubuntu 24 as a subprocess, or trigger playback if already running.
    """
    global _clementine_process
    try:
        if _clementine_process is None or _clementine_process.poll() is not None:
            _clementine_process = subprocess.Popen(
                ["clementine"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("[Music] Clementine started.")
        else:
            print("[Music] Clementine already running. Sending Play command...")

        _send_mpris_command("Play")
    except Exception as e:
        print(f"[Music] Failed to start or play Clementine: {e}")

def music_pause():
    _send_mpris_command("Pause")

def music_next():
    _send_mpris_command("Next")

def music_previous():
    _send_mpris_command("Previous")

"""
Playlist loader
"""
def _launch_clementine_with_playlist(filename: str):
    """
    Kill Clementine if running, then start it with the given playlist.
    """
    global _clementine_process
    try:
        # Kill existing Clementine process if tracked
        if _clementine_process and _clementine_process.poll() is None:
            _clementine_process.terminate()
            _clementine_process.wait(timeout=5)
            print("[Music] Clementine process terminated.")

        # Build full path to playlist
        path = PLAYLIST_DIR / filename
        if not path.exists():
            print(f"[Music] Playlist file not found: {path}")
            return None

        # Start Clementine with playlist
        _clementine_process = subprocess.Popen(
            ["clementine", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"[Music] Clementine launched with playlist: {filename}")
        return filename
    except Exception as e:
        print(f"[Music] Failed to launch Clementine with playlist: {e}")
        return None

# load playlist
def music_load(command: str):
    """
    Load a playlist by matching a string like 'play BeastSelection'.
    """
    stem = command.strip().lower().removeprefix("play ").strip()

    for key in g.PLAYLIST_STEM:
        if key.lower() == stem:
            filename = g.PLAYLIST_FILENAMES.get(key)
            if filename:
                print(f"[Debug] music_load returned: {filename}")
                return _launch_clementine_with_playlist(filename)

    print(f"[Error] No matching playlist for '{stem}'")
    return None

# Dynamically discover available playlists
def discover_playlists():
    """
    Scan the playlist directory for supported formats and update global playlist mappings.
    """
    supported = {".xspf", ".m3u", ".m3u8", ".pls", ".asx"}
    stem_list = []
    stem_to_filename = {}

    for path in PLAYLIST_DIR.iterdir():
        if path.suffix.lower() in supported and path.is_file():
            stem = path.stem
            stem_list.append(stem)
            stem_to_filename[stem] = path.name

    # Update globals
    g.PLAYLIST_STEM.clear()
    g.PLAYLIST_STEM.extend(stem_list)

    g.PLAYLIST_FILENAMES.clear()
    g.PLAYLIST_FILENAMES.update(stem_to_filename)