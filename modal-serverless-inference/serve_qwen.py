"""Serve Qwen 3.5 4B (Unsloth Q4_K_XL GGUF) on Modal as an OpenAI-compatible endpoint.

Mirrors Ember's `unsloth/qwen3.5-4b` llama-swap entry: same GGUF file, same
context size, same `--reasoning off`, same sampling defaults. Failover from
Ember to here should be numerically indistinguishable.

Based on the pattern in /Pondside/Workshop/Projects/Ladybug/src/ladybug/serve.py.

Usage:
  uv run modal deploy serve_qwen.py      # production — stable URL
  uv run modal serve serve_qwen.py       # dev — ephemeral URL, streams logs
"""

from __future__ import annotations

import subprocess

import modal

app = modal.App("pondside-qwen")

models_volume = modal.Volume.from_name(
    "pondside-fallback-models",
    create_if_missing=False,  # populate_volume.py creates it; this just consumes
)

LLAMA_CPP_IMAGE = "ghcr.io/ggml-org/llama.cpp:server-cuda"
MODEL_PATH = "/models/Qwen3.5-4B-UD-Q4_K_XL.gguf"
PORT = 8000

# The llama.cpp image sets ENTRYPOINT=["/app/llama-server"]. Clear it so
# Modal can inject its own Python runner; we launch llama-server as a
# subprocess from inside the serve() function.
serve_image = (
    modal.Image.from_registry(LLAMA_CPP_IMAGE, add_python="3.12")
    .entrypoint([])
)


@app.function(
    image=serve_image,
    gpu="L4",  # 24 GB VRAM — massive headroom for a 4B Q4_K_XL model
    volumes={"/models": models_volume},
    timeout=60 * 60,  # 1 hour max per container lifetime
    scaledown_window=60 * 5,  # idle 5 min → scale to zero
    max_containers=1,  # fallback traffic; one instance is plenty
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

    # Qwen 3.5 4B sampling defaults from Unsloth's recommended settings,
    # matching Ember's llama-swap config exactly. Per-request client values
    # override these.
    cmd = [
        "/app/llama-server",
        "--model", MODEL_PATH,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "-ngl", "99",                # all layers on GPU
        "--ctx-size", "16384",
        "--jinja",                   # use the chat template embedded in the GGUF
        "--reasoning", "off",        # match Ember's llama-swap entry exactly
        # Sampling defaults (Qwen/Unsloth-recommended for Qwen 3.5 4B Instruct)
        "--temp", "0.7",
        "--top-p", "0.8",
        "--top-k", "20",
        "--min-p", "0.0",
        "--presence-penalty", "1.5",
        # Served model name in /v1/models responses — matches Ember's entry
        "--alias", "unsloth/qwen3.5-4b",
    ]
    print(f"[serve] launching: {' '.join(cmd)}")
    subprocess.Popen(cmd)
