# harbormaster

LiteLLM proxy with a Tailscale sidecar. Serves `https://api.tail8bd569.ts.net`.

Routes local inference — chat and embedding models — with Ember as the primary
backend and Modal serverless (see `../modal-serverless-inference/`) as the
fallback. When Ember is unreachable or returns a 5xx, LiteLLM transparently
retries against the Modal endpoint for the same model.

## What's in here

```
compose.yml          Tailscale sidecar + LiteLLM
config.yaml          LiteLLM routing: Ember primary + Modal fallback
serve-config.json    Tailscale Serve: HTTPS :443 → localhost:4000
.env.example         Template for .env (gitignored)
```

## Standing it up from nothing

```bash
# 1. Populate secrets
cp .env.example .env
$EDITOR .env   # generate TS_AUTHKEY and LITELLM_MASTER_KEY

# 2. Bring up the stack
docker compose up -d

# 3. Watch the Tailscale sidecar join the tailnet (30-60 seconds)
docker compose logs -f tailscale
# Look for: "Success. Still logged in as tagged-node @api (owner: jefferyharrell)"

# 4. Disable machine key expiry
#    Browser: https://login.tailscale.com/admin/machines
#    Find the `api` machine → settings → "Disable key expiry"
#    After this, TS_AUTHKEY can expire without breaking anything.

# 5. Verify HTTPS and routing
curl https://api.tail8bd569.ts.net/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```

## Fallback behavior

LiteLLM's fallback kicks in when the primary (Ember) returns 5xx or times out:

1. Client calls `POST /v1/chat/completions` with `model: "unsloth/qwen3.5-4b"`
2. LiteLLM routes to Ember at `https://ember.tail8bd569.ts.net/v1`
3. If Ember is down (connection refused) or llama-swap is stopped:
   - LiteLLM's `num_retries: 2` exhausts against Ember first
   - Then falls back to `unsloth/qwen3.5-4b-modal`
   - Modal cold-starts (~10-15s), may initially return 503 "Loading model"
   - The Modal entry's `num_retries: 3` absorbs the cold-start window
   - Client gets a successful response, slightly delayed on first call
4. Subsequent calls go through the warm Modal container until
   `scaledown_window` expires (5 min idle), at which point cold-start
   happens again.

Failover is transparent to the client. Worst-case user-visible latency is
~30-40s on the first call after Ember goes down. Every call after that is
normal (Modal-warm) until Ember comes back up.
