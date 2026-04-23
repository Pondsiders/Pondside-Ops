"""Populate the `pondside-fallback-models` Modal Volume with GGUFs from HuggingFace.

Runs INSIDE Modal's cloud — downloads happen on Modal's network (fast),
not on residential upload (slow). Your laptop sends a few KB of Python to
Modal and gets a "done" message back. No GGUF bytes cross your home link.

Idempotent: files already present on the Volume are skipped.

Usage:
  uv run modal run populate_volume.py                    # pull all models
  uv run modal run populate_volume.py::populate --force  # re-download everything
"""

from __future__ import annotations

import modal

app = modal.App("pondside-populate")

models_volume = modal.Volume.from_name(
    "pondside-fallback-models",
    create_if_missing=True,
)

# Keep this list in one place. Each serve_*.py references the filename directly.
MODELS = [
    # Qwen 3.5 4B Instruct — Unsloth Dynamic Q4_K_XL GGUF
    # https://huggingface.co/unsloth/Qwen3.5-4B-GGUF
    (
        "unsloth/Qwen3.5-4B-GGUF",
        "Qwen3.5-4B-UD-Q4_K_XL.gguf",
    ),
    # Gemma 3 12B Instruct — Unsloth Dynamic Q4_K_XL GGUF
    # https://huggingface.co/unsloth/gemma-3-12b-it-GGUF
    (
        "unsloth/gemma-3-12b-it-GGUF",
        "gemma-3-12b-it-UD-Q4_K_XL.gguf",
    ),
    # Qwen 3 Embedding 4B — Q4_K_M from Qwen team (match Ember exactly;
    # mixing quants for the SAME embedding model across hosts drifts cosine
    # similarities in ways you can't easily unsee)
    # https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF
    (
        "Qwen/Qwen3-Embedding-4B-GGUF",
        "Qwen3-Embedding-4B-Q4_K_M.gguf",
    ),
    # nomic-embed-text v1.5 — F16 from Nomic team (Rosemary's embedding
    # space; F16 for quality since the model is tiny anyway — 262 MB)
    # https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF
    (
        "nomic-ai/nomic-embed-text-v1.5-GGUF",
        "nomic-embed-text-v1.5.f16.gguf",
    ),
]

# Small CPU-only image. hf-transfer for the fast Rust downloader.
populate_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("huggingface-hub[hf-transfer]>=0.26")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)


@app.function(
    image=populate_image,
    volumes={"/models": models_volume},
    timeout=60 * 30,  # 30 minutes — enough for several big GGUFs even on a bad day
)
def populate(force: bool = False) -> None:
    """Download each (repo, filename) in MODELS into /models on the Volume."""
    import os
    import time

    from huggingface_hub import hf_hub_download

    for repo_id, filename in MODELS:
        dest = f"/models/{filename}"
        if os.path.exists(dest) and not force:
            size_gb = os.path.getsize(dest) / (1024**3)
            print(f"[skip] {filename} already present ({size_gb:.2f} GB)")
            continue

        print(f"[pull] {repo_id} :: {filename}")
        t0 = time.monotonic()
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir="/models",
        )
        elapsed = time.monotonic() - t0
        size_gb = os.path.getsize(dest) / (1024**3)
        rate = size_gb * 1024 / elapsed  # MB/s
        print(f"[done] {filename}  {size_gb:.2f} GB in {elapsed:.1f}s  ({rate:.0f} MB/s)")

    # Make the downloads visible to other Functions that mount this Volume.
    models_volume.commit()
    print("[done] Volume committed.")


@app.local_entrypoint()
def main(force: bool = False) -> None:
    """Kick off populate() in the cloud."""
    populate.remote(force=force)
