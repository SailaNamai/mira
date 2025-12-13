# services.media.py

import requests
from requests.auth import HTTPBasicAuth
import os
import socket
import urllib.parse
from pathlib import Path
from services import config as g
from services.config import BASE_PATH

# Determine if we're running in Docker
IN_DOCKER = os.getenv("IN_DOCKER", "").lower() == "true"

# Get VLC password: use environment variable if in Docker, otherwise default
VLC_PASSWORD = os.getenv("VLC_PASSKEY", "vlcremote") if IN_DOCKER else "vlcremote"

# Playlist dir is fine like this, because its inside .:app
PLAYLIST_DIR = BASE_PATH / "playlists"

def get_vlc_url() -> str:
    """
    Get VLC base URL based on execution environment (Docker or host).

    Returns:
        str: Base URL for VLC HTTP interface
    """
    if IN_DOCKER:
        try:
            # In Docker, use host.docker.internal to access host machine
            host_ip = socket.gethostbyname("host.docker.internal")
        except Exception:
            # Fallback to localhost if host.docker.internal is unavailable
            host_ip = "127.0.0.1"
    else:
        # On host machine, use localhost directly
        host_ip = "127.0.0.1"

    return f"http://{host_ip}:8080"

def convert_to_host_path(container_path: str) -> str:
    """
    Convert a container path to the corresponding host path when running in Docker.

    Args:
        container_path: Path as seen inside the container

    Returns:
        str: Corresponding path on the host machine
    """
    if not IN_DOCKER:
        return container_path

    try:
        # Get the host base path from environment variable
        host_base = os.getenv("CONTAINER_PATH", "")

        if not host_base:
            raise ValueError("CONTAINER_PATH environment variable not set")

        # Convert to Path objects for safe manipulation
        container_path_obj = Path(container_path)
        container_base_obj = Path("/app")  # Container mount point
        host_base_obj = Path(host_base)

        # Check if the path is under the container base directory
        if container_path_obj.is_relative_to(container_base_obj):
            relative_path = container_path_obj.relative_to(container_base_obj)
            host_path = host_base_obj / relative_path
            return str(host_path.resolve())
        else:
            # If not under container base, try to handle it reasonably
            print(f"[Warning] Path not under container base (/app): {container_path}")
            # Try to use just the filename in the host base directory
            return str(host_base_obj / container_path_obj.name)

    except Exception as e:
        print(f"[Error] Failed to convert path: {e}")
        return container_path


def vlc_request(endpoint: str, params: dict = None) -> requests.Response:
    """
    Make authenticated request to VLC web interface.

    Args:
        endpoint: API endpoint path
        params: Query parameters for the request

    Returns:
        requests.Response: Response from VLC server
    """
    url = f"{get_vlc_url()}{endpoint}"
    try:
        response = requests.get(
            url,
            auth=HTTPBasicAuth('', VLC_PASSWORD),
            params=params,
            timeout=10
        )
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"[Media] VLC request failed: {e}")
        return None

def media_play() -> None:
    """
    Start playback in VLC.
    """
    vlc_request("/requests/status.json", {"command": "pl_play"})


def media_pause() -> None:
    """
    Pause current playback in VLC.
    """
    vlc_request("/requests/status.json", {"command": "pl_pause"})


def media_next() -> None:
    """
    Skip to the next track in playlist.
    """
    vlc_request("/requests/status.json", {"command": "pl_next"})


def media_previous() -> None:
    """
    Skip to the previous track in playlist.
    """
    vlc_request("/requests/status.json", {"command": "pl_previous"})

def playlist_load(command: str) -> str:
    """
    Load a playlist by name from command string.

    Args:
        command: Command string containing playlist name (e.g., "play BeastSelection")

    Returns:
        str: Name of loaded playlist file, or None if not found
    """
    stem = command.strip().lower().removeprefix("play ").strip()

    for key in g.PLAYLIST_STEM:
        if key.lower() == stem:
            filename = g.PLAYLIST_FILENAMES.get(key)
            if filename:
                path = PLAYLIST_DIR / filename
                if path.exists():
                    print(f"[Media] Loading playlist: {filename}")
                    print(f"[Media] Container path: {path}")
                    load_playlist_file(str(path))
                    return filename
                else:
                    print(f"[Media] Playlist file not found: {path}")
                    return None

    print(f"[Error] No matching playlist for '{stem}'")
    return None

def load_playlist_file(playlist_path: str) -> None:
    """
    Load a playlist file directly into VLC.

    This function handles the path conversion for VLC (host machine).

    Args:
        playlist_path: Path to the playlist file as seen in container
    """
    try:
        print(f"[Media] Container playlist path: {playlist_path}")

        # Only convert path for VLC if we're in Docker
        if IN_DOCKER:
            host_playlist_path = convert_to_host_path(playlist_path)
            print(f"[Media] Host playlist path for VLC: {host_playlist_path}")
            final_path = host_playlist_path
        else:
            final_path = playlist_path

        # Clear current playlist
        vlc_request("/requests/status.json", {"command": "pl_empty"})

        # Create proper file URL for VLC
        playlist_url = create_vlc_file_url(final_path)
        print(f"[Media] VLC playlist URL: {playlist_url}")

        # Add the entire playlist file to VLC
        response = vlc_request("/requests/status.json", {
            "command": "in_play",
            "input": playlist_url
        })

        if response:
            print("[Media] Successfully loaded playlist file into VLC")
        else:
            print("[Media] Failed to load playlist file into VLC")

    except Exception as e:
        print(f"[Media] Failed to load playlist: {e}")

def create_vlc_file_url(file_path: str) -> str:
    """
    Create a properly formatted file:// URL for VLC.

    Args:
        file_path: File system path

    Returns:
        str: Properly formatted file:// URL
    """
    # Ensure path is absolute
    absolute_path = Path(file_path).resolve()

    # Convert to string and replace backslashes with forward slashes
    path_str = str(absolute_path).replace('\\', '/')

    # URL encode special characters but preserve slashes
    encoded_path = urllib.parse.quote(path_str, safe='/')

    return f"file://{encoded_path}"

def discover_playlists() -> None:
    """
    Scan the playlist directory and update global playlist mappings.

    This function discovers all supported playlist files and updates the
    global configuration with available playlist names and filenames.
    """
    supported_extensions = {".xspf", ".m3u", ".m3u8", ".pls", ".asx"}
    stem_list = []
    stem_to_filename = {}

    # Always use container path for discovery - this runs inside the container
    print(f"[Media] Discovering playlists in: {PLAYLIST_DIR}")
    if not PLAYLIST_DIR.exists():
        print(f"[Media] Warning: Playlist directory does not exist: {PLAYLIST_DIR}")
        PLAYLIST_DIR.mkdir(parents=True, exist_ok=True)

    for path in PLAYLIST_DIR.iterdir():
        if path.suffix.lower() in supported_extensions and path.is_file():
            stem = path.stem
            stem_list.append(stem)
            stem_to_filename[stem] = path.name
            print(f"[Media] Found playlist: {stem}: {path.name}")

    # Update global configuration
    g.PLAYLIST_STEM.clear()
    g.PLAYLIST_STEM.extend(stem_list)

    g.PLAYLIST_FILENAMES.clear()
    g.PLAYLIST_FILENAMES.update(stem_to_filename)

    print(f"[Media] Discovered {len(stem_list)} playlists: {stem_list}")