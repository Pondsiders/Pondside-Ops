"""Serve nomic-embed-text v1.5 (F16 GGUF) on Modal as an OpenAI-compatible embeddings endpoint.

Mirrors Ember's `text-embedding-nomic-embed-text-v1.5` llama-swap entry: same
GGUF file, same context size, same pooling strategy. Failover from Ember to
here produces identical embedding vectors.

This is Rosemary's embedding substrate. Alpha's lives in serve_qwen_embedding.py.

Note: nomic requires the task-prefix convention (`search_query:` / `search_document:`
prepended to inputs). That's a client-side concern handled in Rosemary-App and
Alpha-App — the serving Function is just a passthrough.

The model is tiny (262 MB at F16). Using F16 matches Ember (which uses F16
for the same reason — quality is essentially free at this size, the MSE
penalty for going to Q5_K_M is 6 orders of magnitude worse, per memory
#17128's quantization heuristic for tiny models).

Usage:
  uv run modal deploy serve_nomic_embedding.py    # production — stable URL
  uv run modal serve serve_nomic_embedding.py     # dev — ephemeral URL, streams logs
"""

from __future__ import annotations

import subprocess

import modal

app = modal.App("pondside-nomic-embedding")

models_volume = modal.Volume.from_name(
    "pondside-fallback-models",
    create_if_missing=False,
)

LLAMA_CPP_IMAGE = "ghcr.io/ggml-org/llama.cpp:server-cuda"
MODEL_PATH = "/models/nomic-embed-text-v1.5.f16.gguf"
PORT = 8000

serve_image = (
    modal.Image.from_registry(LLAMA_CPP_IMAGE, add_python="3.12")
    .entrypoint([])
)


@app.function(
    image=serve_image,
    gpu="L4",  # massive overkill for a 262 MB model, but keeps infra uniform
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

    # nomic-embed-text uses mean pooling (average across all tokens). This
    # matches Ember's llama-swap config exactly.
    cmd = [
        "/app/llama-server",
        "--model", MODEL_PATH,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "-ngl", "99",              # all layers on GPU
        "--embedding",             # enable /v1/embeddings endpoint
        "--pooling", "mean",       # nomic's required pooling strategy
        "--ctx-size", "2048",      # matches Ember (model's native max is 8192)
        # Served model name in /v1/models — matches Ember's entry
        "--alias", "text-embedding-nomic-embed-text-v1.5",
    ]
    print(f"[serve] launching: {' '.join(cmd)}")
    subprocess.Popen(cmd)
