from fastapi import FastAPI, Query, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine, Column, String, Float, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from datetime import datetime, timezone
from typing import Optional
import httpx
import asyncio
import os
import time
import random

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

# ─── UUID v7 ──────────────────────────────────────────────────────────────────

def generate_uuid7() -> str:
    """Generate a UUID version 7 (time-ordered, random suffix)."""
    ts_ms = int(time.time() * 1000)
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)
    # high 64 bits: [unix_ts_ms(48) | ver=7(4) | rand_a(12)]
    high = (ts_ms << 16) | (0x7 << 12) | rand_a
    # low 64 bits: [variant=10(2) | rand_b(62)]
    low = (0b10 << 62) | rand_b
    hi = high.to_bytes(8, "big")
    lo = low.to_bytes(8, "big")
    return (
        f"{hi[0:4].hex()}-{hi[4:6].hex()}-{hi[6:8].hex()}"
        f"-{lo[0:2].hex()}-{lo[2:8].hex()}"
    )

# ─── Age classification ────────────────────────────────────────────────────────

def classify_age(age: int) -> str:
    if age <= 12:
        return "child"
    if age <= 19:
        return "teenager"
    if age <= 59:
        return "adult"
    return "senior"

# ─── Database ─────────────────────────────────────────────────────────────────

_raw_url = os.environ.get("DATABASE_URL", "sqlite:////tmp/profiles.db")
# Heroku/some platforms use postgres:// but SQLAlchemy 2.x needs postgresql://
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql://", 1)

if _raw_url.startswith("sqlite"):
    engine = create_engine(
        _raw_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(_raw_url, poolclass=NullPool, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    gender = Column(String)
    gender_probability = Column(Float)
    sample_size = Column(Integer)
    age = Column(Integer)
    age_group = Column(String)
    country_id = Column(String)
    country_probability = Column(Float)
    created_at = Column(String)


Base.metadata.create_all(bind=engine)


def row_to_dict(p: Profile, summary: bool = False) -> dict:
    if summary:
        return {
            "id": p.id,
            "name": p.name,
            "gender": p.gender,
            "age": p.age,
            "age_group": p.age_group,
            "country_id": p.country_id,
        }
    return {
        "id": p.id,
        "name": p.name,
        "gender": p.gender,
        "gender_probability": p.gender_probability,
        "sample_size": p.sample_size,
        "age": p.age,
        "age_group": p.age_group,
        "country_id": p.country_id,
        "country_probability": p.country_probability,
        "created_at": p.created_at,
    }

# ─── Validation error handler ─────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Invalid input type"},
        headers=CORS_HEADERS,
    )

# ─── POST /api/profiles ───────────────────────────────────────────────────────

@app.post("/api/profiles")
async def create_profile(request: Request):
    # Parse request body
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
    name = name.strip()
    if not name:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Missing or empty name"},
            headers=CORS_HEADERS,
        )
    name = name.lower()

    # Check for existing profile (idempotency)
    db = SessionLocal()
    try:
        existing = db.query(Profile).filter(Profile.name == name).first()
        if existing:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Profile already exists",
                    "data": row_to_dict(existing),
                },
                headers=CORS_HEADERS,
            )
    finally:
        db.close()

    # Fetch from all three external APIs concurrently
    async def fetch(url: str, params: dict):
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()

    results = await asyncio.gather(
        fetch("https://api.genderize.io", {"name": name}),
        fetch("https://api.agify.io", {"name": name}),
        fetch("https://api.nationalize.io", {"name": name}),
        return_exceptions=True,
    )

    gender_data, age_data, nation_data = results

    # Check for HTTP / network errors per API
    api_names = ["Genderize", "Agify", "Nationalize"]
    for api_name, result in zip(api_names, results):
        if isinstance(result, Exception):
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "message": f"{api_name} returned an invalid response",
                },
                headers=CORS_HEADERS,
            )

    # Validate Genderize response
    if not gender_data.get("gender") or gender_data.get("count", 0) == 0:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "Genderize returned an invalid response",
            },
            headers=CORS_HEADERS,
        )

    # Validate Agify response
    if age_data.get("age") is None:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "Agify returned an invalid response",
            },
            headers=CORS_HEADERS,
        )

    # Validate Nationalize response
    countries = nation_data.get("country", [])
    if not countries:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "Nationalize returned an invalid response",
            },
            headers=CORS_HEADERS,
        )

    # Build profile record
    top_country = max(countries, key=lambda c: c.get("probability", 0))
    age = age_data["age"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    db = SessionLocal()
    try:
        profile = Profile(
            id=generate_uuid7(),
            name=name,
            gender=gender_data["gender"],
            gender_probability=gender_data.get("probability", 0.0),
            sample_size=gender_data.get("count", 0),
            age=age,
            age_group=classify_age(age),
            country_id=top_country["country_id"],
            country_probability=top_country.get("probability", 0.0),
            created_at=now,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        return JSONResponse(
            status_code=201,
            content={"status": "success", "data": row_to_dict(profile)},
            headers=CORS_HEADERS,
        )
    except Exception:
        db.rollback()
        # Race condition: another concurrent request may have inserted this name
        existing = db.query(Profile).filter(Profile.name == name).first()
        if existing:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Profile already exists",
                    "data": row_to_dict(existing),
                },
                headers=CORS_HEADERS,
            )
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error"},
            headers=CORS_HEADERS,
        )
    finally:
        db.close()

# ─── GET /api/profiles ────────────────────────────────────────────────────────

@app.get("/api/profiles")
async def list_profiles(
    gender: Optional[str] = Query(default=None),
    country_id: Optional[str] = Query(default=None),
    age_group: Optional[str] = Query(default=None),
):
    db = SessionLocal()
    try:
        q = db.query(Profile)
        if gender:
            q = q.filter(Profile.gender.ilike(gender.strip()))
        if country_id:
            q = q.filter(Profile.country_id.ilike(country_id.strip()))
        if age_group:
            q = q.filter(Profile.age_group.ilike(age_group.strip()))
        profiles = q.all()
        data = [row_to_dict(p, summary=True) for p in profiles]
        return JSONResponse(
            status_code=200,
            content={"status": "success", "count": len(data), "data": data},
            headers=CORS_HEADERS,
        )
    finally:
        db.close()

# ─── GET /api/profiles/{id} ───────────────────────────────────────────────────

@app.get("/api/profiles/{profile_id}")
async def get_profile(profile_id: str = Path(...)):
    db = SessionLocal()
    try:
        p = db.query(Profile).filter(Profile.id == profile_id).first()
        if not p:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Profile not found"},
                headers=CORS_HEADERS,
            )
        return JSONResponse(
            status_code=200,
            content={"status": "success", "data": row_to_dict(p)},
            headers=CORS_HEADERS,
        )
    finally:
        db.close()

# ─── DELETE /api/profiles/{id} ────────────────────────────────────────────────

@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: str = Path(...)):
    db = SessionLocal()
    try:
        p = db.query(Profile).filter(Profile.id == profile_id).first()
        if not p:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Profile not found"},
                headers=CORS_HEADERS,
            )
        db.delete(p)
        db.commit()
        return Response(status_code=204, headers=dict(CORS_HEADERS))
    finally:
        db.close()
