# harbormaster

LiteLLM proxy with a Tailscale sidecar. Serves `https://api.tail8bd569.ts.net`.
Three jobs:

1. **Transparent OAuth pass-through** for Claude Max — forwards Claude Code's
   `Authorization: Bearer <oauth>` header unchanged to `api.anthropic.com`.
2. **Local inference routing** — chat and embedding models on Ember (primary)
   with Modal serverless fallback (see `../modal-serverless-inference/`).
3. **Usage observability** — captures Anthropic's rate-limit response headers
   and writes a time-series row per request to Neon. Grafana Cloud queries it.

## Relationship to the running stack

This directory is the **declared state** in version control.

The **running stack** currently lives at `/Pondside/Workshop/Projects/Harbormaster/`
on Primer — that's the path `docker compose` actually operates against today.
It's been running since April 18, 2026 (memory #17016) serving Claude Max
traffic. The two have diverged: the running stack has stale Ollama/LM-Studio
routes that need to be retired.

**Cutover plan** (not done yet, requires a deliberate act):

1. Review this directory; commit any final changes.
2. Copy the contents to Primer's target location (could stay where it is, or
   move to `/Pondside/Workshop/Projects/Harbormaster/` replaced in-place, or
   move to a neutral location like `/Pondside/Basement/harbormaster/`).
3. Preserve the existing `tailscale-state/` and `postgres-data/` volume
   directories — do NOT blow them away. The tailscale-state in particular
   holds the machine identity for `api.tail8bd569.ts.net`.
4. `docker compose down` on the running stack.
5. `docker compose up -d` on the new location.
6. Verify: `api.tail8bd569.ts.net` still resolves, Claude Max traffic still
   flows, local inference routes correctly to Ember, fallback fires when
   Ember is stopped.
7. If all good, retire `/Pondside/Workshop/Projects/Harbormaster/`.

Order of operations matters: the volume directories carry live state
(Postgres data, Tailscale machine identity). Moving without preserving them
means re-bootstrapping the sidecar and losing LiteLLM's spend history.

## What's in here

```
compose.yml          Tailscale sidecar + Postgres + LiteLLM
config.yaml          LiteLLM routing: Claude + Ember primary + Modal fallback
Dockerfile           Thin wrapper on litellm:main-latest; adds asyncpg for callbacks
callbacks.py         Custom LiteLLM callback — captures Anthropic rate-limit headers
serve-config.json    Tailscale Serve: HTTPS :443 → localhost:4000
.env.example         Template for .env (gitignored)
```

## Standing it up from nothing (first deploy on a fresh host)

```bash
# 1. Populate secrets
cp .env.example .env
$EDITOR .env   # generate TS_AUTHKEY, LITELLM_MASTER_KEY, POSTGRES_PASSWORD, NEON_DATABASE_URL

# 2. Bring up the stack
docker compose up -d

# 3. Watch the Tailscale sidecar join the tailnet (30-60 seconds)
docker compose logs -f tailscale
# Look for: "Success. Still logged in as tagged-node @api (owner: jefferyharrell)"

# 4. Disable machine key expiry (Option D completion)
#    Browser: https://login.tailscale.com/admin/machines
#    Find the `api` machine → settings → "Disable key expiry"
#    After this, TS_AUTHKEY can expire without breaking anything.

# 5. Verify HTTPS and routing
curl https://api.tail8bd569.ts.net/v1/models \
  -H "x-litellm-api-key: Bearer $LITELLM_MASTER_KEY"
```

## Chat fallback behavior

LiteLLM's fallback kicks in when the primary (Ember) returns 5xx or times out:

1. Client calls `POST /v1/chat/completions` with `model: "unsloth/qwen3.5-4b"`
2. LiteLLM routes to Ember at `https://ember.tail8bd569.ts.net/v1`
3. If Ember is down (connection refused) or llama-swap is stopped:
   - LiteLLM's `num_retries: 2` exhausts against Ember first
   - Then falls back to `unsloth/qwen3.5-4b-modal`
   - Modal cold-starts (~10-15s), may initially return 503 "Loading model"
   - Modal entry's `num_retries: 3` absorbs the cold-start window
   - Client gets a successful response, slightly delayed on first call
4. Subsequent calls go through warm Modal container until `scaledown_window`
   expires (5 min idle), at which point cold-start happens again.

Failover is transparent to the client. Worst-case user-visible latency is
~30-40s on the first call after Ember goes down. Every call after that is
normal (Modal-warm) until Ember comes back up.

## What is NOT in here yet

- **Harbormaster's own healthcheck endpoint** — we rely on LiteLLM's `/health`.
- **Automated model warmup** — no cron to periodically ping Modal endpoints to
  keep them warm. Cold starts happen on demand; we accept the latency hit.
- **Secrets management integration** — `.env` is hand-managed. Future: pull
  from 1Password at compose time via `op inject`.
- **Backup of postgres-data** — handled by the Restic backup that covers
  `/Pondside` (once the stack is moved inside Pondside).
