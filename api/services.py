import csv
import httpx
import io
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional, BinaryIO

from sqlalchemy.exc import IntegrityError

from api.cache import cache_get, cache_set, invalidate_profile_caches
from api.database import SessionLocal, engine
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
        try:
            db.commit()
        except IntegrityError:
            # Concurrent insert lost the race on the unique-name constraint —
            # fall back to the row the winner committed.
            db.rollback()
            existing = db.query(Profile).filter(Profile.name == name).first()
            if existing:
                return {
                    "status_code": 200,
                    "body": {"status": "success", "message": "Profile already exists", "data": row_to_dict(existing)},
                }
            raise
        db.refresh(profile)
        invalidate_profile_caches()
        return {
            "status_code": 201,
            "body": {"status": "success", "data": row_to_dict(profile)},
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

    cache_key = (
        "profiles:list:"
        f"{gender}:{age_group}:{country_id}:{min_age}:{max_age}:"
        f"{min_gender_probability}:{min_country_probability}:"
        f"{sort_by}:{order}:{page}:{limit}"
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return {"status_code": 200, "body": cached}

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

        body = {
            "status": "success",
            "page": page,
            "limit": limit,
            "total": total,
            "data": [row_to_dict(p) for p in profiles],
        }
        cache_set(cache_key, body, ttl=60)
        return {"status_code": 200, "body": body}
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

    cache_key = f"profiles:search:{q.strip().lower()}:{page}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return {"status_code": 200, "body": cached}

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

        body = {
            "status": "success",
            "page": page,
            "limit": limit,
            "total": total,
            "data": [row_to_dict(p) for p in profiles],
        }
        cache_set(cache_key, body, ttl=60)
        return {"status_code": 200, "body": body}
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
        invalidate_profile_caches()
        return {"status_code": 204, "body": None}
    finally:
        db.close()


# ─── CSV bulk ingestion ───────────────────────────────────────────────────────

_CSV_REQUIRED = ("name", "gender", "age", "country_id")
_CSV_OPTIONAL = (
    "gender_probability", "sample_size", "age_group",
    "country_name", "country_probability", "created_at",
)
_CSV_COLUMNS = (
    "id", "name", "gender", "gender_probability", "sample_size",
    "age", "age_group", "country_id", "country_name",
    "country_probability", "created_at",
)
_CSV_BATCH_SIZE = 1000


def _validate_row(raw: dict) -> tuple[Optional[dict], Optional[str]]:
    """Return (clean_dict, None) or (None, reason). reason categorises skips."""
    try:
        name = (raw.get("name") or "").strip().lower()
        if not name:
            return None, "missing_required"

        gender = (raw.get("gender") or "").strip().lower()
        if gender not in VALID_GENDERS:
            return None, "invalid_value"

        age_str = (raw.get("age") or "").strip()
        if not age_str:
            return None, "missing_required"
        age = int(age_str)
        if age < 0 or age > 150:
            return None, "invalid_value"

        country_id = (raw.get("country_id") or "").strip().upper()
        if len(country_id) != 2 or not country_id.isalpha():
            return None, "invalid_value"

        # Optional fields with safe defaults
        age_group = (raw.get("age_group") or "").strip().lower() or classify_age(age)
        if age_group not in VALID_AGE_GROUPS:
            return None, "invalid_value"

        def _opt_float(key: str, default: float) -> float:
            v = (raw.get(key) or "").strip()
            if not v:
                return default
            f = float(v)
            if not (0.0 <= f <= 1.0):
                raise ValueError
            return f

        gender_prob = _opt_float("gender_probability", 0.0)
        country_prob = _opt_float("country_probability", 0.0)

        sample_str = (raw.get("sample_size") or "").strip()
        sample_size = int(sample_str) if sample_str else 0
        if sample_size < 0:
            return None, "invalid_value"

        country_name = (raw.get("country_name") or "").strip() or COUNTRY_NAMES.get(country_id)
        created_at = (raw.get("created_at") or "").strip() or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "id": generate_uuid7(),
            "name": name,
            "gender": gender,
            "gender_probability": gender_prob,
            "sample_size": sample_size,
            "age": age,
            "age_group": age_group,
            "country_id": country_id,
            "country_name": country_name,
            "country_probability": country_prob,
            "created_at": created_at,
        }, None
    except (ValueError, TypeError):
        return None, "invalid_value"


def _flush_batch_postgres(cur, batch: list[dict]) -> int:
    """Insert batch via execute_values + ON CONFLICT. Returns rows actually inserted."""
    from psycopg2.extras import execute_values
    sql = (
        f"INSERT INTO profiles ({', '.join(_CSV_COLUMNS)}) VALUES %s "
        "ON CONFLICT (name) DO NOTHING"
    )
    rows = [tuple(r[c] for c in _CSV_COLUMNS) for r in batch]
    execute_values(cur, sql, rows, page_size=len(rows))
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def _flush_batch_sqlite(db, batch: list[dict]) -> int:
    """Dev path: dedupe against existing names then bulk insert."""
    names = [r["name"] for r in batch]
    existing = {
        n for (n,) in db.query(Profile.name).filter(Profile.name.in_(names)).all()
    }
    new_rows = [r for r in batch if r["name"] not in existing]
    if new_rows:
        db.bulk_insert_mappings(Profile, new_rows)
        db.commit()
    return len(new_rows)


def upload_profiles_csv(file_stream: BinaryIO) -> dict:
    """
    Stream-parse a CSV upload, batch-insert valid rows, return a summary.

    The whole file is never held in memory: csv.DictReader pulls one logical
    record at a time from the underlying SpooledTemporaryFile, and rows are
    flushed every _CSV_BATCH_SIZE. Batches commit independently so a partial
    failure mid-stream still keeps the rows already inserted.
    """
    counters = {
        "received": 0,
        "inserted": 0,
        "skipped_missing_required": 0,
        "skipped_invalid_value": 0,
        "skipped_duplicate_in_batch": 0,
        "skipped_duplicate_in_db": 0,
        "skipped_malformed": 0,
    }
    t0 = time.time()

    # Decode bytes → text, replace bad UTF-8 (counts as malformed via row check)
    try:
        text_stream = io.TextIOWrapper(file_stream, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text_stream)
    except Exception:
        return {
            "status_code": 400,
            "body": {"status": "error", "message": "Could not parse CSV"},
        }

    if not reader.fieldnames:
        return {
            "status_code": 400,
            "body": {"status": "error", "message": "Empty CSV (no header)"},
        }
    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = [c for c in _CSV_REQUIRED if c not in headers]
    if missing:
        return {
            "status_code": 400,
            "body": {
                "status": "error",
                "message": f"CSV missing required columns: {missing}",
            },
        }

    is_postgres = engine.dialect.name != "sqlite"
    raw_conn = engine.raw_connection() if is_postgres else None
    db = SessionLocal() if not is_postgres else None
    cur = raw_conn.cursor() if is_postgres else None

    batch: list[dict] = []
    seen_in_batch: set[str] = set()

    def _flush() -> None:
        if not batch:
            return
        if is_postgres:
            inserted = _flush_batch_postgres(cur, batch)
            raw_conn.commit()
        else:
            inserted = _flush_batch_sqlite(db, batch)
        counters["inserted"] += inserted
        # Anything not inserted that was sent to the DB is a duplicate-in-DB
        counters["skipped_duplicate_in_db"] += len(batch) - inserted
        batch.clear()
        seen_in_batch.clear()

    try:
        for raw in reader:
            counters["received"] += 1
            # csv.DictReader sets None for short rows and puts excess columns
            # under a `None` key. Treat both as malformed.
            if None in raw.values() or None in raw.keys():
                counters["skipped_malformed"] += 1
                continue

            clean, reason = _validate_row(raw)
            if clean is None:
                if reason == "missing_required":
                    counters["skipped_missing_required"] += 1
                else:
                    counters["skipped_invalid_value"] += 1
                continue

            if clean["name"] in seen_in_batch:
                counters["skipped_duplicate_in_batch"] += 1
                continue
            seen_in_batch.add(clean["name"])
            batch.append(clean)

            if len(batch) >= _CSV_BATCH_SIZE:
                _flush()
        _flush()
    finally:
        if cur is not None:
            cur.close()
        if raw_conn is not None:
            raw_conn.close()
        if db is not None:
            db.close()

    if counters["inserted"]:
        invalidate_profile_caches()

    return {
        "status_code": 200,
        "body": {
            "status": "success",
            "summary": counters,
            "elapsed_seconds": round(time.time() - t0, 2),
        },
    }
