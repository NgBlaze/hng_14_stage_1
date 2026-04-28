from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.auth import get_current_user
from api.limiter import limiter

router = APIRouter(prefix="/api/users")


@router.get("/me")
@limiter.limit("60/minute")
async def get_me(request: Request, user=Depends(get_current_user)):
    return JSONResponse(content={
        "status": "success",
        "data": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "is_active": user.is_active,
        },
    })
