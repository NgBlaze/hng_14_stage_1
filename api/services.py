import httpx
import asyncio
from datetime import datetime, timezone
from typing import Optional

from api.database import SessionLocal
from api.models import Profile, row_to_dict
from api.utils import generate_uuid7, classify_age, COUNTRY_NAMES
from api.nlp import parse_query


# ─── Validation constants ─────────────────────────────────────────────────────

VALID_GENDERS = {"male", "female"}
VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}
VALID_SORT_FIELDS = {"age", "created_at", "gender_probability"}
VALID_ORDERS = {"asc", "desc"}
SORT_COL_MAP = {
    "age": Profile.age,
    "created_at": Profile.created_at,
    "gender_probability": Profile.gender_probability,
}


# ─── Create profile via external APIs ─────────────────────────────────────────

async def create_profile_from_name(name: str) -> dict:
    """
    Fetch demographic data from external APIs and create a profile.
    Returns a dict: {"status_code": int, "body": dict}
    """
    name = name.strip().lower()

    # Check for existing profile
    db = SessionLocal()
    try:
        existing = db.query(Profile).filter(Profile.name == name).first()
        if existing:
            return {
                "status_code": 200,
                "body": {"status": "success", "message": "Profile already exists", "data": row_to_dict(existing)},
            }
    finally:
        db.close()

    # Fetch from external APIs
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

    api_names = ["Genderize", "Agify", "Nationalize"]
    for api_name, result in zip(api_names, results):
        if isinstance(result, Exception):
            return {
                "status_code": 502,
                "body": {"status": "error", "message": f"{api_name} returned an invalid response"},
            }

    gender_data, age_data, nation_data = results

    if not gender_data.get("gender") or gender_data.get("count", 0) == 0:
        return {
            "status_code": 502,
            "body": {"status": "error", "message": "Genderize returned an invalid response"},
        }
    if age_data.get("age") is None:
        return {
            "status_code": 502,
            "body": {"status": "error", "message": "Agify returned an invalid response"},
        }
    countries = nation_data.get("country", [])
    if not countries:
        return {
            "status_code": 502,
            "body": {"status": "error", "message": "Nationalize returned an invalid response"},
        }

    top_country = max(countries, key=lambda c: c.get("probability", 0))
    cid = top_country["country_id"]
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
            country_id=cid,
            country_name=COUNTRY_NAMES.get(cid),
            country_probability=top_country.get("probability", 0.0),
            created_at=now,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return {
            "status_code": 201,
            "body": {"status": "success", "data": row_to_dict(profile)},
        }
    except Exception:
        db.rollback()
        existing = db.query(Profile).filter(Profile.name == name).first()
        if existing:
            return {
                "status_code": 200,
                "body": {"status": "success", "message": "Profile already exists", "data": row_to_dict(existing)},
            }
        return {
            "status_code": 500,
            "body": {"status": "error", "message": "Internal server error"},
        }
    finally:
        db.close()


# ─── List profiles with filters, sorting, pagination ──────────────────────────

def list_profiles(
    *,
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    country_id: Optional[str] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    min_gender_probability: Optional[float] = None,
    min_country_probability: Optional[float] = None,
    sort_by: Optional[str] = None,
    order: str = "asc",
    page: int = 1,
    limit: int = 10,
) -> dict:
    """
    Returns {"status_code": int, "body": dict}
    """
    # Validation
    if gender is not None and gender.lower() not in VALID_GENDERS:
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if age_group is not None and age_group.lower() not in VALID_AGE_GROUPS:
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if sort_by is not None and sort_by.lower() not in VALID_SORT_FIELDS:
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if order.lower() not in VALID_ORDERS:
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if min_age is not None and min_age < 0:
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if max_age is not None and max_age < 0:
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if min_age is not None and max_age is not None and min_age > max_age:
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if min_gender_probability is not None and not (0.0 <= min_gender_probability <= 1.0):
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    if min_country_probability is not None and not (0.0 <= min_country_probability <= 1.0):
        return {"status_code": 422, "body": {"status": "error", "message": "Invalid query parameters"}}
    page = max(1, page)
    limit = max(1, min(limit, 100_000))

    db = SessionLocal()
    try:
        q = db.query(Profile)

        if gender:
            q = q.filter(Profile.gender == gender.lower())
        if age_group:
            q = q.filter(Profile.age_group == age_group.lower())
        if country_id:
            q = q.filter(Profile.country_id == country_id.upper())
        if min_age is not None:
            q = q.filter(Profile.age >= min_age)
        if max_age is not None:
            q = q.filter(Profile.age <= max_age)
        if min_gender_probability is not None:
            q = q.filter(Profile.gender_probability >= min_gender_probability)
        if min_country_probability is not None:
            q = q.filter(Profile.country_probability >= min_country_probability)

        total = q.count()

        if sort_by:
            col = SORT_COL_MAP[sort_by.lower()]
            q = q.order_by(col.asc() if order.lower() == "asc" else col.desc())

        offset = (page - 1) * limit
        profiles = q.offset(offset).limit(limit).all()

        return {
            "status_code": 200,
            "body": {
                "status": "success",
                "page": page,
                "limit": limit,
                "total": total,
                "data": [row_to_dict(p) for p in profiles],
            },
        }
    finally:
        db.close()


# ─── Natural language search ──────────────────────────────────────────────────

def search_profiles(q: str, page: int = 1, limit: int = 10) -> dict:
    """
    Returns {"status_code": int, "body": dict}
    """
    filters = parse_query(q)
    if filters is None:
        return {
            "status_code": 422,
            "body": {"status": "error", "message": "Unable to interpret query"},
        }

    db = SessionLocal()
    try:
        query = db.query(Profile)
        if "gender" in filters:
            query = query.filter(Profile.gender == filters["gender"])
        if "age_group" in filters:
            query = query.filter(Profile.age_group == filters["age_group"])
        if "country_id" in filters:
            query = query.filter(Profile.country_id == filters["country_id"])
        if "min_age" in filters:
            query = query.filter(Profile.age >= filters["min_age"])
        if "max_age" in filters:
            query = query.filter(Profile.age <= filters["max_age"])

        total = query.count()
        offset = (page - 1) * limit
        profiles = query.offset(offset).limit(limit).all()

        return {
            "status_code": 200,
            "body": {
                "status": "success",
                "page": page,
                "limit": limit,
                "total": total,
                "data": [row_to_dict(p) for p in profiles],
            },
        }
    finally:
        db.close()


# ─── Get single profile ───────────────────────────────────────────────────────

def get_profile_by_id(profile_id: str) -> dict:
    db = SessionLocal()
    try:
        p = db.query(Profile).filter(Profile.id == profile_id).first()
        if not p:
            return {
                "status_code": 404,
                "body": {"status": "error", "message": "Profile not found"},
            }
        return {
            "status_code": 200,
            "body": {"status": "success", "data": row_to_dict(p)},
        }
    finally:
        db.close()


# ─── Delete profile ───────────────────────────────────────────────────────────

def delete_profile_by_id(profile_id: str) -> dict:
    db = SessionLocal()
    try:
        p = db.query(Profile).filter(Profile.id == profile_id).first()
        if not p:
            return {
                "status_code": 404,
                "body": {"status": "error", "message": "Profile not found"},
            }
        db.delete(p)
        db.commit()
        return {"status_code": 204, "body": None}
    finally:
        db.close()
