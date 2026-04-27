import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi.util import get_remote_address

from api.auth import create_access_token, create_refresh_token, hash_token, verify_pkce
from api.database import SessionLocal
from api.limiter import limiter
from api.models import OAuthState, RefreshToken, User
from api.utils import generate_uuid7

GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")
WEB_PORTAL_URL = os.environ.get("WEB_PORTAL_URL", "").rstrip("/")
ADMIN_GITHUB_USERNAMES = {
    u.strip() for u in os.environ.get("ADMIN_GITHUB_USERNAMES", "").split(",") if u.strip()
}
REFRESH_TOKEN_EXPIRE_MINUTES = 5

router = APIRouter(prefix="/auth")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _issue_token_pair(user_id: str, role: str, db) -> tuple[str, str]:
    access_token = create_access_token(user_id, role)
    refresh_raw = create_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    rt = RefreshToken(
        id=generate_uuid7(),
        user_id=user_id,
        token_hash=hash_token(refresh_raw),
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(rt)
    db.commit()
    return access_token, refresh_raw


def _upsert_user(github_id: str, username: str, email: Optional[str], avatar_url: str, db) -> User:
    now = datetime.now(timezone.utc)
    user = db.query(User).filter(User.github_id == github_id).first()
    if user:
        user.username = username
        user.email = email
        user.avatar_url = avatar_url
        user.last_login_at = now
        if username in ADMIN_GITHUB_USERNAMES:
            user.role = "admin"
        db.commit()
    else:
        user = User(
            id=generate_uuid7(),
            github_id=github_id,
            username=username,
            email=email,
            avatar_url=avatar_url,
            role="admin" if username in ADMIN_GITHUB_USERNAMES else "analyst",
            is_active=True,
            last_login_at=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


async def _fetch_github_user(gh_token: str) -> tuple[dict, Optional[str]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        user_resp, email_resp = await asyncio.gather(
            client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/json"},
            ),
            client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/json"},
            ),
        )
    gh_user = user_resp.json()
    emails = email_resp.json() if isinstance(email_resp.json(), list) else []
    primary_email = next((e["email"] for e in emails if e.get("primary")), gh_user.get("email"))
    return gh_user, primary_email


# ─── GET /auth/github ─────────────────────────────────────────────────────────

@router.get("/github")
@limiter.limit("10/minute", key_func=get_remote_address)
async def github_oauth_start(request: Request):
    """Initiate GitHub OAuth for web portal."""
    state = secrets.token_urlsafe(32)
    db = SessionLocal()
    try:
        db.add(OAuthState(
            id=generate_uuid7(),
            state=state,
            source="web",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        ))
        db.commit()
    finally:
        db.close()

    callback_url = f"{BACKEND_URL}/auth/github/callback"
    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={callback_url}"
        f"&state={state}"
        f"&scope=read:user,user:email"
    )
    response = RedirectResponse(url=github_url)
    response.set_cookie("oauth_state", state, httponly=True, secure=True, samesite="lax", max_age=600)
    return response


# ─── GET /auth/github/callback ────────────────────────────────────────────────

