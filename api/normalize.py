"""
Canonicalization for cache keys.

Two requests that resolve to the same logical query must produce the same
cache key, regardless of how the user expressed them. For example:

    GET /api/profiles/search?q=Nigerian females between 20 and 45
    GET /api/profiles/search?q=Women aged 20-45 living in Nigeria
    GET /api/profiles?gender=female&country_id=NG&min_age=20&max_age=45

all parse to the same filter dict and therefore share one cache entry.
"""

from typing import Any

# Keys are listed in a fixed order so the resulting string is deterministic
# regardless of dict insertion order.
_FILTER_KEYS = (
    "gender",
    "age_group",
    "country_id",
    "min_age",
    "max_age",
    "min_gender_probability",
    "min_country_probability",
    "sort_by",
    "order",
)


def _normalize_value(key: str, value: Any) -> str:
    if value is None:
        return ""
    if key == "country_id":
        return str(value).strip().upper()
    if key in ("gender", "age_group", "sort_by", "order"):
        return str(value).strip().lower()
    return str(value)


def canonical_filter_key(filters: dict) -> str:
    """
    Produce a deterministic key fragment from a filter dict.

    Unset (None or missing) values collapse to empty so equivalent queries —
    one with `min_age=None`, one omitting `min_age` entirely — yield the
    same key.
    """
    parts = [_normalize_value(k, filters.get(k)) for k in _FILTER_KEYS]
    return ":".join(parts)


def cache_key_for(filters: dict, page: int, limit: int, *, prefix: str = "profiles:q") -> str:
    """
    Build the full Redis cache key for a paginated filtered query.

    `prefix` defaults to `profiles:q` (shared between list and search) so
    `invalidate_profile_caches()` continues to wipe both via SCAN profiles:*.
    """
    return f"{prefix}:{canonical_filter_key(filters)}:p{page}:l{limit}"
