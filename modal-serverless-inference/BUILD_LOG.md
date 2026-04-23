# modal-serverless-inference Build Log

Append-only deploy-and-decision diary for the Modal serverless fallback layer.

## Spec

- **Role**: OpenAI-compatible inference fallback for Alpha and Rosemary when
  Ember is down. Harbormaster dispatches here via LiteLLM fallback priority
  behind Ember's `/v1` endpoint.
- **Engine**: llama.cpp via `ghcr.io/ggml-org/llama.cpp:server-cuda` image.
  Same engine as Ember; behavior parity is the point.
- **Models**: same Unsloth Q4_K_XL GGUFs as Ember — identical numerics on
  failover.
  - `unsloth/qwen3.5-4b` → `Qwen3.5-4B-UD-Q4_K_XL.gguf` (~3 GB)
  - `gemma-3-12b-it` → `gemma-3-12b-it-UD-Q4_K_XL.gguf` (~7.5 GB)
- **GPU**: L4 (24 GB, $0.80/hr) for both models. Ample headroom.
- **Weights**: shared Modal Volume `pondside-fallback-models` (~11 GB total).
- **Scale-to-zero**: `scaledown_window=300` (5 min idle → shutdown).
- **Cold start**: ~30-45s first-request cost after scaledown. Acceptable for
  fallback where Ember is the warm primary.

## 2026-04-23 — Directory scaffolded

Initial files:

- `README.md` — what this is, how to stand it up
- `pyproject.toml` — `modal>=0.67`, `huggingface-hub[hf-transfer]>=0.26`
- `populate_volume.py` — HF→Volume downloader, runs in Modal's cloud
  (so residential 40 Mbps up is never touched). Idempotent.
- `serve_qwen.py` — Qwen 3.5 4B serving Function
- `serve_gemma.py` — Gemma 3 12B serving Function

Adapted from `/Pondside/Workshop/Projects/Ladybug/src/ladybug/serve.py` —
Ladybug was the proof-of-concept (April 16) for llama-server-on-Modal,
originally serving a LoRA'd Qwen 3.5 4B. This is the production fallback
version: no LoRA, two models, matches Ember's llama-swap configs exactly.

### Key choices

- **GGUF quantization over vLLM FP16.** Smaller models load faster (7.5 GB
  vs 24 GB), run on cheaper hardware (L4 vs L40S/A100), and — critically —
  preserve numerical behavior with Ember on failover. vLLM's sustained-
  throughput wins (PagedAttention, continuous batching) don't apply to a
  bursty fallback layer. See memory #16946 for the earlier version of this
  decision for Ladybug.
- **Two Functions, not one with llama-swap.** llama-swap's value prop is
  "one GPU, many models, evict under pressure" — orthogonal to serverless
  where each Function gets dedicated GPU(s) from Modal's autoscaler. Two
  Functions, two endpoints, Harbormaster routes by model name.
- **L4 for both.** Qwen 4B is trivial for any GPU; Gemma 12B Q4_K_XL is
  ~9 GB resident and fits comfortably in 24 GB. If fallback gen speed
  feels too slow in practice, Gemma upgrades to L40S (~3x compute,
  2.4x cost) by changing one string.
- **`scaledown_window=300`.** Default of 60s is too aggressive for
  conversational fallback — a user mid-thread on Ember-down would pay cold
  start again after a 60s gap. 5 min window costs maybe $0.25/month if
  fallback sees occasional traffic.

### Pending

- `uv sync` + `uv run modal setup` — one-time, requires Jeffery's browser
- `modal volume create pondside-fallback-models` — implicit, happens on
  first `modal run populate_volume.py`
- `uv run modal run populate_volume.py` — downloads ~11 GB from HF to
  Volume in Modal's cloud (expect ~60-90s)
- `uv run modal deploy serve_qwen.py` — get public URL
- `uv run modal deploy serve_gemma.py` — get public URL
- Add both URLs to Harbormaster's config as fallbacks behind Ember's entries
- Failover smoke test: stop llama-swap on Ember, send a request, verify
  Harbormaster routes to Modal

## Next

- [ ] First `modal run populate_volume.py` execution — capture wall time
      and observed download rate
- [ ] First deploys — record public URLs here for future reference
- [ ] Harbormaster fallback config snippet (once URLs are known)
- [ ] Failover test result
- [ ] First month's Modal usage report — did the free tier cover it?
