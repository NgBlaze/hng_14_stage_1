from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.auth import get_current_user
from api.ratelimit import api_rate_limit

router = APIRouter(prefix="/api/users")


@router.get("/me")
async def get_me(
    request: Request,
    user=Depends(get_current_user),
    _=Depends(api_rate_limit),
):
    return JSONResponse(content={
        "status": "success",
        "data": {
            "id": user.id,
            "github_id": user.github_id,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "is_active": user.is_active,
        },
    })
