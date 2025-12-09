# ---------- Builder stage ----------
FROM nvidia/cuda:13.0.0-devel-ubuntu24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Basic build packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-venv \
    libportaudio2 libasound2-dev pulseaudio-utils \
    mkcert libnss3-tools \
    git \
    libgl1 \
    libegl1 \
    libglu1-mesa \
    libxkbcommon-x11-0 \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

# System packages needed for build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*

# Make sure CUDA stubs are visible to linker
RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/lib/x86_64-linux-gnu/libcuda.so || true && \
    ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/lib/x86_64-linux-gnu/libcuda.so.1 || true

WORKDIR /app

# Build llama.cpp with CUDA/cuBLAS, skip examples/tests, but allow mtmd
RUN git clone https://github.com/ggml-org/llama.cpp /app/llama.cpp && \
    cd /app/llama.cpp && mkdir build && cd build && \
    cmake .. -DGGML_CUDA=ON \
             -DLLAMA_CURL=OFF \
             -DLLAMA_BUILD_EXAMPLES=OFF \
             -DLLAMA_BUILD_TESTS=OFF \
             -DLLAMA_BUILD_TOOLS=OFF \
             -DMTMD_BUILD=ON \
             -DCMAKE_CUDA_ARCHITECTURES=all-major && \
    make -j$(nproc)

# Build llama-cpp-python fork with CUDA and mtmd
RUN CMAKE_ARGS="-DGGML_CUDA=ON \
                -DLLAMA_CURL=OFF \
                -DLLAMA_BUILD_EXAMPLES=OFF \
                -DLLAMA_BUILD_TESTS=OFF \
                -DLLAMA_BUILD_TOOLS=OFF \
                -DMTMD_BUILD=ON \
                -DCMAKE_CUDA_ARCHITECTURES=all-major" \
    pip wheel --no-cache-dir --wheel-dir /app/wheels \
    git+https://github.com/JamePeng/llama-cpp-python.git

# ---------- Runtime stage ----------
FROM nvidia/cuda:13.0.0-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Fix torchcodec issue by ensuring shared Python libraries are available
    LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/local/lib/python-shared:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:$LD_LIBRARY_PATH \
    TORCH_CODEC_FFMPEG_PATH=/usr/bin/ffmpeg

WORKDIR /app
COPY . /app

# Copy compiled libraries
COPY --from=builder /app/llama.cpp/build/bin/libggml*.so* /usr/local/lib/
COPY --from=builder /app/llama.cpp/build/bin/libllama*.so* /usr/local/lib/

# Install runtime system packages - ADD missing Qt/XCB dependencies and Python dev packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3.12-venv \
    # Python development packages for shared libraries (CRITICAL FOR TORCHCODEC)
    python3-dev libpython3-dev \
    # Audio dependencies
    libportaudio2 libasound2-dev pulseaudio-utils libsox-fmt-all \
    # FFmpeg and development libraries
    ffmpeg libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libavfilter-dev \
    libavdevice-dev libswresample-dev \
    # SSL/Security
    mkcert libnss3-tools libssl3 libnss3 libnspr4 \
    # GUI dependencies (PyQt6, pywebview)
    libgl1 libegl1 libglu1-mesa \
    libfontconfig1 libglib2.0-0 \
    libx11-6 libxcb1 libxrender1 libxi6 libxcursor1 libxinerama1 \
    libxkbcommon-x11-0 libxcb-xinerama0 libxcb-cursor0 \
    # XCB LIBRARIES FOR QT 6.5.0+
    libxcb-xfixes0 libxcb-shm0 libxcb-randr0 libxcb-render0 \
    libxcb-image0 libxcb-keysyms1 libxcb-icccm4 libxcb-util1 \
    libxcb-shape0 libxcb-sync1 libxcb-composite0 \
    libxkbfile1 libxkbcommon0 \
    libdbus-1-3 libxss1 libxtst6 libpulse0 \
    # Image processing (Pillow)
    libjpeg-turbo8 zlib1g libtiff6 libwebp7 libopenjp2-7 libimagequant0 \
    # System utilities
    git wget curl \
    # For pywebview GTK backend
    libwebkit2gtk-4.1-0 \
    # Additional Qt platform plugin dependencies
    libxcb-cursor-dev libxcb-xfixes0-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy system Python shared libraries to a dedicated directory in LD_LIBRARY_PATH
RUN mkdir -p /usr/local/lib/python-shared && \
    cp /usr/lib/x86_64-linux-gnu/libpython3.12*.so* /usr/local/lib/python-shared/ && \
    chmod +x /usr/local/lib/python-shared/* && \
    # Verify the libraries were copied correctly
    ls -la /usr/local/lib/python-shared/ && \
    ldconfig

# ==========================================
# Create venv in /opt instead of /app to avoid being overwritten by volume mount
# ==========================================
RUN python3 -m venv /opt/venv

# Fix ONLY python symlinks (NEVER copy system pip as it's externally managed)
RUN cd /opt/venv/bin && \
    rm -f python* && \
    [ -f python3.12 ] || cp /usr/bin/python3.12 python3.12 && \
    ln -sf python3.12 python && \
    ln -sf python3.12 python3 && \
    chmod +x python3.12

# Bootstrap/upgrade pip INSIDE venv using python -m pip (avoids system pip entirely)
RUN /opt/venv/bin/python -m pip install --upgrade pip setuptools wheel

# Install PyTorch CUDA 13.0 into venv
RUN /opt/venv/bin/pip install --no-cache-dir \
    torch==2.9.1+cu130 torchaudio==2.9.1+cu130 \
    --index-url https://download.pytorch.org/whl/cu130

# Install torchcodec
RUN /opt/venv/bin/pip install --no-cache-dir \
    torchcodec==0.9.0 \
    --index-url https://download.pytorch.org/whl/cu130

# Install coqui-tts deps (except torch/torchaudio, already pinned), pin transformers
RUN /opt/venv/bin/pip install --no-cache-dir \
    anyascii coqpit-config coqui-tts-trainer cython einops encodec fsspec \
    gruut inflect librosa matplotlib "monotonic-alignment-search" num2words \
    numba numpy packaging pysbd pyyaml scipy soundfile tqdm "transformers==4.57.1" typing-extensions

# Now install coqui-tts itself (no deps, since we handled them)
RUN /opt/venv/bin/pip install coqui-tts --no-deps

# Install pre-built JamePeng/llama-cpp-python wheel into venv
COPY --from=builder /app/wheels /wheels
RUN /opt/venv/bin/pip install /wheels/llama_cpp_python-*.whl

# Install regular Python packages into venv
RUN /opt/venv/bin/pip install --no-cache-dir \
    ijson pillow cryptography dateparser vosk ddgs \
    trafilatura pdfminer.six requests pywebview \
    "PyQt6==6.10.0" PyQt6-WebEngine "pyqt6-sip==13.10.2" \
    "Flask~=3.1.2" flask-cors flask-socketio

EXPOSE 5001 5002
CMD ["/opt/venv/bin/python", "mira.py"]