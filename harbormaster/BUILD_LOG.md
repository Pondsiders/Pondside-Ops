# Harbormaster Build Log

Append-only deploy-and-decision diary for the LiteLLM proxy container stack.

## Spec

- **Role**: OpenAI-compatible inference gateway at `https://api.tail8bd569.ts.net`.
  Routes local inference (Ember primary, Modal serverless fallback).
- **Host**: Docker Compose stack; portable to any host on the tailnet by
  moving the compose files + volumes.
- **Identity**: `api.tail8bd569.ts.net` — a dedicated tailnet node carried by
  the `tailscale` sidecar in this compose stack. Persistent state in the
  `tailscale-state/` volume; `TS_AUTH_ONCE=true` means the sidecar only
  re-auths when state is missing.

## 2026-04-23 — Scaffold committed

Four Ember-primary + Modal-fallback model pairs, served through the OpenAI-
compatible `/v1` interface:

| model_name | Primary | Fallback |
|---|---|---|
| `unsloth/qwen3.5-4b` | Ember | pondside-qwen-serve.modal.run |
| `gemma-3-12b-it` | Ember | pondside-gemma-serve.modal.run |
| `text-embedding-qwen3-embedding-4b` | Ember | pondside-qwen-embedding-serve.modal.run |
| `text-embedding-nomic-embed-text-v1.5` | Ember | pondside-nomic-embedding-serve.modal.run |

Fallback mapping declared in `litellm_settings.fallbacks`. Modal entries
carry `num_retries: 3, timeout: 60` to absorb the cold-start "Loading model"
503 window (typically 5-15s for llama-server to finish loading weights from
a Modal Volume after port-open).

## Next

- [ ] First deploy — `docker compose up -d`
- [ ] Disable key expiry on the `api` machine in Tailscale admin
- [ ] Failover test: stop Ember's llama-swap, verify Harbormaster routes
      successfully to Modal for all four models, measure client-visible
      latency on the first cold-start-to-200 path
