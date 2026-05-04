import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Path, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from api import services
from api.auth import check_api_version, check_csrf, get_current_user, require_admin
from api.ratelimit import api_rate_limit

router = APIRouter(prefix="/api/profiles")


def _pagination_links(base: str, filters: dict, page: int, limit: int, total: int) -> dict:
    total_pages = max(1, (total + limit - 1) // limit)

    def url(p: int) -> str:
        parts = [f"page={p}", f"limit={limit}"]
        parts += [f"{k}={v}" for k, v in filters.items() if v is not None]
        return f"{base}?{'&'.join(parts)}"

    return {
        "self": url(page),
        "next": url(page + 1) if page < total_pages else None,
        "prev": url(page - 1) if page > 1 else None,
    }


# ─── POST /api/profiles (admin only) ─────────────────────────────────────────

@router.post("")

async def create_profile(
    request: Request,
    user=Depends(require_admin),
    _=Depends(check_api_version),
    __=Depends(check_csrf),
    ___=Depends(api_rate_limit),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Missing or empty name"})

    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"status": "error", "message": "Missing or empty name"})

    name = body.get("name")
    if not name or not isinstance(name, str):
        return JSONResponse(status_code=400, content={"status": "error", "message": "Missing or empty name"})
    name = name.strip().lower()
    if not name:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Missing or empty name"})

    result = await services.create_profile_from_name(name)
    return JSONResponse(status_code=result["status_code"], content=result["body"])


# ─── POST /api/profiles/upload (admin only) ──────────────────────────────────

@router.post("/upload")
async def upload_profiles(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require_admin),
    _=Depends(check_api_version),
    __=Depends(check_csrf),
    ___=Depends(api_rate_limit),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Expected a .csv file"},
        )

    # Service is sync (DB I/O + csv.DictReader); run off the event loop so
    # other requests on this worker keep responding.
    result = await run_in_threadpool(services.upload_profiles_csv, file.file)
    return JSONResponse(status_code=result["status_code"], content=result["body"])


# ─── GET /api/profiles/export ─────────────────────────────────────────────────

@router.get("/export")

async def export_profiles(
    request: Request,
    fmt: str = Query(alias="format"),
    gender: Optional[str] = Query(default=None),
    age_group: Optional[str] = Query(default=None),
    country_id: Optional[str] = Query(default=None),
    min_age: Optional[int] = Query(default=None),
    max_age: Optional[int] = Query(default=None),
    min_gender_probability: Optional[float] = Query(default=None),
    min_country_probability: Optional[float] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    order: str = Query(default="asc"),
    user=Depends(get_current_user),
    _=Depends(check_api_version),
    __=Depends(api_rate_limit),
):
    if fmt.lower() != "csv":
        return JSONResponse(status_code=400, content={"status": "error", "message": "Only csv format is supported"})

    result = services.list_profiles(
        gender=gender, age_group=age_group, country_id=country_id,
        min_age=min_age, max_age=max_age,
        min_gender_probability=min_gender_probability,
        min_country_probability=min_country_probability,
        sort_by=sort_by, order=order,
        page=1, limit=100_000,
    )
    if result["status_code"] != 200:
        return JSONResponse(status_code=result["status_code"], content=result["body"])

    fieldnames = [
        "id", "name", "gender", "gender_probability", "age", "age_group",
        "country_id", "country_name", "country_probability", "created_at",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(result["body"]["data"])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="profiles_{timestamp}.csv"'},
    )


# ─── GET /api/profiles/search ─────────────────────────────────────────────────

@router.get("/search")

async def search_profiles(
    request: Request,
    q: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    user=Depends(get_current_user),
    _=Depends(check_api_version),
    __=Depends(api_rate_limit),
):
    if not q or not q.strip():
        return JSONResponse(status_code=400, content={"status": "error", "message": "Missing or empty query"})

    result = services.search_profiles(q, page=page, limit=limit)
    if result["status_code"] == 200:
        body = result["body"]
        total = body["total"]
        body["total_pages"] = max(1, (total + limit - 1) // limit)
        body["links"] = _pagination_links("/api/profiles/search", {"q": q}, page, limit, total)
    return JSONResponse(status_code=result["status_code"], content=result["body"])


# ─── GET /api/profiles ────────────────────────────────────────────────────────

@router.get("")

async def list_profiles(
    request: Request,
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
    user=Depends(get_current_user),
    _=Depends(check_api_version),
    __=Depends(api_rate_limit),
):
    result = services.list_profiles(
        gender=gender, age_group=age_group, country_id=country_id,
        min_age=min_age, max_age=max_age,
        min_gender_probability=min_gender_probability,
        min_country_probability=min_country_probability,
        sort_by=sort_by, order=order, page=page, limit=limit,
    )
    if result["status_code"] == 200:
        body = result["body"]
        total = body["total"]
        body["total_pages"] = max(1, (total + limit - 1) // limit)
        body["links"] = _pagination_links(
            "/api/profiles",
            {"gender": gender, "age_group": age_group, "country_id": country_id,
             "min_age": min_age, "max_age": max_age, "sort_by": sort_by,
             "order": order if order != "asc" else None},
            page, limit, total,
        )
    return JSONResponse(status_code=result["status_code"], content=result["body"])


# ─── GET /api/profiles/{id} ───────────────────────────────────────────────────

@router.get("/{profile_id}")

async def get_profile(
    request: Request,
    profile_id: str = Path(...),
    user=Depends(get_current_user),
    _=Depends(check_api_version),
    __=Depends(api_rate_limit),
):
    result = services.get_profile_by_id(profile_id)
    return JSONResponse(status_code=result["status_code"], content=result["body"])


# ─── DELETE /api/profiles/{id} (admin only) ───────────────────────────────────

@router.delete("/{profile_id}")

async def delete_profile(
    request: Request,
    profile_id: str = Path(...),
    user=Depends(require_admin),
    _=Depends(check_api_version),
    __=Depends(check_csrf),
    ___=Depends(api_rate_limit),
):
    result = services.delete_profile_by_id(profile_id)
    if result["status_code"] == 204:
        return Response(status_code=204)
    return JSONResponse(status_code=result["status_code"], content=result["body"])
