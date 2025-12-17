# services.tts_xtts_v2.py

import os
import torch
import torchaudio
import re
import dateparser
from datetime import datetime
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from services.config import BASE_PATH
from services.user_managment import FilePool
from services.db_get import GetDB

model = None
gpt_latent = None
speaker_embedding = None
_tts_socketio = None # We imprint this during every app startup so its available here.
MODEL_DIR = BASE_PATH / "static" / "xtts-v2"
REFERENCE_WAV = MODEL_DIR / "samples" / "en_sample.wav"
CUSTOM_WAV = MODEL_DIR / "samples" / "custom_24k.wav"

SAMPLE_RATE = 24000
LANGUAGE = "en"

def init_tts_service(socketio_instance):
    """Initialize the TTS service with the socketio instance"""
    global _tts_socketio
    _tts_socketio = socketio_instance
    print("[TTS@XTTS-v2] Service initialized with Socket.IO")

def get_xtts_v2_model():
    global model, gpt_latent, speaker_embedding

    # Load to CPU or GPU
    mode = GetDB.get_tts_mode()
    print(f"[TTS@XTTS-v2] Initializing to {mode}...")

    config = XttsConfig()
    config.load_json(os.path.join(MODEL_DIR, "config.json"))

    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=MODEL_DIR, eval=True) # eval=True for inference, eval=False for training

    if mode == "gpu":
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            print("[TTS@XTTS-v2] CUDA not available! Falling back to CPU...")
        model.to(device)
    else:
        model.to("cpu")

    print("[TTS@XTTS-v2] Extracting speaker latents...")
    audio_file = CUSTOM_WAV if CUSTOM_WAV.exists() else REFERENCE_WAV
    gpt_latent, speaker_embedding = model.get_conditioning_latents(audio_path=[audio_file])
    print("[TTS@XTTS-v2] Ready.")


def voice_out(text, user_id, timestamp=None, output_dir=BASE_PATH / "static" / "temp"):
    """Synthesize voice using the globally set socketio instance"""
    global _tts_socketio

    if _tts_socketio is None:
        raise RuntimeError("[TTS@XTTS-v2] Socket.IO not initialized. Call init_tts_service() first.")

    if model is None or gpt_latent is None or speaker_embedding is None:
        raise RuntimeError("[TTS@XTTS-v2] Not initialized. Call get_xtts_v2_model() first.")

    text = normalize_text(text)
    timestamp, chunks = split_into_chunks(text) if timestamp is None else (timestamp, split_into_chunks(text)[1])

    # Get the socket_id for this user (find active device)
    # TODO: Think about which device should play: Current or first? First would enable a stationary speaker with mic...
    socket_id = None
    from services.config import ACTIVE_DEVICES
    for sid, device in ACTIVE_DEVICES.items():
        if device['user_id'] == user_id:
            socket_id = sid
            break

    if not socket_id:
        print(f"[TTS@XTTS-v2] No active socket found for user_id={user_id}")
        return

    print(f"[TTS@XTTS-v2] Starting synthesis for user_id={user_id}, socket_id={socket_id}")

    for i, chunk in enumerate(chunks):
        print(f"[TTS@XTTS-v2] Synthesizing chunk {i + 1}/{len(chunks)}: \"{chunk}\"")
        output = model.inference(
            text=chunk,
            language=LANGUAGE,
            gpt_cond_latent=gpt_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.7,
            length_penalty=1.0,
            repetition_penalty=2.0,
            top_k=50,
            top_p=0.85,
            speed=1.0,
            enable_text_splitting=False
        )

        # Save the chunk using FilePool
        chunk_path = FilePool.get_voice_chunk_path(user_id, timestamp, i + 1)
        torchaudio.save(chunk_path, torch.tensor(output["wav"]).unsqueeze(0), SAMPLE_RATE)

        # Get the URL path
        filename = chunk_path.name
        url_path = f"/static/temp/{filename}"

        # Emit Socket.IO event with the chunk info
        print(f"[TTS@XTTS-v2] Emitting voice_chunk_ready for chunk {i + 1}")
        _tts_socketio.emit('voice_chunk_ready', {
            'user_id': user_id,
            'chunk_index': i + 1,
            'total_chunks': len(chunks),
            'audio_url': url_path,
            'text': chunk
        }, room=socket_id)

    # Emit completion event
    print(f"[TTS@XTTS-v2] Voice synthesis complete for user_id={user_id}")
    _tts_socketio.emit('voice_synthesis_complete', {
        'user_id': user_id,
        'total_chunks': len(chunks),
        'timestamp': timestamp
    }, room=socket_id)

