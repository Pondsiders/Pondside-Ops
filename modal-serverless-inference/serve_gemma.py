"""Serve Gemma 3 12B Instruct (Unsloth Q4_K_XL GGUF) on Modal as an OpenAI-compatible endpoint.

Mirrors Ember's `gemma-3-12b-it` llama-swap entry: same GGUF file, same
context size, same q8_0 KV cache, same sampling defaults. Failover from
Ember to here should be numerically indistinguishable.

Note: Gemma 3 is NOT a thinking model — no `--reasoning off` flag needed.
The `--jinja` flag is load-bearing; llama-server auto-prepends `<bos>` so
do NOT wrap prompts manually (matters only if reaching for /completion; the
/v1/chat/completions path handles it correctly).

Based on the pattern in /Pondside/Workshop/Projects/Ladybug/src/ladybug/serve.py.

Usage:
  uv run modal deploy serve_gemma.py     # production — stable URL
  uv run modal serve serve_gemma.py      # dev — ephemeral URL, streams logs
"""

from __future__ import annotations

import subprocess

import modal

app = modal.App("pondside-gemma")

models_volume = modal.Volume.from_name(
    "pondside-fallback-models",
    create_if_missing=False,  # populate_volume.py creates it; this just consumes
)

LLAMA_CPP_IMAGE = "ghcr.io/ggml-org/llama.cpp:server-cuda"
MODEL_PATH = "/models/gemma-3-12b-it-UD-Q4_K_XL.gguf"
PORT = 8000

serve_image = (
    modal.Image.from_registry(LLAMA_CPP_IMAGE, add_python="3.12")
    .entrypoint([])
)


@app.function(
    image=serve_image,
    # L4 24 GB: 7.5 GB Gemma weights + ~1 GB q8_0 KV cache at ctx=4096
    # leaves plenty of headroom. Upgrade to L40S ($1.95/hr, ~3x compute)
    # if fallback gen speed is too slow in practice.
    gpu="L4",
    volumes={"/models": models_volume},
    timeout=60 * 60,
    scaledown_window=60 * 5,
    max_containers=1,
)
@modal.concurrent(max_inputs=10)
@modal.web_server(port=PORT, startup_timeout=180)
def serve() -> None:
    """Launch llama-server; Modal proxies port PORT as the public endpoint."""
    import os

    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(
            f"Missing GGUF on Volume: {MODEL_PATH}. "
            "Run populate_volume.py first."
        )

    # Gemma 3 sampling defaults from Google's published recommendations,
    # matching Ember's llama-swap config exactly. Per-request client values
    # override these. repeat_penalty=1.0 is load-bearing (non-1.0 degrades
    # Gemma 3 quality per Gemma team guidance).
    cmd = [
        "/app/llama-server",
        "--model", MODEL_PATH,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "-ngl", "99",                  # all layers on GPU
        "--ctx-size", "4096",          # matches Ember; SWA KV cache is beefy
        "--jinja",                     # use the chat template embedded in the GGUF
        "--cache-type-k", "q8_0",      # shrink KV cache (halves its footprint)
        "--cache-type-v", "q8_0",
        # Sampling defaults (Gemma team's published recommendations)
        "--temp", "1.0",
        "--top-p", "0.95",
        "--top-k", "64",
        "--min-p", "0.01",
        "--repeat-penalty", "1.0",     # disabled — Gemma 3 degrades with repetition penalty
        # Served model name in /v1/models responses — matches Ember's entry
        "--alias", "gemma-3-12b-it",
    ]
    print(f"[serve] launching: {' '.join(cmd)}")
    subprocess.Popen(cmd)
