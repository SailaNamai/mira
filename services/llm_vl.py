# services.llm_vl.py

import base64
import os
import re

import services.globals as g # for llm_vl

# MIME map
_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

def image_inference(image_path: str, user_msg: str) -> str | None:
    """
    Run inference on the given image with a custom user message.
    Returns the raw model output (string) or None if empty.
    """
    if g.llm_vl is None:
        raise RuntimeError("[VL] Model not initialized. Call init_qwen_vl() first.")

    data_uri = image_to_base64_data_uri(image_path)

    messages = [
        {"role": "system", "content": "You are a vision-language assistant."},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": user_msg},
            ],
        },
    ]

    res = g.llm_vl.create_chat_completion(
        messages=messages,
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        presence_penalty=1.5,
    )

    text = res["choices"][0]["message"]["content"].strip()
    return text if text else None

def image_to_base64_data_uri(file_path: str) -> str:
    """
    Convert local image file to base64 data URI with correct MIME type.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Image file not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    mime_type = _IMAGE_MIME_TYPES.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{encoded}"


def scan_barcode(image_path: str) -> str | None:
    """
    Run inference on the given image and return the barcode digits.
    """
    if g.llm_vl is None:
        raise RuntimeError("[VL] Model not initialized. Call init_qwen_vl() first.")

    data_uri = image_to_base64_data_uri(image_path)

    messages = [
        {"role": "system", "content": "You are a barcode reader. Emit only the numeric code."},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": "Emit the code in this image and nothing else."},
            ],
        },
    ]

    res = g.llm_vl.create_chat_completion(messages=messages, temperature=0.0)
    text = res["choices"][0]["message"]["content"].strip()

    # Defensive parse: extract first long digit sequence
    match = re.search(r"\b\d{8,}\b", text)
    if match:
        return match.group(0)

    print(f"[VL] No barcode found in output: {text}")
    return None
