# harbormaster

LiteLLM proxy with a Tailscale sidecar. Serves `https://api.tail8bd569.ts.net`.

Routes local inference — chat and embedding models — with Ember as the primary
backend and Modal serverless (see `../modal-serverless-inference/`) as the
fallback. When Ember is unreachable, LiteLLM transparently routes to the
Modal endpoint for the same model. Admin UI lives at `/ui` for virtual keys,
spend tracking, request logs, and model management.

## What's in here

```
compose.yml          Tailscale sidecar + Postgres + LiteLLM
config.yaml          LiteLLM routing + fallbacks + cooldown + health checks
serve-config.json    Tailscale Serve: HTTPS :443 → localhost:4000
.env.example         Template for .env (gitignored)
```

## Standing it up from nothing

```bash
# 1. Populate secrets
cp .env.example .env
$EDITOR .env   # fill in all the XXX values; see generation hints in the file

# 2. Bring up the stack (tailscale sidecar, postgres, litellm)
docker compose up -d

# 3. Watch the Tailscale sidecar join the tailnet (30-60 seconds)
docker compose logs -f tailscale
# Look for: "Success. Still logged in as tagged-node @api (owner: jefferyharrell)"

# 4. Disable machine key expiry
#    Browser: https://login.tailscale.com/admin/machines
#    Find the `api` machine → settings → "Disable key expiry"
#    After this, TS_AUTHKEY can expire without breaking anything.

# 5. Verify API routing
curl https://api.tail8bd569.ts.net/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# 6. Log in to the UI
#    Browser: https://api.tail8bd569.ts.net/ui
#    Username/password: whatever you set for UI_USERNAME / UI_PASSWORD
```

## What the UI is good for

- **Models tab:** see all registered models (primary + fallback pairs) and
  their health status
- **Virtual Keys:** mint per-client keys (e.g., one for Alpha-App, one for
  Rosemary-App, one for Jeffery's BoltAI, etc.) with independent spend/rate
  limits
- **Spend:** daily spend trends, per-key spend, per-model spend
- **Logs:** request logs with status codes, latency, and token counts —
  much nicer than `docker logs | grep`
- **Test:** built-in request tester — send a prompt to any model from the UI

## Fallback behavior

LiteLLM's fallback kicks in when the primary (Ember) is down or slow:

1. Client calls `POST /v1/chat/completions` with `model: "unsloth/qwen3.5-4b"`
2. LiteLLM routes to Ember at `https://ember.tail8bd569.ts.net/v1`
3. If Ember is down (connection refused) or llama-swap is stopped:
   - Primary has `max_retries: 0` — fail fast, one attempt
   - After one failure, primary is **benched for 2 minutes** (cooldown)
   - During cooldown, requests skip straight to `-modal` fallback
   - Modal cold-starts (~10-15s), may initially return 503 "Loading model"
   - Fallback entry's `num_retries: 3` absorbs the cold-start window
   - Client gets a successful response, ~15s delay on first cold call
4. Background health checks (every 30s) proactively probe Ember.
   Once Ember responds cleanly, it rejoins the routing pool. No manual
   intervention needed.

Failover is transparent to the client. First call after Ember goes down
pays the Modal cold-start tax (~15s). Every call after that is normal
until Ember recovers.

## Secrets — the one that's load-bearing

`LITELLM_SALT_KEY` encrypts stored API keys in Postgres. It's **immutable
after the first model is added** — rotating it breaks existing stored
credentials. Generate it once (`echo "sk-salt-$(openssl rand -hex 24)"`),
put it in `.env`, never touch it again.

The other secrets (master key, UI password, Postgres password) are
rotatable normally if leaked.