@router.get("/github/callback")
@limiter.limit("10/minute", key_func=get_remote_address)
async def github_oauth_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """Handle GitHub OAuth redirect for web portal."""
    if error or not code or not state:
        return RedirectResponse(url=f"{WEB_PORTAL_URL}/login?error=oauth_failed")

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        oauth_state = (
            db.query(OAuthState)
            .filter(
                OAuthState.state == state,
                OAuthState.source == "web",
                OAuthState.used == False,
            )
            .first()
        )
        if not oauth_state or oauth_state.expires_at.replace(tzinfo=timezone.utc) < now:
            return RedirectResponse(url=f"{WEB_PORTAL_URL}/login?error=invalid_state")

        oauth_state.used = True
        db.commit()

        # Exchange code for GitHub access token
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": f"{BACKEND_URL}/auth/github/callback",
                },
                headers={"Accept": "application/json"},
            )
        gh_token = token_resp.json().get("access_token")
        if not gh_token:
            return RedirectResponse(url=f"{WEB_PORTAL_URL}/login?error=token_exchange_failed")

        # Fetch GitHub user info
        async with httpx.AsyncClient(timeout=10.0) as client:
            user_r = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/json"},
            )
            email_r = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/json"},
            )
        gh_user = user_r.json()
        emails = email_r.json() if isinstance(email_r.json(), list) else []
        primary_email = next((e["email"] for e in emails if e.get("primary")), gh_user.get("email"))

        user = _upsert_user(str(gh_user["id"]), gh_user["login"], primary_email, gh_user.get("avatar_url", ""), db)
        access_token, refresh_raw = _issue_token_pair(user.id, user.role, db)

    finally:
        db.close()

    # Redirect to web portal if it's a separate deployment, otherwise show backend success page
    portal = WEB_PORTAL_URL if (WEB_PORTAL_URL and WEB_PORTAL_URL != BACKEND_URL) else None
    redirect_url = f"{portal}/dashboard" if portal else f"{BACKEND_URL}/auth/success"

    response = RedirectResponse(url=redirect_url)
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="none", max_age=180)
    response.set_cookie("refresh_token", refresh_raw, httponly=True, secure=True, samesite="none", max_age=300)
    response.set_cookie("csrf_token", secrets.token_hex(32), httponly=False, secure=True, samesite="strict", max_age=180)
    return response


# ─── POST /auth/github/exchange (CLI PKCE flow) ───────────────────────────────

