#!/bin/bash
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Starting XTTS-v2 download ==="
if [ -d "$BASE_DIR/static/xtts-v2" ]; then
  echo "XTTS-v2 already present, skipping."
else
  mkdir -p "$BASE_DIR/static"
  if ! command -v git-lfs &> /dev/null; then
    echo "git-lfs not found, installing..."
    sudo apt update && sudo apt install -y git-lfs
    git lfs install
  fi
  git clone https://huggingface.co/coqui/XTTS-v2 "$BASE_DIR/static/xtts-v2"
fi
echo "=== Finished XTTS-v2 download ==="

echo "=== Starting Vosk download ==="
if [ -d "$BASE_DIR/static/vosk-model-en-us-0.42-gigaspeech" ]; then
  echo "Vosk model already present, skipping."
else
  mkdir -p "$BASE_DIR/static"
  wget --show-progress -O "$BASE_DIR/vosk.zip" \
    https://alphacephei.com/vosk/models/vosk-model-en-us-0.42-gigaspeech.zip
  unzip -o "$BASE_DIR/vosk.zip" -d "$BASE_DIR/static"
  rm "$BASE_DIR/vosk.zip"
  # If unzip created a nested folder, flatten it
  if [ -d "$BASE_DIR/static/vosk-model-en-us-0.42-gigaspeech/vosk-model-en-us-0.42-gigaspeech" ]; then
    mv "$BASE_DIR/static/vosk-model-en-us-0.42-gigaspeech/vosk-model-en-us-0.42-gigaspeech" \
       "$BASE_DIR/static/vosk-model-en-us-0.42-gigaspeech.tmp"
    rm -rf "$BASE_DIR/static/vosk-model-en-us-0.42-gigaspeech"
    mv "$BASE_DIR/static/vosk-model-en-us-0.42-gigaspeech.tmp" \
       "$BASE_DIR/static/vosk-model-en-us-0.42-gigaspeech"
  fi
fi
echo "=== Finished Vosk download ==="

echo "=== Starting Qwen3 text model download ==="
if [ -f "$BASE_DIR/Qwen3-8B-UD-Q6_K_XL.gguf" ]; then
  echo "Qwen3 text model already present, skipping."
else
  wget --show-progress -O "$BASE_DIR/Qwen3-8B-UD-Q6_K_XL.gguf" \
    "https://huggingface.co/unsloth/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-UD-Q6_K_XL.gguf?download=true"
fi
echo "=== Finished Qwen3 text model download ==="

echo "=== Starting Qwen3 VL model download ==="
if [ -f "$BASE_DIR/Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf" ]; then
  echo "Qwen3 VL model already present, skipping."
else
  wget --show-progress -O "$BASE_DIR/Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf" \
    "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf?download=true"
fi
echo "=== Finished Qwen3 VL model download ==="

echo "=== Starting Qwen3 mmproj download ==="
if [ -f "$BASE_DIR/Qwen3-VL-8B-Instruct-mmproj-F16.gguf" ]; then
  echo "Qwen3 mmproj already present, skipping."
else
  wget --show-progress -O "$BASE_DIR/Qwen3-VL-8B-Instruct-mmproj-F16.gguf" \
    "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/mmproj-F16.gguf?download=true"
fi
echo "=== Finished Qwen3 mmproj download ==="

echo "Downloads complete."
