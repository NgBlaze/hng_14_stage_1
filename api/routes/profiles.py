from fastapi import APIRouter, Query, Request, Path
from fastapi.responses import JSONResponse, Response
from typing import Optional

from api import services

CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

router = APIRouter(prefix="/api/profiles")


# ─── POST /api/profiles ───────────────────────────────────────────────────────

@router.post("")
async def create_profile(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing or empty name"},
            headers=CORS_HEADERS,
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing or empty name"},
            headers=CORS_HEADERS,
        )

    name = body.get("name")
    if name is None or name == "":
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing or empty name"},
            headers=CORS_HEADERS,
        )
    if not isinstance(name, str):
        return JSONResponse(
            status_code=422,
            content={"status": "error", "message": "Invalid type"},
            headers=CORS_HEADERS,
        )
    name = name.strip().lower()
    if not name:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing or empty name"},
            headers=CORS_HEADERS,
        )

    result = await services.create_profile_from_name(name)
    return JSONResponse(
        status_code=result["status_code"],
        content=result["body"],
        headers=CORS_HEADERS,
    )


# ─── GET /api/profiles/search  (must be before /{profile_id}) ─────────────────

@router.get("/search")
async def search_profiles(
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
):
    if not q or not q.strip():
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing or empty query"},
            headers=CORS_HEADERS,
        )

    result = services.search_profiles(q, page=page, limit=limit)
    return JSONResponse(
        status_code=result["status_code"],
        content=result["body"],
        headers=CORS_HEADERS,
    )


# ─── GET /api/profiles ────────────────────────────────────────────────────────

@router.get("")
async def list_profiles(
    gender: Optional[str] = Query(default=None),
    age_group: Optional[str] = Query(default=None),
    country_id: Optional[str] = Query(default=None),
    min_age: Optional[int] = Query(default=None),
    max_age: Optional[int] = Query(default=None),
    min_gender_probability: Optional[float] = Query(default=None),
    min_country_probability: Optional[float] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    order: str = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
):
    result = services.list_profiles(
        gender=gender,
        age_group=age_group,
        country_id=country_id,
        min_age=min_age,
        max_age=max_age,
        min_gender_probability=min_gender_probability,
        min_country_probability=min_country_probability,
        sort_by=sort_by,
        order=order,
        page=page,
        limit=limit,
    )
    return JSONResponse(
        status_code=result["status_code"],
        content=result["body"],
        headers=CORS_HEADERS,
    )


# ─── GET /api/profiles/{id} ───────────────────────────────────────────────────

@router.get("/{profile_id}")
async def get_profile(profile_id: str = Path(...)):
    result = services.get_profile_by_id(profile_id)
    return JSONResponse(
        status_code=result["status_code"],
        content=result["body"],
        headers=CORS_HEADERS,
    )


# ─── DELETE /api/profiles/{id} ────────────────────────────────────────────────

@router.delete("/{profile_id}")
async def delete_profile(profile_id: str = Path(...)):
    result = services.delete_profile_by_id(profile_id)
    if result["status_code"] == 204:
        return Response(status_code=204, headers=dict(CORS_HEADERS))
    return JSONResponse(
        status_code=result["status_code"],
        content=result["body"],
        headers=CORS_HEADERS,
    )
