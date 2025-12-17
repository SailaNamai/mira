# services.config.py

import os
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

# Returns host IP
def get_local_ip():
    """Return host IP if running in Docker, else local machine IP."""
    if os.getenv("IN_DOCKER", "").lower() == "true":
        try:
            # Needs extra_hosts: host.docker.internal:host-gateway in compose
            return socket.gethostbyname("host.docker.internal")
        except Exception:
            return "127.0.0.1"
    else:
        # Fallback: discover local IP by connecting to a public address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

@contextmanager
def suppress_stdout_stderr():
    """
    Redirect stdout/stderr to a dummy buffer temporarily.
    Is only active during .gguf load.
    # Disable the call to this function if a model crashes.
    """
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
MAX_CONTEXT = 6144 # TODO: Frontend setting and write to DB

def init_qwen():
    """
    Initialize Qwen3 at startup on GPU/CPU depending on settings.
    """
    mode = GetDB.get_llm_mode()
    print(f"[LLM] Model initializing on {mode}...")
    if mode == "cpu":
        gpu_layers = 0
    else:
        gpu_layers = -1

    global llm
    """
    model_path=MODEL_PATH
    print(f"[DEBUG] Model path: {model_path}")
    print(f"[DEBUG] File exists: {os.path.exists(model_path)}")
    print(f"[DEBUG] File size: {os.path.getsize(model_path)} bytes" if os.path.exists(model_path) else "File not found")
    print(f"[DEBUG] File permissions: {oct(os.stat(model_path).st_mode)[-3:]}" if os.path.exists(model_path) else "N/A")
    print(f"[DEBUG] Current working directory: {os.getcwd()}")
    """
    with suppress_stdout_stderr(): # remove this wrap for debug info if model crashes
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
            verbose=True,
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
    Initialize Qwen3-VL at startup.
    """
    mode = GetDB.get_llm_vl_mode()
    print(f"[LLM VL] Model initializing on {mode}...")
    if mode == "cpu":
        gpu_layers = 0
    else:
        gpu_layers = -1

    global llm_vl

    with suppress_stdout_stderr(): # remove this wrap when needing to debug the VL model
        llm_vl = Llama(
            model_path=str(MODEL_PATH_VL),
            chat_handler=Qwen3VLChatHandler( # PyCharm complaint is wrong (custom Handler).
                clip_model_path=str(MMPROJ_PATH),
                force_reasoning=False,
            ),
            n_gpu_layers=gpu_layers,
            n_ctx=2048, # This seems to work well with my phones camera
            n_threads=16,
            swa_full=True,
            verbose=True,
        )
    print("[LLM VL] Model initialized and warmed up.")

########################################################################################
"""############################   Resource Validation  ##############################"""
########################################################################################
import psutil
import torch
from typing import Optional, Tuple, Dict
from services.db_persist import persist_resource_safety_overrides

def enforce_resource_safety():
    """Main function to enforce resource safety at startup."""
    print("[Startup] Checking system resources for safe operation...")

    try:
        # Step 1: Determine safe modes based on resources
        recommended_modes = determine_safe_compute_modes()

        print("[Startup] Recommended safety modes:")
        print(f"[Startup] LLM mode: '{recommended_modes['llm_mode']}'")
        print(f"[Startup] VL-LLM mode: '{recommended_modes['llm_vl_mode']}'")
        print(f"[Startup] TTS mode: '{recommended_modes['tts_mode']}'")

        # Step 2: Persist these recommendations to database if needed
        overrides_applied = persist_resource_safety_overrides(recommended_modes)

        if overrides_applied:
            print("[Startup] Resource safety override applied.")
        else:
            print("[Startup] Resource settings already sane.")

        return True

    except Exception as e:
        print(f"[Startup] Resource safety check failed: {e}")
        print("[Startup] Continuing with existing settings - models may crash if resources are insufficient")
        return False

