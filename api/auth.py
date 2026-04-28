import hashlib
import base64
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.database import SessionLocal

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "insecure-dev-key")
ACCESS_TOKEN_EXPIRE_MINUTES = 3
REFRESH_TOKEN_EXPIRE_MINUTES = 5
ALGORITHM = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire, "type": "access"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.PyJWTError:
        return None


def generate_pkce_pair() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    code_verifier = secrets.token_urlsafe(43)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return computed == code_challenge


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    from api.models import User

    token = credentials.credentials if credentials else request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Authentication required"},
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Invalid or expired token"},
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == payload["sub"]).first()
        if not user:
            raise HTTPException(
                status_code=401,
                detail={"status": "error", "message": "User not found"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail={"status": "error", "message": "Account is inactive"},
            )
        return user
    finally:
        db.close()


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"status": "error", "message": "Admin access required"},
        )
    return user


def check_api_version(request: Request, x_api_version: Optional[str] = Header(default=None)):
    # also accept ?api_version=1 for browser-navigable endpoints (e.g. CSV export)
    effective = x_api_version or request.query_params.get("api_version")
    if effective != "1":
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "API version header required"},
        )
