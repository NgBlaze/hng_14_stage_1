from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.auth import decode_access_token


def get_user_or_ip(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_access_token(auth[7:])
        if payload and payload.get("sub"):
            return payload["sub"]
    token = request.cookies.get("access_token")
    if token:
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            return payload["sub"]
    return get_remote_address(request)


limiter = Limiter(key_func=get_user_or_ip)
