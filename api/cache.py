"""Optional Redis cache layer.

When `REDIS_URL` is set, profile list/search responses are cached for a
short TTL and invalidated on writes. When unset (or the redis client
isn't installed), every call is a no-op so the rest of the app behaves
exactly as before.
"""
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", "").strip()
_PROFILE_NAMESPACE = "profiles:"

_client = None
_init_attempted = False


def _get_client():
    """Lazy, best-effort Redis connection. Failures degrade to no-op."""
    global _client, _init_attempted
    if _init_attempted:
        return _client
    _init_attempted = True
    if not _REDIS_URL:
        return None
    try:
        import redis  # type: ignore

        _client = redis.Redis.from_url(_REDIS_URL, decode_responses=True, socket_timeout=0.5)
        _client.ping()
        logger.info("redis cache: connected")
    except Exception as e:
        logger.warning("redis cache: disabled (%s)", e)
        _client = None
    return _client


def cache_get(key: str) -> Optional[Any]:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def invalidate_profile_caches() -> None:
    """Drop every cached list/search payload after a write.

    Uses SCAN (not KEYS) so a large keyspace doesn't block Redis.
    """
    client = _get_client()
    if client is None:
        return
    try:
        for key in client.scan_iter(match=f"{_PROFILE_NAMESPACE}*", count=500):
            client.delete(key)
    except Exception:
        pass
