### Quickstart

1. Confirm Nvidia Driver 580.105.08 (or higher): 
    ```
    nvidia-smi
    ```

2. Clone:
    ```
    git clone https://github.com/SailaNamai/mira.git
    cd mira
    ```

3. Downloads (pulls in ~25 GB):
    ```
    chmod +x download.sh
    ./download.sh
    ```

4. Then run the Dockerfile:
    ```
    docker compose build --no-cache mira
    ```

5. Create your passkeys:
    ```    
    Open .../mira/services/passkeys_template.py with a text editor and follow the instructions.
    ```

6. back at ```.../mira``` start with:
    ```
    docker compose up mira
    ```

7. When you see ```[Docker] GUI disabled, Flask servers only``` access with:
    ```
    # Phone/client from local network:
    https://Your.IP:5001/login?token=ONE_OF_YOUR_ALLOWED_KEYS 
    # or Phone through web: 
    with Cloudflare tunnel: https://yourdomain.org/login?token=ONE_OF_YOUR_ALLOWED_KEYS 
    # or from the host with browser extension
    http://Your.IP:5002/login?token=ONE_OF_YOUR_ALLOWED_KEYS
    ```

Don't have Docker? [Read the docker-engine section](#install-docker-engine)

**Hardware**:
<table>
  <tr>
    <td>
      <table>
        <thead>
          <tr>
            <th style="text-align:center">Minimum</th>
            <th style="text-align:center">Recommended</th>
            <th style="text-align:left">Comment</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="text-align:center">16GB VRAM</td>
            <td style="text-align:center">More</td>
            <td>16GB will leave about 4GB<br>for context window.</td>
          </tr>
          <tr>
            <td style="text-align:center">50 TFLOPS</td>
            <td style="text-align:center">Faster</td>
            <td>Speed is king in our use case.</td>
          </tr>
          <tr>
            <td style="text-align:center">32GB RAM</td>
            <td style="text-align:center">More</td>
            <td>Qwen3-VL@8B_Q6K(~9GB);<br>Vosk (~4GB); + context.</td>
          </tr>
          <tr>
            <td style="text-align:center">8c/16t CPU</td>
            <td style="text-align:center">Faster+More</td>
            <td>VL is slow on CPU.</td>
          </tr>
        </tbody>
      </table>
    </td>
    <td style="vertical-align:top; padding-left:20px;">
      <img src="static/readme/hardware_settings.jpg" alt="hardware settings" width="250">
    </td>
  </tr>
</table>

**DO NOT** overload your VRAM on initial startup. You'll crash with 'oom' and can either delete the DB (generates new on startup) or edit the settings manually.

### (soft) Dependencies
**Cloudflare**: 

You need to buy (any) domain, which costs only a couple of currency units per year.
The tunnel service itself is offered for free by Cloudflare. Point the tunnel towards **http** flask at port **5002**.
If you make the tunnel a systemd service, make sure it retries for the app being alive, otherwise it fails silently, and you have to restart the tunnel manually after running the app.

**LibreOffice**: 

For file conversion.

**Clementine**:

For music. Drop playlist into ```...mira/playlists```

**Chromium and the extension**:

Install Chromium if you don't have it.
Install extension from ```...mira/services/browser/chromium_extension``` with Chromium's ```dev mode``` enabled.

**Nutrition**: 

Data for foundation foods is included in the repo but branded data is too big for GitHub. 
If you want (US-centric) branded search results place 
```
https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_branded_food_json_2025-04-24.zip 
```
at ```.../mira/static/nutrition``` and extract. Then do python ```clean_data_Branded.py```

### Install Docker-Engine

Prepare Ubuntu for Docker:
```
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

Verification:
```docker --version```

Then install Docker:
```
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Add user privilege:
```
sudo usermod -aG docker $USER
newgrp docker
```

Enable Docker:
```
sudo systemctl enable --now docker
docker version
```

Get the Nvidia Toolkit for Docker access to Nvidia GPU
```
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
```

Configures Docker to recognize and use NVIDIA GPU:
```
sudo nvidia-ctk runtime configure --runtime=docker
```

Then restart Docker:
```
sudo systemctl restart docker
```

Verification:
```
docker run --rm --gpus all nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi
```

<details>
<summary>Click to expand example output</summary>

```bash
Unable to find image 'nvidia/cuda:13.0.0-base-ubuntu24.04' locally
13.0.0-base-ubuntu24.04: Pulling from nvidia/cuda
13e8f87efde8: Pull complete 
ddc61996788f: Pull complete 
0acb0bb33f99: Pull complete 
32f112e3802c: Pull complete 
9c9b39ad83d5: Pull complete 
Digest: -
Status: Downloaded newer image for nvidia/cuda:13.0.0-base-ubuntu24.04
Sun Dec  7 09:07:21 2025       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.105.08             Driver Version: 580.105.08     CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 4080 ...    On  |   00000000:01:00.0  On |                  N/A |
| 31%   35C    P2             46W /  320W |   14353MiB /  16376MiB |      5%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+
```
</details>

---

---
Manual install (incomplete, not recommended):

### Look at the dockerfile, it tells you exactly what you need to install without Docker.

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
Record a wake word ("please") and drop it into ```...mira/static/sounds/please.wav```

Place XTTS-v2 in ```.../mira/static/xtts-v2.```

```https://huggingface.co/coqui/XTTS-v2```

Can change voice by placing a 24k .wav as ```.../mira/static/xtts-v2/samples/custom_24k.wav```

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

You can create a .desktop file for the QT window but **DO NOT** start Mira's system with it.
- Always use a terminal to start Mira.

 