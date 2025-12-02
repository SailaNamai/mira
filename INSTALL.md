I'm doing this on a rtx4080 super with 
```
Ubuntu 24 LTS
Driver Version: 580.105.08
CUDA Version: 13.0
```  

### **Clone the repo, then:**

### CUDA
This should be pretty straight forward.
Confirm your GPU supports it:

```lspci | grep -i nvidia```

Then reference with:
https://developer.nvidia.com/cuda-gpus

Nvidia provides an (extensive) guide - you can search for simpler guides or ask a smart model with web search.
https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html

Check success with

```nvcc --version```

### Downloads:

**Vosk**, **XTTS-v2**, **LLM**: 

Choose vosk-model-en-us-0.42-gigaspeech and extract to ```.../mira/static/vosk-model-en-us-0.42-gigaspeech.```

```https://alphacephei.com/vosk/models```

Place XTTS-v2 in ```.../mira/static/xtts-v2.```

```https://huggingface.co/coqui/XTTS-v2```

Any **non vl** Qwen3 model should work. I use Unsloth 8b at Q6K (use gguf).
Smaller than 8b might not do well with intent recognition.

Place at ```.../mira/```

Adjust this line in ```.../mira/services/llm_config.py```: 

```MODEL_PATH = BASE_PATH / "Qwen3-8B-UD-Q6_K_XL.gguf"``` 

```https://huggingface.co/models?search=qwen3```

For Qwen3 VL choose any VL model and download the model(gguf)+mmproj-F16

Place at ```.../mira/```

Adjust these lines in ```.../mira/services/globals.py```: 

```
MODEL_PATH = BASE_PATH / "Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf"
MMPROJ_PATH = BASE_PATH / "Qwen3-VL-8B-Instruct-mmproj-F16.gguf"
``` 
If you have the hardware (24+ GB VRAM) also change (same file):

```n_gpu_layers=0,``` to ```n_gpu_layers=-1,```

For now **must** use the specified llama-cpp-python fork (just below).

### Python

**CREATE A PYTHON ENVIRONMENT** for the project.
- Conda might work (untested).

**DO NOT** pip install requirements.txt:
- llama-cpp-python needs to be built with CUDA
- llama-cpp-python needs to be this fork: https://github.com/JamePeng/llama-cpp-python
  - clone at ```mira/llama-cpp-python``` and then from that directory do: ```CMAKE_ARGS="-DLLAMA_CUBLAS=ON" pip install .```
- torch and torchaudio are CUDA version sensitive
  - Works for me with the specified versions (in requirements.txt) and CUDA13
- Rest should be fine to just pip install

### LLama.cpp

**CMake >= 3.22**

```sudo apt install cmake```

**GCC**

```sudo apt install build-essential```

**Verify** with:

```cmake --version```

```gcc --version```

```nvidia-smi```

Go to ```.../mira``` and open in terminal, then clone and build:
Build at least with CUDA argument.

```https://github.com/ggml-org/llama.cpp```

### HTTP/HTTPS
This is messy, because we need two flask servers.
- HTTPS runs on port 5001
- HTTP run on port 5002

Without https we can not access the phones mic and camera when using the local network.

Without http we can not use a cloudflare tunnel (explodes when its own https clashes with ours) and the browser extensions needs http as well.

After entering the passkeys (at first startup) you can access: 
  - https://Your.IP:5001/login?token=ONE_OF_YOUR_ALLOWED_KEYS or 
  - with Cloudflare tunnel: https://yourdomain.org/login?token=ONE_OF_YOUR_ALLOWED_KEYS or
  - http://Your.IP:5002/login?token=ONE_OF_YOUR_ALLOWED_KEYS

You can create a .desktop file for the QT window but **DO NOT** start Mira's system with it.
- Always use a terminal to start Mira.

### (soft) Dependencies
LibreOffice: For file conversion.
Clementine: For music.
Chromium: For browser integration.