def determine_safe_compute_modes() -> Dict[str, str]:
    """
    Validates current database settings against available system resources.
    Only corrects settings that would cause out-of-memory errors.
    Respects user preferences when resources allow.

    Returns a dictionary with corrected modes where needed.
    """
    # Get resource information
    total_vram, free_vram = get_cuda_vram_info()
    total_ram, avail_ram = get_system_ram_info()

    # Convert to GB for easier comparison
    total_vram_gb = total_vram / (1024 ** 3) if total_vram else 0
    free_vram_gb = free_vram / (1024 ** 3) if free_vram else 0
    avail_ram_gb = avail_ram / (1024 ** 3)

    print(f"[Resource Check] Available RAM: {avail_ram_gb:.1f}GB")
    if total_vram is not None:
        print(f"[Resource Check] VRAM: {free_vram_gb:.1f}/{total_vram_gb:.1f}GB free/total")
    else:
        print("[Resource Check] No CUDA GPU detected")
        total_vram_gb = 0  # Ensure no GPU modes are allowed

    # Get current settings from database (user's preferences)
    from services.db_get import GetDB

    current_settings = {
        'llm_mode': GetDB.get_llm_mode(),
        'llm_vl_mode': GetDB.get_llm_vl_mode(),
        'tts_mode': GetDB.get_tts_mode()
    }

    print(f"[Resource Check] Current settings from DB:")
    print(f"[Resource Check] LLM mode: '{current_settings['llm_mode']}'")
    print(f"[Resource Check] VL-LLM mode: '{current_settings['llm_vl_mode']}'")
    print(f"[Resource Check] TTS mode: '{current_settings['tts_mode']}'")

    # Start with current settings
    recommendations = current_settings.copy()

    # Safeguard 1: VL-LLM on GPU requires 24GB+ VRAM
    if current_settings['llm_vl_mode'] == 'gpu' and total_vram_gb < 23.0: # 24 is too aggressive
        recommendations['llm_vl_mode'] = 'cpu'
        print(
            f"[Resource Check] Correcting VL-LLM mode from 'gpu' to 'cpu' - insufficient VRAM ({total_vram_gb:.1f}GB < 24GB required for VL-LLM)")

    # Safeguard 2: LLM on GPU requires 16GB+ VRAM
    if current_settings['llm_mode'] == 'gpu' and total_vram_gb < 15.0: # 16 is too aggressive
        recommendations['llm_mode'] = 'cpu'
        print(
            f"[Resource Check] Correcting LLM mode from 'gpu' to 'cpu' - insufficient VRAM ({total_vram_gb:.1f}GB < 16GB required for LLM)")

    # Safeguard 3: TTS on GPU requires 8GB+ VRAM
    if current_settings['tts_mode'] == 'gpu' and total_vram_gb < 7.0: # 8 is too aggressive
        recommendations['tts_mode'] = 'cpu'
        print(
            f"[Resource Check] Correcting TTS mode from 'gpu' to 'cpu' - insufficient VRAM ({total_vram_gb:.1f}GB < 8GB required for TTS)")

    # Additional safeguard: If no CUDA available, force everything to CPU
    if total_vram is None:
        for mode in ['llm_mode', 'llm_vl_mode', 'tts_mode']:
            if recommendations[mode] == 'gpu':
                recommendations[mode] = 'cpu'
                print(f"[Resource Check] No CUDA available - forcing {mode} from 'gpu' to 'cpu'")

    # RAM warning
    if avail_ram_gb < 32.0:
        print(
            f"[Resource Check] Low available RAM ({avail_ram_gb:.1f}GB < 32GB recommended). Performance may be impacted.")

    # Report what changed
    for key in current_settings:
        if current_settings[key] != recommendations[key]:
            print(
                f"[Resource Check] SAFEGUARD APPLIED: {key} changed from '{current_settings[key]}' to '{recommendations[key]}'")

    return recommendations

def get_cuda_vram_info() -> Tuple[Optional[int], Optional[int]]:
    """
    Returns (total_vram_bytes, free_vram_bytes) using PyTorch CUDA.
    Returns (None, None) if CUDA is not available.
    """
    try:
        if torch.cuda.is_available():
            torch.cuda.init()  # Ensure CUDA is initialized
            free_vram, total_vram = torch.cuda.mem_get_info()
            return total_vram, free_vram
        return None, None
    except Exception as e:
        print(f"[Resource Check] CUDA error: {e}")
        return None, None

def get_system_ram_info() -> Tuple[int, int]:
    """Returns (total_ram_bytes, available_ram_bytes)."""
    mem = psutil.virtual_memory()
    return mem.total, mem.available

########################################################################################
"""############################        Various         ##############################"""
########################################################################################

# media
PLAYLIST_STEM = []
PLAYLIST_FILENAMES = {}  # Dict of stem:filename
# Tasmota plugs
PLUGS = {}
# user devices
ACTIVE_DEVICES = {}  # {socket_id: {'user_id': int, 'device_name': str}}