# modal-serverless-inference

Serverless OpenAI-compatible inference on Modal. Our fallback inference layer
— when Ember is down for maintenance (or anything else), Harbormaster
dispatches here instead.

## What's served

Same models we run on Ember, same quantizations:

- **`unsloth/qwen3.5-4b`** — Qwen 3.5 4B, Unsloth Dynamic Q4_K_XL GGUF
- **`gemma-3-12b-it`** — Gemma 3 12B Instruct, Unsloth Dynamic Q4_K_XL GGUF

Identical numerics to Ember on failover, because literally the same GGUF
files (on a Modal Volume rather than Ember's `/mnt/models/`).

## Shape

- **Two `@app.function`s**, one per model, each in its own file
  (`serve_qwen.py`, `serve_gemma.py`). Each deploys independently, each
  scales independently, each gets its own public HTTPS URL.
- **One shared Modal Volume** (`pondside-fallback-models`) holds both GGUFs.
  Populated by `populate_volume.py`, which runs inside Modal to pull from
  HuggingFace at Modal's network speed (our 40 Mbps up never gets touched).
- **llama.cpp as the engine** via `ghcr.io/ggml-org/llama.cpp:server-cuda`,
  pinned by tag. Same engine as Ember; behavior parity is the point.
- **L4 GPU (24 GB, $0.80/hr)** for both models. Plenty of headroom —
  Gemma 12B Q4_K_XL is ~8-9 GB resident with its KV cache.
- **Scale-to-zero** by default. Cold start ~30-45s (GGUF load from Volume).
  Acceptable for fallback.

## Standing it up from nothing

```bash
# One-time: install deps + log into Modal
uv sync
uv run modal setup

# One-time: populate the Volume with both GGUFs
# (downloads ~13 GB from HF to Modal, NOT to your laptop)
uv run modal run populate_volume.py

# Deploy both serving Functions
uv run modal deploy serve_qwen.py
uv run modal deploy serve_gemma.py

# Modal prints the public URLs; add them to Harbormaster as fallbacks.
```

Adding a new model later: drop a line into `populate_volume.py`, re-run,
then create `serve_<model>.py` based on the existing ones.

## Differences from the VM conventions

This directory does NOT have:

- `cloud-init/` — Modal provides the runtime
- `domain.xml` — no libvirt
- `motd` — no first-login for humans; `modal deploy` is the entire deploy
- Abe handoff — Modal is a managed platform, nobody builds the box

This directory DOES have, same as VM directories:

- `BUILD_LOG.md` — append-only deploy-and-decision diary
- Pinned versions — `modal` package, llama.cpp image tag, `huggingface_hub`
- Config in git, secrets NOT in git — any per-deploy secrets go via
  `modal secret create`, referenced by name from the Function decorator

## Secrets

No secrets in this repo. If any of our serving Functions ever needs a token
(e.g. gated HF repos), set it via `modal secret create <name> FOO=bar` once,
then reference by name on the Function: `secrets=[modal.Secret.from_name("<name>")]`.

## Links

- Modal docs: https://modal.com/docs
- llama.cpp server image: https://github.com/ggml-org/llama.cpp/pkgs/container/llama.cpp
- Unsloth Qwen 3.5 GGUFs: https://huggingface.co/unsloth/Qwen3.5-4B-GGUF
- Unsloth Gemma 3 GGUFs: https://huggingface.co/unsloth/gemma-3-12b-it-GGUF
- Reference implementation (our own): `/Pondside/Workshop/Projects/Ladybug/src/ladybug/serve.py`
