"""Serve Qwen 3 Embedding 4B (Q4_K_M GGUF) on Modal as an OpenAI-compatible embeddings endpoint.

Mirrors Ember's `text-embedding-qwen3-embedding-4b` llama-swap entry: same
GGUF file, same context size, same pooling strategy. Failover from Ember to
here produces identical embedding vectors — critical for Cortex consistency,
since mixing quantizations for the SAME embedding model across hosts drifts
cosine similarities in ways you can't easily see.

This is Alpha's embedding substrate. Rosemary's lives in serve_nomic_embedding.py.

Usage:
  uv run modal deploy serve_qwen_embedding.py     # production — stable URL
  uv run modal serve serve_qwen_embedding.py      # dev — ephemeral URL, streams logs
"""

from __future__ import annotations

import subprocess

import modal

app = modal.App("pondside-qwen-embedding")

models_volume = modal.Volume.from_name(
    "pondside-fallback-models",
    create_if_missing=False,
)

LLAMA_CPP_IMAGE = "ghcr.io/ggml-org/llama.cpp:server-cuda"
MODEL_PATH = "/models/Qwen3-Embedding-4B-Q4_K_M.gguf"
PORT = 8000

serve_image = (
    modal.Image.from_registry(LLAMA_CPP_IMAGE, add_python="3.12")
    .entrypoint([])
)


@app.function(
    image=serve_image,
    gpu="L4",  # 24 GB VRAM — massive headroom for a 2.5 GB embedding model
    volumes={"/models": models_volume},
    timeout=60 * 60,
    scaledown_window=60 * 5,  # idle 5 min → scale to zero
    max_containers=1,
)
@modal.concurrent(max_inputs=10)
@modal.web_server(port=PORT, startup_timeout=180)
def serve() -> None:
    """Launch llama-server in embedding mode; Modal proxies port PORT."""
    import os

    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(
            f"Missing GGUF on Volume: {MODEL_PATH}. "
            "Run populate_volume.py first."
        )

    # Qwen 3 Embedding 4B uses last-token pooling (the last token of each
    # input sequence is taken as the embedding vector). This matches Ember's
    # llama-swap config exactly.
    cmd = [
        "/app/llama-server",
        "--model", MODEL_PATH,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "-ngl", "99",              # all layers on GPU
        "--embedding",             # enable /v1/embeddings endpoint
        "--pooling", "last",       # Qwen 3 Embedding's required pooling strategy
        "--ctx-size", "2048",      # matches Ember
        # Served model name in /v1/models — matches Ember's entry
        "--alias", "text-embedding-qwen3-embedding-4b",
    ]
    print(f"[serve] launching: {' '.join(cmd)}")
    subprocess.Popen(cmd)