@router.post("/github/exchange")
@limiter.limit("10/minute", key_func=get_remote_address)
async def cli_exchange(request: Request):
    """CLI sends code + code_verifier after capturing the GitHub callback."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid request body"})

    code = body.get("code")
    code_verifier = body.get("code_verifier")
    code_challenge = body.get("code_challenge")
    redirect_uri = body.get("redirect_uri")

    if not all([code, code_verifier, code_challenge, redirect_uri]):
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "Missing required fields: code, code_verifier, code_challenge, redirect_uri"},
        )

    if not verify_pkce(code_verifier, code_challenge):
        raise HTTPException(status_code=400, detail={"status": "error", "message": "PKCE verification failed"})

    # Exchange code with GitHub
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    gh_token = token_resp.json().get("access_token")
    if not gh_token:
        raise HTTPException(status_code=502, detail={"status": "error", "message": "GitHub token exchange failed"})

    # Fetch GitHub user
    async with httpx.AsyncClient(timeout=10.0) as client:
        user_r = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/json"},
        )
        email_r = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/json"},
        )
    gh_user = user_r.json()
    emails = email_r.json() if isinstance(email_r.json(), list) else []
    primary_email = next((e["email"] for e in emails if e.get("primary")), gh_user.get("email"))

    db = SessionLocal()
    try:
        user = _upsert_user(str(gh_user["id"]), gh_user["login"], primary_email, gh_user.get("avatar_url", ""), db)
        access_token, refresh_raw = _issue_token_pair(user.id, user.role, db)
    finally:
        db.close()

    return JSONResponse(content={
        "status": "success",
        "access_token": access_token,
        "refresh_token": refresh_raw,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
        },
    })


# ─── POST /auth/refresh ───────────────────────────────────────────────────────

@router.post("/refresh")
@limiter.limit("10/minute", key_func=get_remote_address)
async def refresh_tokens(request: Request):
    refresh_raw = None
    try:
        body = await request.json()
        refresh_raw = body.get("refresh_token")
    except Exception:
        pass
    if not refresh_raw:
        refresh_raw = request.cookies.get("refresh_token")
    if not refresh_raw:
        raise HTTPException(status_code=401, detail={"status": "error", "message": "Refresh token required"})

    token_hash = hash_token(refresh_raw)
    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        rt = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash, RefreshToken.is_revoked == False)
            .first()
        )
        if not rt:
            raise HTTPException(status_code=401, detail={"status": "error", "message": "Invalid refresh token"})
        if rt.expires_at.replace(tzinfo=timezone.utc) < now:
            rt.is_revoked = True
            db.commit()
            raise HTTPException(status_code=401, detail={"status": "error", "message": "Refresh token expired"})

        rt.is_revoked = True
        db.commit()

        user = db.query(User).filter(User.id == rt.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail={"status": "error", "message": "Account inactive"})

        access_token, new_refresh_raw = _issue_token_pair(user.id, user.role, db)
    finally:
        db.close()

    response = JSONResponse(content={
        "status": "success",
        "access_token": access_token,
        "refresh_token": new_refresh_raw,
    })
    # If request came via cookie (web), update cookies too
    if request.cookies.get("refresh_token"):
        response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="none", max_age=180)
        response.set_cookie("refresh_token", new_refresh_raw, httponly=True, secure=True, samesite="none", max_age=300)
        response.set_cookie("csrf_token", secrets.token_hex(32), httponly=False, secure=True, samesite="strict", max_age=180)
    return response


# ─── POST /auth/logout ────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(request: Request):
    refresh_raw = None
    try:
        body = await request.json()
        refresh_raw = body.get("refresh_token")
    except Exception:
        pass
    if not refresh_raw:
        refresh_raw = request.cookies.get("refresh_token")

    if refresh_raw:
        db = SessionLocal()
        try:
            rt = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(refresh_raw)).first()
            if rt:
                rt.is_revoked = True
                db.commit()
        finally:
            db.close()

    response = JSONResponse(content={"status": "success", "message": "Logged out"})
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("csrf_token")
    return response


# ─── GET /auth/whoami ─────────────────────────────────────────────────────────

@router.get("/whoami")
async def whoami(request: Request):
    from api.auth import get_current_user
    user = await get_current_user(request)
    return JSONResponse(content={
        "status": "success",
        "data": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
        },
    })


# ─── GET /auth/success (fallback page before web portal is deployed) ──────────

@router.get("/success")
async def auth_success(request: Request):
    from fastapi.responses import HTMLResponse
    from api.auth import decode_access_token

    token = request.cookies.get("access_token")
    payload = decode_access_token(token) if token else None
    username = "unknown"

    if payload:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == payload["sub"]).first()
            if user:
                username = user.username
        finally:
            db.close()

    portal_url = WEB_PORTAL_URL if (WEB_PORTAL_URL and WEB_PORTAL_URL != BACKEND_URL) else None

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Insighta Labs+ — Login Successful</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f8fafc;display:flex;align-items:center;justify-content:center;
         min-height:100vh;padding:1rem}}
    .card{{background:#fff;border:1px solid #e2e8f0;border-radius:16px;
           padding:2.5rem;max-width:420px;width:100%;text-align:center;
           box-shadow:0 4px 24px rgba(0,0,0,.06)}}
    .check{{font-size:3rem;margin-bottom:1rem}}
    h1{{font-size:1.4rem;font-weight:700;color:#1e293b;margin-bottom:.5rem}}
    .username{{color:#4f46e5;font-weight:600}}
    p{{color:#64748b;font-size:.9rem;margin-bottom:1.5rem;line-height:1.6}}
    .btn{{display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;
          padding:.75rem 1.5rem;border-radius:8px;font-weight:600;font-size:.9rem;
          transition:background .2s}}
    .btn:hover{{background:#4338ca}}
    .hint{{margin-top:1.25rem;color:#94a3b8;font-size:.8rem}}
    code{{background:#f1f5f9;padding:.2em .4em;border-radius:4px;font-size:.85em}}
  </style>
</head>
<body>
  <div class="card">
    <div class="check">&#10003;</div>
    <h1>Logged in as <span class="username">@{username}</span></h1>
    <p>Authentication successful. Your session has been established.</p>
    {"<a class='btn' href='" + portal_url + "/dashboard'>Open Web Portal</a>" if portal_url else
     "<p style='color:#f59e0b;font-size:.85rem'>&#9888; Web portal not yet deployed.<br>Deploy it and set <code>WEB_PORTAL_URL</code> in your backend env.</p>"}
    <div class="hint">
      CLI users: your session is active. Run <code>insighta whoami</code> to confirm.
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)
