# services.stt_distil_whisper.py

import psutil
import torch
import numpy as np
import time
import os
import soundfile as sf
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from transformers.utils import is_torch_sdpa_available
from services.config import BASE_PATH

# Define model path and configuration
distil_whisper_model_path = BASE_PATH / "static" / "distil-whisper"
sample_rate = 16000
max_new_tokens = 128  # Optimal for most voice commands
_model = None
_processor = None
_pipe = None

def get_distil_whisper_model(stt_mode):
    """
    Initialize and load the Distil-Whisper model with adaptive settings for different (CPU) hardware.
    """
    global _model, _processor, _pipe

    # Check if model files exist locally
    model_path_str = str(distil_whisper_model_path)
    if not os.path.exists(model_path_str):
        raise ValueError(f"[STT@Distil-Whisper] Model path does not exist: {model_path_str}")

    print(f"[STT@Distil-Whisper] Loading model with mode: {stt_mode}")
    try:
        # Determine device based on stt_mode and availability
        if stt_mode == "gpu" and torch.cuda.is_available():
            device = "cuda:0"
            dtype = torch.float16
            print("[STT@Distil-Whisper] Using GPU with float16 precision")
            batch_size = 16

            # GPU-specific optimizations
            torch.backends.cudnn.benchmark = True
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True

        else:
            # Get CPU info with psutil and adjust arguments accordingly
            device = "cpu"
            dtype = torch.float32

            try:
                cpu_count = psutil.cpu_count(logical=False) or 4  # Physical cores
                total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)
                print(f"[STT@Distil-Whisper] Hardware detected: {cpu_count} physical cores, {total_ram_gb:.1f}GB RAM")
            except ImportError:
                print("[STT@Distil-Whisper] psutil not available. Using default hardware detection.")
                import multiprocessing
                cpu_count = multiprocessing.cpu_count() // 2 or 4  # Estimate physical cores
                total_ram_gb = 16  # Default assumption

            # Adaptive thread configuration based on CPU capabilities
            if cpu_count >= 16:
                num_threads = min(24, cpu_count * 2)  # i9/Ryzen 9 tier
                batch_size = 12
                print(f"[STT@Distil-Whisper] High-end CPU detected: {cpu_count} cores. Using {num_threads} threads.")
            elif cpu_count >= 8:
                num_threads = min(12, cpu_count * 2)  # i7/Ryzen 7 tier
                batch_size = 8
                print(f"[STT@Distil-Whisper] Mid-range CPU detected: {cpu_count} cores. Using {num_threads} threads.")
            elif cpu_count >= 4:
                num_threads = min(8, cpu_count * 2)  # i5/Ryzen 5 tier
                batch_size = 6
                print(f"[STT@Distil-Whisper] Entry-level CPU detected: {cpu_count} cores. Using {num_threads} threads.")
            else:
                num_threads = max(2, cpu_count * 2)  # Low-power systems
                batch_size = 4
                print(
                    f"[STT@Distil-Whisper] Low-power system detected: {cpu_count} cores. Using {num_threads} threads.")

            # Reduce settings if RAM is limited
            if total_ram_gb < 16:
                batch_size = max(2, batch_size // 2)
                print(f"[STT@Distil-Whisper] Limited RAM ({total_ram_gb:.1f}GB): Reducing batch size to {batch_size}")
            if total_ram_gb < 8:
                num_threads = min(8, num_threads)
                batch_size = max(2, batch_size // 2)
                print(
                    f"[STT@Distil-Whisper] Very limited RAM ({total_ram_gb:.1f}GB): Further reducing batch size to {batch_size}")

            # Apply CPU optimizations
            torch.set_num_threads(num_threads)
            torch.set_num_interop_threads(num_threads)
            torch.set_flush_denormal(True)  # Prevent denormal slowdowns

            # Intel-specific optimizations (safe to set even on AMD)
            os.environ["OMP_NUM_THREADS"] = str(num_threads)
            os.environ["KMP_BLOCKTIME"] = "0"
            os.environ["KMP_AFFINITY"] = "granularity=fine,compact,1,0"
            os.environ["KMP_SETTINGS"] = "1"

            if stt_mode.lower() == "gpu":
                print("[STT@Distil-Whisper] Warning: GPU requested but not available. Falling back to CPU.")

        # Load model with optimizations
        print("[STT@Distil-Whisper] Loading model weights...")

        model_kwargs = {
            "dtype": dtype,
            "low_cpu_mem_usage": True,
            "use_safetensors": True,
            "local_files_only": True,
        }

        # Use SDPA if available and if on CPU; Flash attention for GPU is unlikely to be helpful
        if device.startswith("cpu"):
            if is_torch_sdpa_available():
                model_kwargs["attn_implementation"] = "sdpa" # "Expected type 'dtype | bool' (matched generic type '_VT'), got 'str' instead" is not an issue here
                print("[STT@Distil-Whisper] SDPA (Scaled Dot Product Attention): Enabled for CPU optimization")
            else:
                print("[STT@Distil-Whisper] SDPA not available: Using standard attention")

        # Load model
        _model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_path_str,
            **model_kwargs
        )

        # Move model to device
        _model.to(device)

        # Load processor
        print("[STT@Distil-Whisper] Loading processor...")
        _processor = AutoProcessor.from_pretrained(
            model_path_str,
            local_files_only=True
        )

        # Create pipeline with adaptive settings
        print("[STT@Distil-Whisper] Creating pipeline...")

        # Handle chunk_length_s warning appropriately
        pipeline_kwargs = {
            "task": "automatic-speech-recognition",
            "model": _model,
            "tokenizer": _processor.tokenizer,
            "feature_extractor": _processor.feature_extractor,
            "max_new_tokens": max_new_tokens,
            "batch_size": batch_size,
            "dtype": dtype,  # torch_dtype is deprecated
            "device": device,
            # Handle the chunk_length_s warning
            "chunk_length_s": 25,  # Optimal for distil-large-v3
        }

        # Add ignore_warning if we're using chunk_length_s with seq2seq models
        pipeline_kwargs["ignore_warning"] = True

        _pipe = pipeline(**pipeline_kwargs)

        print(f"[STT@Distil-Whisper] Model loaded successfully on: {device.upper()}. With batch size: {batch_size}.")
        if device == "cpu":
            print(
                f"[STT@Distil-Whisper] Thread config: {torch.get_num_threads()} intra-op, {torch.get_num_interop_threads()} inter-op")
        return _model, _processor, _pipe

    except Exception as e:
        print(f"[STT@Distil-Whisper] Failed to load model: {e}")
        # Clean up on failure to avoid partial loading
        _model, _processor, _pipe = None, None, None
        raise

def load_audio_file(file_path):
    """
    Load audio file and return the audio array with sampling rate for whisper.
    """
    try:
        # Use soundfile as sf to load audio file
        audio_array, sampling_rate = sf.read(str(file_path))

        # Convert to mono if stereo
        if len(audio_array.shape) > 1:
            audio_array = np.mean(audio_array, axis=1)

        return audio_array, sampling_rate

    except Exception as e:
        print(f"[STT@Distil-Whisper] Error loading audio file: {e}")
        raise

def transcribe_audio(audio_path):
    """
    Transcribe audio using Distil-Whisper - simplified for frontend compatibility.
    Frontend only needs the transcribed text in a simple structure.
    """
    global _pipe

    if _pipe is None:
        raise RuntimeError("[STT@Distil-Whisper] Model not initialized. Call get_distil_whisper_model() first.")

    try:
        start_time = time.time()

        # Load audio file
        print(f"[STT@Distil-Whisper] Loading audio file: {audio_path}")
        audio_array, sampling_rate = load_audio_file(audio_path)

        # Simple transcription
        print(f"[STT@Distil-Whisper] Transcribing audio...")
        # noinspection PyCallingNonCallable
        result = _pipe(audio_array)

        full_text = result["text"].strip()
        duration = time.time() - start_time

        print(f"[STT@Distil-Whisper] Transcription complete. Duration: {duration:.2f}s")
        print(f"[STT@Distil-Whisper] Text: '{full_text}'")

        # Return structure
        return {
            "text": full_text,
            "duration": duration
        }

    except Exception as e:
        print(f"[STT@Distil-Whisper] Error during transcription: {e}")
        # Return consistent structure even on failure
        return {
            "text": "",
            "duration": 0
        }