def split_into_chunks(text, max_chars=200):
    # Split by sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter out empty sentences
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return timestamp, []

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    chunks = []

    # Process first sentence separately - always make it the first chunk(s)
    first_sentence = sentences[0]
    # Split first sentence into chunks if it exceeds max_chars
    if len(first_sentence) > max_chars:
        remaining = first_sentence
        while remaining:
            if len(remaining) <= max_chars:
                chunks.append(remaining)
                break
            # Find best split point near max_chars
            split_idx = remaining.rfind(' ', 0, max_chars)
            if split_idx == -1:  # No space found, force split
                split_idx = max_chars
            chunk = remaining[:split_idx].strip()
            chunks.append(chunk)
            remaining = remaining[split_idx:].strip()
    else:
        chunks.append(first_sentence)

    # Process remaining sentences with original grouping logic
    current = ""
    for sentence in sentences[1:]:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current += " " + sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)

    return timestamp, chunks

def clean_voice_chunks(user_id, output_dir=BASE_PATH / "static" / "temp"):
    """Clean voice chunks, optionally for a specific user"""
    # Clean only files for this specific user
    for f in output_dir.glob(f"voice_chunk_{user_id}_*.wav"):
        try:
            f.unlink()
            print(f"[TTS@XTTS-v2] Deleted user-specific file: {f}")
        except Exception as e:
            print(f"[TTS@XTTS-v2] Could not delete {f}: {e}")


