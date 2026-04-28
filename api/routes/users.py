from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.auth import get_current_user

router = APIRouter(prefix="/api/users")


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
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
