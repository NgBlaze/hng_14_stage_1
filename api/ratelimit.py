"""Postgres-backed sliding-window rate limiter.

slowapi's in-memory storage doesn't survive across Vercel serverless
invocations, so the spec'd limits (10/min on /auth/*, 60/min elsewhere)
were effectively unenforced. This module provides a DB-backed counter
that works regardless of which container handles a request.
"""
import os
import time

from fastapi import HTTPException, Request
from sqlalchemy import text

from api.auth import decode_access_token
from api.database import SessionLocal, engine

# Disable rate limit entirely (escape hatch) by setting RATE_LIMIT_DISABLED=1
_DISABLED = os.environ.get("RATE_LIMIT_DISABLED", "").strip() == "1"

_TABLE_READY = False


def _ensure_table():
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        with engine.connect() as conn:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_buckets (
                    key VARCHAR PRIMARY KEY,
                    window_start BIGINT NOT NULL,
                    count INTEGER NOT NULL
                )
                """
            ))
            conn.commit()
        _TABLE_READY = True
    except Exception:
        # Best-effort; if table init fails we silently allow requests
        pass


def _identity(request: Request) -> str:
    """Prefer authenticated user id, otherwise the client IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_access_token(auth[7:])
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"
    cookie = request.cookies.get("access_token")
    if cookie:
        payload = decode_access_token(cookie)
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"
    # Trust X-Forwarded-For from Vercel
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return f"ip:{fwd.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def _check(key: str, limit: int, window_seconds: int = 60):
    if _DISABLED:
        return
    _ensure_table()

    now = int(time.time())
    window_start = (now // window_seconds) * window_seconds

    db = SessionLocal()
    try:
        # Atomic upsert that resets count when the window changes
        result = db.execute(
            text(
                """
                INSERT INTO rate_limit_buckets (key, window_start, count)
                VALUES (:key, :ws, 1)
                ON CONFLICT (key) DO UPDATE SET
                    count = CASE
                        WHEN rate_limit_buckets.window_start = EXCLUDED.window_start
                        THEN rate_limit_buckets.count + 1
                        ELSE 1
                    END,
                    window_start = EXCLUDED.window_start
                RETURNING count
                """
            ),
            {"key": key, "ws": window_start},
        )
        row = result.first()
        db.commit()
        count = row[0] if row else 1
    except Exception:
        # If DB hiccups, fail-open rather than denying valid traffic
        db.rollback()
        return
    finally:
        db.close()

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail={"status": "error", "message": "Rate limit exceeded. Please try again later."},
        )


def auth_rate_limit(request: Request):
    """10 requests / minute on /auth/* per IP."""
    ident = _identity(request)
    _check(f"auth:{ident}", limit=10, window_seconds=60)


def api_rate_limit(request: Request):
    """60 requests / minute on /api/* per user (or IP fallback)."""
    ident = _identity(request)
    _check(f"api:{ident}", limit=60, window_seconds=60)