def normalize_text(text):
    print("[TTS@XTTS-v2] Normalizing text")
    # Replace DD.MM.YYYY or DD-MM-YYYY or DD/MM/YYYY with spoken English format
    def replace_date(match):
        raw = match.group(0)
        # Try to parse with day-first (common in Europe) then month-first
        parsed = dateparser.parse(raw, settings={'PREFER_DAY_OF_MONTH': 'first'}) or \
                 dateparser.parse(raw, settings={'PREFER_DAY_OF_MONTH': 'last'})
        if not parsed:
            return raw

        day = parsed.day
        month_name = parsed.strftime("%B")  # full month name

        # Ordinal for day (1st, 2nd, 3rd, 4th...)
        ordinal = lambda \
            n: f"{n}th" if 10 <= n % 100 <= 20 else f"{n}{'ts'[-2:] if n % 10 == 1 else 'nd' if n % 10 == 2 else 'rd' if n % 10 == 3 else 'th'}"
        day_spoken = ordinal(day)

        year_spoken = year_to_words(parsed.year)

        # Natural spoken format: "the twenty-third of November, twenty twenty-four"
        # or just "November twenty-third, twenty twenty-four" — both common
        # XTTS sounds excellent with either; many prefer without "the" and "of"
        return f"{month_name} the {day_spoken}, {year_spoken}"

    # Replace HH:MM time format (24-hour or 12-hour) with spoken form
    def replace_time(match):
        raw = match.group(0)
        parsed = dateparser.parse(raw)
        if not parsed:
            return raw
        hour = parsed.hour
        minute = parsed.minute
        hour_spoken = str(hour) if hour > 0 else "zero"
        if minute == 0:
            return f"{hour_spoken} o'clock"
        return f"{hour_spoken} {minute:02d}"

    # Match common date formats
    text = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", replace_date, text)

    # Normalize time (HH:MM or H:MM)
    text = re.sub(r"\b\d{1,2}:\d{2}\b", replace_time, text)

    # Replace mathematical operators with spoken equivalents
    # Minus sign before numbers (e.g., -5, -3.14, -.7)
    text = re.sub(r"-(?=\d)", " minus ", text)
    # Rest of the operators
    operator_map = {
        r"\+\=": "plus equals",
        r"\-\=": "minus equals",
        r"\*\=": "times equals",
        r"\/\=": "divided by equals",
        r"\+\+": "plus plus",
        r"\-\-": "minus minus",
        r"\=\=": "equals equals",
        r"\!\=": "not equals",
        r"\>=": "greater than or equal to",
        r"\<=": "less than or equal to",
        r"\>": "greater than",
        r"\<": "less than",
        r"\=": "equals",
        r"\+": "plus",
    }
    # Apply operator_map
    for pattern, spoken in operator_map.items():
        text = re.sub(pattern, f" {spoken} ", text)

    # Remove Markdown bold markup **, italic markup * and ```
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"```", "", text)

    # --- CURRENCY NORMALIZATION ---
    currency_symbols = {
        r"\$": "dollar",  # USD, AUD, CAD, etc.
        r"\$US": "US dollar",  # explicit
        r"£": "pound",  # GBP
        r"€": "euro",  # EUR
        r"¥": "yen",  # JPY / CNY
        r"¥CN": "yuan",  # explicit Chinese yuan
        r"₹": "rupee",  # INR
        r"₽": "ruble",  # RUB
        r"₩": "won",  # KRW
        r"₿": "bitcoin",  # BTC
        r"Fr": "franc",  # CHF (Swiss franc), also used in some African currencies
        r"R\$": "real",  # BRL
        r"A\$": "Australian dollar",
        r"C\$": "Canadian dollar",
        r"NZ\$": "New Zealand dollar",
    }

    # Amounts with optional decimals and spaces
    currency_pattern = r"""
        (?:
            (?:{symbols})           # currency symbol
            \s*                     # optional space
            ([\d,]+(?:\.\d+)?)      # number: 1,234.56 or 1234 or 1234.5
            |
            ([\d,]+(?:\.\d+)?)      # number first
            \s*
            (?:{symbols})           # then symbol
        )
    """.format(symbols="|".join(re.escape(s) for s in currency_symbols.keys()))

    # Build the regex properly (verbose + ignore case)
    currency_regex = re.compile(currency_pattern, re.VERBOSE | re.IGNORECASE)

    def replace_currency(match):
        # Figure out which part matched
        amount_str = next((g for g in match.groups() if g), "").replace(",", "")
        symbol = None
        for sym in currency_symbols:
            if re.search(re.escape(sym), match.group(0), re.IGNORECASE):
                symbol = sym
                break

        if not amount_str or not symbol:
            return match.group(0)

        # Clean amount
        try:
            amount = float(amount_str)
        except:
            return match.group(0)

        currency_name = currency_symbols[symbol].split()[-1]  # use last word (e.g. "US dollar" → "dollar")

        # Integer part
        dollars = int(amount)
        cents = int(round((amount - dollars) * 100)) if '.' in amount_str else 0

        if cents > 0:
            return f"{number_to_words(dollars)} {currency_name}s and {number_to_words(cents)} cents"
        else:
            if dollars == 1:
                return f"one {currency_name}"
            elif dollars == 0:
                return f"zero {currency_name}s"
            else:
                return f"{number_to_words(dollars)} {currency_name}s"

    # Simple but excellent number-to-words for currency (0–999,999)
    def number_to_words(n: int) -> str:
        if n == 0: return "zero"
        ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen"]
        tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

        if n < 20:
            return ones[n]
        if n < 100:
            return tens[n // 10] + (f"-{ones[n % 10]}" if n % 10 else "")
        if n < 1000:
            return ones[n // 100] + " hundred" + (" " + number_to_words(n % 100) if n % 100 else "")
        if n < 1000000:
            return number_to_words(n // 1000) + " thousand" + (" " + number_to_words(n % 1000) if n % 1000 else "")
        return str(n)

    # Actually apply it
    text = currency_regex.sub(replace_currency, text)

    return text

def year_to_words(year: int) -> str:
    """
    Convert a year (any positive integer) into natural spoken English as used by native speakers
    and preferred by TTS systems like XTTS-v2, Piper, etc.

    Examples:
        1999 → "nineteen ninety nine"
        2009 → "two thousand and nine"  or "twenty oh nine" (both common, we prefer the clearer one)
        1905 → "nineteen oh five"
        2000 → "two thousand"
        2024 → "twenty twenty four"
        1876 → "eighteen seventy six"
        3048 → "three thousand and forty eight"
        987  → "nine hundred and eighty seven"
    """
    if year < 0:
        return str(year)

    s = ""

    if year == 2000:
        return "two thousand"
    if year < 1000:  # e.g. 987
        hundreds = year // 100
        tens = year % 100

        if hundreds:
            s += f"{_small(hundreds)} hundred"
            if tens:
                s += " and "
        if tens:
            s += _small(tens) if tens >= 20 or tens == 0 else f"oh {_small(tens)}"
        return s

    if 1000 <= year < 10000:
        thousands = year // 1000
        remainder = year % 1000

        s = f"{_small(thousands)} thousand"

        if remainder == 0:
            return s  # e.g. 2000, 3000

        if remainder < 100:  # 2005, 1907, 3011 → "oh" style
            if remainder < 10:
                s += f" oh {_small(remainder)}"
            else:
                s += f" {_small(remainder)}"  # 2005 → "two thousand oh five" is also acceptable
        else:
            # 2001-2099, 2100+, etc.
            if thousands >= 2 or remainder >= 100:
                # Modern style: 2001 = "two thousand and one", 2024 = "twenty twenty-four"
                if 100 <= remainder <= 999:
                    hundreds = remainder // 100
                    tens = remainder % 100
                    if hundreds:
                        s += f" {hundreds} hundred"
                        if tens:
                            s += f" and {tens}" if tens < 10 else f" {tens}"
                    else:
                        s += f" and {tens}"
                else:
                    s += f" and {remainder}"
            else:
                # 2000–2019 often spoken as "twenty oh one", "twenty nineteen", etc.
                # But XTTS sounds better with "two thousand and one", "two thousand nineteen"
                if remainder <= 19:
                    s += f" and {_small(remainder)}"
                else:
                    s += f" {_small(remainder)}"

        return s.strip()

    # For years >= 10000, just say the digits (rare anyway)
    return str(year)

# Helper for numbers 0–19 and tens
_small_numbers = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"
]
_tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

def _small(n: int) -> str:
    if n < 20:
        return _small_numbers[n]
    else:
        ten = n // 10
        one = n % 10
        if one == 0:
            return _tens[ten]
        else:
            # Use space instead of hyphen
            return f"{_tens[ten]} { _small_numbers[one] }"