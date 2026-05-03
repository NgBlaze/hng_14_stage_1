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

        _client = redis.Redis.from_url(
            _REDIS_URL,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        _client.ping()
        logger.info("redis cache: connected url=%s", _REDIS_URL.split("@")[-1])
    except Exception as e:
        logger.warning("redis cache: disabled (%s)", e)
        _client = None
    return _client


def cache_get(key: str) -> Optional[Any]:
    client = _get_client()
    if client is None:
        logger.info("cache disabled (no REDIS_URL): key=%s", key)
        return None
    try:
        raw = client.get(key)
        if raw:
            logger.info("cache HIT: key=%s", key)
            return json.loads(raw)
        logger.info("cache MISS: key=%s", key)
        return None
    except Exception as e:
        logger.warning("cache GET error: key=%s err=%s", key, e)
        return None


def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
        logger.info("cache SET: key=%s ttl=%ds", key, ttl)
    except Exception as e:
        logger.warning("cache SET error: key=%s err=%s", key, e)


def invalidate_profile_caches() -> None:
    """Drop every cached list/search payload after a write.

    Uses SCAN (not KEYS) so a large keyspace doesn't block Redis.
    """
    client = _get_client()
    if client is None:
        return
    try:
        deleted = 0
        for key in client.scan_iter(match=f"{_PROFILE_NAMESPACE}*", count=500):
            client.delete(key)
            deleted += 1
        logger.info("cache INVALIDATE: deleted=%d keys=%s*", deleted, _PROFILE_NAMESPACE)
    except Exception as e:
        logger.warning("cache INVALIDATE error: %s", e)
