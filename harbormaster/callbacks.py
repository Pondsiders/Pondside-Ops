"""Harbormaster custom callbacks.

Captures Anthropic response headers (anthropic-ratelimit-unified-*) from
every Claude request that flows through the proxy. Writes rows to a
dedicated `anthropic_usage` table in our Postgres.

Schema:
    id            SERIAL PRIMARY KEY
    ts            TIMESTAMPTZ DEFAULT NOW()
    key_alias     TEXT      -- virtual key alias ("alpha", "rosemary", etc.)
    key_hash      TEXT      -- virtual key hash (stable identity)
    model         TEXT      -- upstream model name
    status_5h           TEXT       -- allowed / allowed_warning / rejected
    util_5h             NUMERIC    -- 0.0–1.0
    reset_5h            TIMESTAMPTZ
    status_7d           TEXT
    util_7d             NUMERIC
    reset_7d            TIMESTAMPTZ
    representative      TEXT       -- which window dominates ('five_hour' / 'seven_day')
    overage_status      TEXT       -- allowed / rejected
    request_id          TEXT       -- anthropic request id (for cross-ref)
    raw_headers         JSONB      -- full llm_provider- headers for archaeology
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import asyncpg  # type: ignore[import-not-found]
from litellm.integrations.custom_logger import CustomLogger

_RATE_HEADER_PREFIX = "llm_provider-anthropic-ratelimit-"
# Prefer Neon for observability data. Fall back to local Postgres for
# dev/testing if NEON_DATABASE_URL isn't set.
_DATABASE_URL = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS anthropic_usage (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    key_alias       TEXT,
    key_hash        TEXT,
    model           TEXT,
    status_5h       TEXT,
    util_5h         NUMERIC,
    reset_5h        TIMESTAMPTZ,
    status_7d       TEXT,
    util_7d         NUMERIC,
    reset_7d        TIMESTAMPTZ,
    representative  TEXT,
    overage_status  TEXT,
    request_id      TEXT,
    raw_headers     JSONB
);
CREATE INDEX IF NOT EXISTS anthropic_usage_ts_idx ON anthropic_usage (ts DESC);
CREATE INDEX IF NOT EXISTS anthropic_usage_key_alias_idx ON anthropic_usage (key_alias);
"""


def _to_ts(epoch_str: str | None) -> datetime | None:
    if not epoch_str:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_str), tz=timezone.utc)
    except (ValueError, TypeError):
        return None


def _to_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class AnthropicUsageLogger(CustomLogger):
    """On every successful request, if it was an Anthropic call, extract
    the rate-limit headers and persist them.
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def _pool_or_init(self) -> asyncpg.Pool:
        if self._pool is None:
            # Parse manually and pass kwargs so we avoid any query-string
            # params (sslmode, channel_binding, connection_limit) that
            # asyncpg's URL parser doesn't handle uniformly. SSL is
            # required for Neon; we pass it explicitly.
            from urllib.parse import urlparse
            parsed = urlparse(_DATABASE_URL)
            # Neon hostnames end in .neon.tech and require SSL
            is_neon = parsed.hostname and "neon.tech" in parsed.hostname
            self._pool = await asyncpg.create_pool(
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port or 5432,
                database=(parsed.path or "/").lstrip("/"),
                min_size=1,
                max_size=4,
                server_settings={},
                ssl="require" if is_neon else None,
            )
            async with self._pool.acquire() as conn:
                await conn.execute(_SCHEMA_SQL)
        return self._pool

    async def async_log_success_event(
        self, kwargs: dict, response_obj: Any, start_time, end_time
    ) -> None:
        """Fires for /v1/chat/completions path (all providers)."""
        await self._capture(kwargs, response_obj)

    async def async_post_call_success_hook(
        self, data: dict, user_api_key_dict: Any, response: Any
    ) -> Any:
        """Fires for /v1/messages (Anthropic pass-through) path.

        LiteLLM contract: return the response unchanged.
        """
        # Build a kwargs-shaped dict so _capture can treat both paths uniformly.
        # For the pass-through path the metadata is attached differently.
        kwargs_like = {
            "model": data.get("model"),
            "litellm_params": {"metadata": {
                "user_api_key_alias": getattr(user_api_key_dict, "key_alias", None),
                "user_api_key_hash": getattr(user_api_key_dict, "token", None),
            }},
        }
        await self._capture(kwargs_like, response)
        return response

    async def _capture(self, kwargs: dict, response_obj: Any) -> None:
        try:
            hidden = getattr(response_obj, "_hidden_params", None) or {}
            headers: dict = hidden.get("additional_headers") or {}

            # Detect by header presence, not by custom_llm_provider — the
            # /v1/messages pass-through path leaves custom_llm_provider as
            # None while still carrying the llm_provider- prefixed headers
            # from the Anthropic response.
            anthropic_headers = {
                k[len("llm_provider-"):]: v
                for k, v in headers.items()
                if k.startswith("llm_provider-")
            }
            if not any(k.startswith("anthropic-ratelimit-") for k in anthropic_headers):
                # Not an Anthropic request we care about (Ollama, LM Studio, etc.)
                return

            # Attribution
            meta = (kwargs.get("litellm_params") or {}).get("metadata") or {}
            key_alias = meta.get("user_api_key_alias")
            key_hash = meta.get("user_api_key_hash")
            model = kwargs.get("model")

            pool = await self._pool_or_init()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO anthropic_usage (
                        key_alias, key_hash, model,
                        status_5h, util_5h, reset_5h,
                        status_7d, util_7d, reset_7d,
                        representative, overage_status,
                        request_id, raw_headers
                    ) VALUES (
                        $1, $2, $3,
                        $4, $5, $6,
                        $7, $8, $9,
                        $10, $11,
                        $12, $13::jsonb
                    )
                    """,
                    key_alias,
                    key_hash,
                    model,
                    anthropic_headers.get("anthropic-ratelimit-unified-5h-status"),
                    _to_float(anthropic_headers.get("anthropic-ratelimit-unified-5h-utilization")),
                    _to_ts(anthropic_headers.get("anthropic-ratelimit-unified-5h-reset")),
                    anthropic_headers.get("anthropic-ratelimit-unified-7d-status"),
                    _to_float(anthropic_headers.get("anthropic-ratelimit-unified-7d-utilization")),
                    _to_ts(anthropic_headers.get("anthropic-ratelimit-unified-7d-reset")),
                    anthropic_headers.get("anthropic-ratelimit-unified-representative-claim"),
                    anthropic_headers.get("anthropic-ratelimit-unified-overage-status"),
                    anthropic_headers.get("request-id"),
                    __import__("json").dumps(anthropic_headers),
                )
        except Exception as exc:  # noqa: BLE001
            # Don't let observability take down the request path
            import sys
            print(f"[anthropic_usage_logger] error: {exc}", file=sys.stderr, flush=True)


anthropic_usage = AnthropicUsageLogger()
