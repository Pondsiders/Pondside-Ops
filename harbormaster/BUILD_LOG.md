# Harbormaster Build Log

Append-only deploy-and-decision diary for the LiteLLM proxy container stack.

## Spec

- **Role**: OpenAI-compatible API gateway at `https://api.tail8bd569.ts.net`.
  Routes local inference (Ember primary, Modal fallback) and passes Claude
  Max OAuth traffic to Anthropic unchanged.
- **Host**: Primer bare-metal Docker today; portable to any host on the
  tailnet by moving the compose stack + volumes.
- **Identity**: `api.tail8bd569.ts.net` — a dedicated tailnet node carried by
  the `tailscale` sidecar container in this compose stack.
- **Containers**: tailscale (sidecar), postgres (internal), litellm (main).

## 2026-04-18 — Original Harbormaster (at /Pondside/Workshop/Projects/Harbormaster)

Built as part of the LiteLLM-proxy-for-Claude-Max work (memory #17016).
Serves Claude Max traffic via transparent OAuth pass-through. Earlier
versions also routed Qwen 3.5 via Ollama on Primer and Gemma 4 A4B via
LM Studio on Jeffery's MacBook.

Those local-inference routes have gone stale (memories #17118, #17122):
Ollama retired, LM Studio retired in favor of Ember + llama-swap.

## 2026-04-23 — Pondside-Ops/harbormaster scaffold

Declared state of the Harbormaster stack committed to Pondside-Ops. Changes
vs. the running stack at /Pondside/Workshop/Projects/Harbormaster/:

### Option D identity persistence

Added `TS_AUTH_ONCE: "true"` to the Tailscale sidecar. Combined with the
existing persistent `tailscale-state` volume, this means:

- `TS_AUTHKEY` is used only on first boot (or disaster recovery).
- Subsequent restarts use cached machine/node keys.
- After first boot, manually set "Disable key expiry" on the `api` machine
  in the Tailscale admin panel → machine identity lives as long as the
  volume does.

This was a real finding this afternoon (memory #17139). Earlier in the day I
was bracing for recurring 90-day auth-key rotation; Jeffery worked out that
TS_AUTHKEY is dormant after first boot if state persists, which dissolved the
concern entirely.

### Routes retired

- `qwen-3.5-4b` via `ollama_chat/` at `primer:11434` — REMOVED. Ollama is
  retired; Ember runs llama.cpp via llama-swap.
- `gemma-4-26b` via `lm_studio/` at `jefferys-macbook-pro:1234` — REMOVED.
  Ember serves Gemma 3 12B (not 4 26B A4B; different model family).

### Routes added

Four Ember-primary + Modal-fallback pairs, all served through the OpenAI-
compatible `/v1` interface via llama-server:

| model_name | Primary (Ember) | Fallback (Modal) |
|---|---|---|
| `unsloth/qwen3.5-4b` | ✓ | pondside-qwen-serve.modal.run |
| `gemma-3-12b-it` | ✓ | pondside-gemma-serve.modal.run |
| `text-embedding-qwen3-embedding-4b` | ✓ | pondside-qwen-embedding-serve.modal.run |
| `text-embedding-nomic-embed-text-v1.5` | ✓ | pondside-nomic-embedding-serve.modal.run |

Fallback mapping declared in `litellm_settings.fallbacks`. Modal entries
carry `num_retries: 3, timeout: 60` to absorb the cold-start "Loading model"
503 window (memory #17137; typically 5-15s for llama-server to finish
loading weights from a Modal Volume after port-open).

### Claude pass-through kept unchanged

`claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` still
route to `anthropic/*` with `forward_client_headers_to_llm_api: true`.
This is the load-bearing path for Alpha-App and Rosemary-App — the OAuth
flow from Claude Code must not be touched.

### Callbacks preserved

`callbacks.py` (200 lines, asyncpg-backed) copied wholesale from the
running stack. Captures Anthropic rate-limit response headers into Neon's
`anthropic_usage` table on every Claude response. Dashboards in Grafana
Cloud depend on this. Not changing it.

## Next

- [ ] Review this scaffold with fresh eyes (tomorrow or later this week)
- [ ] Cutover: move compose stack location from Workshop/Projects to here,
      preserving `tailscale-state/` and `postgres-data/` volumes
- [ ] After first boot of the moved stack, disable key expiry on the `api`
      machine in Tailscale admin
- [ ] Failover test: stop Ember's llama-swap, verify Harbormaster routes
      successfully to Modal for all four models, measure client-visible
      latency on the first cold-start-to-200 path
- [ ] Once failover verified, retire `/Pondside/Workshop/Projects/Harbormaster/`
