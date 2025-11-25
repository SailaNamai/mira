# services.llm_config.py
"""
apt-get update
apt-get install pciutils build-essential cmake curl libcurl4-openssl-dev -y
git clone https://github.com/ggml-org/llama.cpp
cmake llama.cpp -B llama.cpp/build \
    -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON -DLLAMA_CURL=ON
cmake --build llama.cpp/build --config Release -j --clean-first
cp llama.cpp/build/bin/llama-* llama.cpp

./llama.cpp/build/bin/llama-mtmd-cli \
  --model /home/sailanamai/mira/Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf \
  --mmproj /home/sailanamai/mira/mmproj-F16.gguf \
  --n-gpu-layers 99 \
  --jinja \
  --top-p 0.8 \
  --top-k 20 \
  --temp 0.7 \
  --min-p 0.0 \
  --flash-attn on \
  --presence-penalty 1.5 \
  --ctx-size 8192
"""
from services.globals import BASE_PATH


class Config:
    """
    ##########
    ###
    ###     MIRA Config
    ###
    ##########
    """
    #MODEL_PATH = BASE_PATH / "krix-12b-model_stock-q6_k.gguf"
    MODEL_PATH_VL = BASE_PATH / "Qwen3-VL-8B-Instruct-UD-Q6_K_XL.gguf"
    MODEL_PATH = BASE_PATH / "Qwen3-8B-UD-Q6_K_XL.gguf"
    #MODEL_PATH_INTENT = BASE_PATH / "Qwen3-1.7B-Q8_0.gguf"

    # N_CTX: context window size in tokens.
    N_CTX = 8192

    # N_THREADS: number of CPU threads to use for offloaded computations.
    # llama.cpp can spill some transformer layers to the CPU when VRAM is tight.
    N_THREADS: int = 16

    # N_GPU_LAYERS: count of transformer layers loaded onto the GPU.
    #  • Increasing this uses more VRAM but accelerates inference.
    #  • Decreasing it frees GPU memory but shifts work to the CPU, slowing down.
    N_GPU_LAYERS: int = 56

    """
    ##########
    ###
    ###     Unused
    ###
    ##########
    """
    TEMPERATURE: float = 0.68


    # Nucleus sampling cutoff (top_p): trims the “candidate list” to only the most probable words.
    #   • If top_p=0.9, it sums probabilities from the top until that running total reaches 90%, then
    #   • A lower top_p (e.g., 0.5) makes the model extremely conservative (only the very top words),
    TOP_P: float = 0.85

    # Frequency penalty: discourages the model from repeating the same words over and over.
    #   • Scale runs from –2.0 to +2.0.
    #   • Values > 0.0 gently penalize tokens that have already appeared
    #   • Values < 0.0 actually encourage repetition
    FREQUENCY_PENALTY: float = 0.00

    # Repeat penalty: reduces the chance of the model reusing the exact same token sequences.
    #   • Works multiplicatively on token probabilities—tokens that have already appeared get
    #     their likelihood scaled down by this factor.
    #   • A value of 1.0 means “no penalty” (neutral).
    #   • Values > 1.0 discourage repetition more strongly.
    #   • Values < 1.0 *reward* repetition.
    REPEAT_PENALTY: float = 1.00

    # Presence penalty: nudges the model to introduce new topics or entities instead of sticking to old ones.
    #   • Also ranges from –2.0 to +2.0.
    #   • Positive values push the model to bring in fresh concepts
    #   • Negative values make the model more comfortable staying on the same topic
    PRESENCE_PENALTY: float = 0.00

    # Typical-p sampling: filters tokens based on how "typical" their probability is compared to the distribution.
    #   • Instead of just looking at the top tokens (top_k) or cumulative probability (top_p),
    #     it measures how close each token’s probability is to the *expected average surprise* (entropy).
    #   • The model then keeps only those tokens whose probability is within the chosen threshold (typical_p).
    #   • A value of 1.0 means "off" (no filtering).
    #   • Values between 0.9–0.99 are common: they prune out unusually high- or low-probability tokens,
    #     which often reduces bizarre or incoherent outputs while keeping the text lively.
    #   • Lower values (e.g., 0.8) make the model very conservative and predictable,
    #     while values close to 1.0 allow more diversity but risk occasional oddities.
    TYPICAL_P: float = 0.97

    # Top-k sampling: limits the candidate pool to only the k most likely tokens.
    #   • The model ranks all possible next tokens by probability, then keeps only the top k.
    #   • For example, with k=50, only the 50 most probable tokens are considered; everything else is discarded.
    #   • This creates a "hard cutoff" — unlike top_p (nucleus sampling), which uses probability mass,
    #     top_k uses a fixed number of tokens.
    #   • Lower values (e.g., 10–20) make the model very deterministic and focused, but risk bland or repetitive text.
    #   • Higher values (e.g., 80–100) allow more variety and creativity, but can also introduce noise or odd word choices.
    #   • Setting k=-1 disables top-k entirely, leaving other sampling methods (like top_p or typical_p) in control.
    TOP_K: int = 50

    STREAMING: bool = True

    # Don't think we need it.
    # stop sequences: generation will end as soon as any of these substrings appears
    # pass to llama-cpp-python as `stop=Config.STOP_SEQUENCES`
    # STOP_SEQUENCES: List[str] = ["<|END_TEXT|>"]

    # reproducible generations
    # supply to llama-cpp-python via `seed=…` or CLI `--seed N`
    SEED: int = 42

    # log level (CLI only): e.g. “info”, “warn”, “error” to silence perf prints
    LOG_LEVEL: str = "warn"

    # batch size (Python binding only): number of prompt tokens processed per forward-pass
    # higher values use more CPU/RAM but can be faster
    BATCH_SIZE: int = 512