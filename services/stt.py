from vosk import Model, KaldiRecognizer
import wave
import json
import time
import os
import subprocess
import tempfile
import shutil
from services.config import BASE_PATH

# Define model path and sample rate
vosk_model_path = BASE_PATH / "static" / "vosk-model-en-us-0.42-gigaspeech"
please_helper_path = BASE_PATH / "static" / "sounds" / "please.wav"
sample_rate = 16000
_model = None

def get_vosk_model():
    global _model
    if _model is None:
        model_path_str = str(vosk_model_path)
        if not os.path.exists(model_path_str):
            raise ValueError(f"[STT] Vosk model path does not exist: {model_path_str}")
        print("[STT] Loading Vosk model into memory...")
        _model = Model(model_path_str)
    return _model


def prepend_wake_audio(audio_path, wake_word="please"):
    """
    Prepends '{wake_word}.wav' if it exists.
    Returns:
        (used_audio_path, temp_dir_or_None, wake_info)
    where wake_info = {
        "word": str or None,
        "duration": float (seconds) or 0.0
    }
    """
    wake_audio_path = BASE_PATH / "static" / "sounds" / f"{wake_word}.wav"

    if not wake_audio_path.exists():
        print(f"[STT] Warning: wake word audio '{wake_word}.wav' not found. Skipping prepend.")
        return str(audio_path), None, {"word": None, "duration": 0.0}

    # Get duration of wake word audio (to know how much to trim later)
    try:
        with wave.open(str(wake_audio_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            wake_duration = frames / float(rate)
    except Exception as e:
        print(f"[STT] Failed to read wake audio duration: {e}. Falling back.")
        return str(audio_path), None, {"word": None, "duration": 0.0}

    temp_dir = tempfile.mkdtemp()
    merged_path = os.path.join(temp_dir, "merged_input.wav")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(wake_audio_path),
        "-i", str(audio_path),
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a_out]",
        "-map", "[a_out]",
        "-c:a", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        merged_path
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"[STT] Prepended '{wake_word}' ({wake_duration:.2f}s) → {merged_path}")
        return merged_path, temp_dir, {"word": wake_word, "duration": wake_duration}
    except subprocess.CalledProcessError as e:
        print(f"[STT] FFmpeg failed: {e.stderr}. Falling back to original.")
        shutil.rmtree(temp_dir)
        return str(audio_path), None, {"word": None, "duration": 0.0}

def transcribe_audio(audio_path, prepend_wake=True, wake_word="please"):
    temp_dir = None
    wake_info = {"word": None, "duration": 0.0}

    if prepend_wake:
        print(f"[STT] Prepending wake word '{wake_word}' to: {audio_path}")
        audio_path, temp_dir, wake_info = prepend_wake_audio(audio_path, wake_word)

    try:
        wf = wave.open(str(audio_path), "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != sample_rate:
            raise ValueError("[STT] Audio must be 16-bit mono WAV at 16kHz")

        rec = KaldiRecognizer(get_vosk_model(), sample_rate)
        rec.SetWords(True)

        segments = []
        start_time = time.time()

        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if "result" in result:
                    segments.extend(result["result"])

        final_result = json.loads(rec.FinalResult())
        if "result" in final_result:
            segments.extend(final_result["result"])

        full_text = final_result.get("text", "").strip()
        duration = time.time() - start_time

        # ===== TRIM WAKE WORD FROM TRANSCRIPTION =====
        trimmed_segments = segments
        trimmed_text = full_text

        if wake_info["word"] and segments:
            word = wake_info["word"]
            # Try exact match on first word(s)
            # Vosk segments are per-word with "word" field
            trimmed_segments = []
            consumed_time = 0.0
            wake_done = False

            for seg in segments:
                # Stop trimming once we've passed wake_duration
                if not wake_done and seg["end"] <= wake_info["duration"] + 0.05:  # +50ms tolerance
                    # Candidate for wake word
                    token = seg["word"].lower().strip(".,!?\"'() ")
                    if token == word.lower():
                        # Match! Skip this segment
                        consumed_time = seg["end"]
                        continue  # drop it
                    else:
                        # Doesn't match — wake word may be multi-word or misrecognized
                        # → fallback: keep all, or log
                        print(f"[STT] Wake word mismatch: expected '{word}', got '{token}' at t={seg['start']:.2f}s")
                        # Optional: stricter policy — break and keep all if first word ≠ wake_word?
                trimmed_segments.append(seg)

            # Rebuild text from remaining segments
            trimmed_text = " ".join(seg["word"] for seg in trimmed_segments).strip()

        print(f"[STT] Transcription complete. Duration: {duration:.2f}s")
        print(f"[STT] Original text: '{full_text}' \n Trimmed: '{trimmed_text}'")

        return {
            "text": trimmed_text,
            "segments": [
                {"start": seg["start"], "end": seg["end"], "text": seg["word"]}
                for seg in trimmed_segments
            ],
            "language": "en",
            "language_probability": 1.0,
            "duration": duration
        }

    except Exception as e:
        print(f"[STT] Error during transcription: {e}")
        raise
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir)
            print(f"[STT] Cleaned up temp dir: {temp_dir}")