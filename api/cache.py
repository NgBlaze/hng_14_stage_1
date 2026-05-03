"""Optional Redis cache layer.

When `REDIS_URL` is set, profile list/search responses are cached for a
short TTL and invalidated on writes. When unset (or the redis client
isn't installed), every call is a no-op so the rest of the app behaves
exactly as before.
"""
import json
import logging
import os
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", "").strip()
_PROFILE_NAMESPACE = "profiles:"

_client = None
_init_attempted = False


def _emit(level: str, msg: str) -> None:
    """Belt-and-suspenders logger: WARNING-level + stdout print.

    Vercel's log viewer sometimes hides INFO-level lines, and the Python
    runtime occasionally buffers stdout. Logging at WARNING and printing
    with flush=True guarantees the line surfaces in the function logs.
    """
    line = f"[CACHE] {msg}"
    if level == "warning":
        logger.warning(line)
    else:
        logger.info(line)
    print(line, file=sys.stdout, flush=True)


# Loud import-time marker so we can confirm the deploy is running this build.
_emit("info", f"module loaded redis_url_set={bool(_REDIS_URL)}")


def _get_client():
    """Lazy, best-effort Redis connection. Failures degrade to no-op."""
    global _client, _init_attempted
    if _init_attempted:
        return _client
    _init_attempted = True
    if not _REDIS_URL:
        _emit("warning", "init: REDIS_URL is empty — cache disabled")
        return None
    try:
        import redis  # type: ignore

        _client = redis.Redis.from_url(
            _REDIS_URL,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        pong = _client.ping()
        _emit(
            "warning",
            f"init: connected ping={pong} host={_REDIS_URL.split('@')[-1]}",
        )
    except Exception as e:
        _emit("warning", f"init: disabled type={type(e).__name__} err={e}")
        _client = None
    return _client


def cache_get(key: str) -> Optional[Any]:
    client = _get_client()
    if client is None:
        _emit("warning", f"GET skipped (no client) key={key}")
        return None
    try:
        raw = client.get(key)
        if raw:
            _emit("warning", f"HIT  key={key} bytes={len(raw)}")
            return json.loads(raw)
        _emit("warning", f"MISS key={key}")
        return None
    except Exception as e:
        _emit("warning", f"GET error key={key} type={type(e).__name__} err={e}")
        return None


def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        payload = json.dumps(value, default=str)
        client.setex(key, ttl, payload)
        _emit("warning", f"SET  key={key} ttl={ttl}s bytes={len(payload)}")
    except Exception as e:
        _emit("warning", f"SET error key={key} type={type(e).__name__} err={e}")


def invalidate_profile_caches() -> None:
    """Drop every cached list/search payload after a write."""
    client = _get_client()
    if client is None:
        return
    try:
        deleted = 0
        for key in client.scan_iter(match=f"{_PROFILE_NAMESPACE}*", count=500):
            client.delete(key)
            deleted += 1
        _emit("warning", f"INVALIDATE deleted={deleted} pattern={_PROFILE_NAMESPACE}*")
    except Exception as e:
        _emit("warning", f"INVALIDATE error type={type(e).__name__} err={e}")
