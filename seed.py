#!/usr/bin/env python3
"""
Seed the database with generated profile records.
Re-running this script is safe — existing names are skipped.

Usage:
    python seed.py                  # default: 2026 profiles (Stage 3 baseline)
    python seed.py --count 1000000  # Stage 4B baseline (1M+ rows)
"""

import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Iterable, Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Float, Integer, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

load_dotenv()

# ─── DB setup (mirrors api/index.py) ─────────────────────────────────────────

_raw_url = os.environ.get("DATABASE_URL", "sqlite:////tmp/profiles.db")
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql://", 1)

IS_SQLITE = _raw_url.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(
        _raw_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
else:
    engine = create_engine(_raw_url, poolclass=NullPool, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    gender = Column(String)
    gender_probability = Column(Float)
    sample_size = Column(Integer)
    age = Column(Integer)
    age_group = Column(String)
    country_id = Column(String)
    country_name = Column(String)
    country_probability = Column(Float)
    created_at = Column(String)


Base.metadata.create_all(bind=engine)

# ensure country_name column exists
with engine.connect() as conn:
    try:
        if IS_SQLITE:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN country_name VARCHAR"))
        else:
            conn.execute(text(
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS country_name VARCHAR"
            ))
        conn.commit()
    except Exception:
        pass

# ─── Data tables ──────────────────────────────────────────────────────────────

MALE_FIRST_NAMES = [
    "emmanuel", "david", "john", "michael", "james", "robert", "william", "joseph",
    "charles", "george", "ahmed", "ali", "omar", "hassan", "ibrahim", "samuel",
    "daniel", "benjamin", "joshua", "andrew", "peter", "paul", "mark", "matthew",
    "thomas", "jacob", "noah", "henry", "oliver", "emeka", "chidi", "tunde",
    "seun", "femi", "kwame", "kofi", "yusuf", "kingsley", "gabriel", "raphael",
    "ismail", "hamid", "abel", "caleb", "elijah", "ezra", "felix", "moses",
    "aaron", "isaac", "elias", "simon", "levi", "victor", "raymond", "clinton",
    "dominic", "stanley", "clarence", "reginald", "cornelius", "ambrose",
    "desmond", "edgar", "ferdinand", "gilbert", "horace", "ignatius", "jerome",
    "lambert", "norbert", "patrick", "quentin", "rupert", "sylvester", "thaddeus",
    "ulrich", "virgil", "walter", "xavier", "zachary", "alvin", "barnabas",
    "celestine", "donatus", "ephraim", "florian", "godwin", "humphrey", "innocent",
    "jeremiah", "kenneth", "lawrence", "maxwell", "nathaniel", "octavius",
]

FEMALE_FIRST_NAMES = [
    "mary", "sarah", "grace", "joy", "faith", "hope", "peace", "mercy",
    "blessing", "amara", "chioma", "adaeze", "fatima", "aisha", "zainab",
    "halima", "aminata", "mariam", "nadia", "diana", "jennifer", "jessica",
    "michelle", "angela", "ngozi", "adeola", "funke", "bisi", "toyin",
    "akosua", "abena", "efua", "ama", "adwoa", "sophia", "elena", "maria",
    "ana", "isabela", "carolina", "valentina", "adriana", "lucia", "priya",
    "anita", "kavita", "sunita", "rekha", "sade", "yetunde", "kemi", "bola",
    "titi", "lola", "yemi", "folake", "ronke", "wunmi", "bunmi", "dupe",
    "iyabo", "omowunmi", "adunola", "titilayo", "abimbola", "oluwakemi",
    "chidinma", "chinwe", "adanna", "obiageli", "nkechi", "uloma", "uche",
    "adaora", "ogechukwu", "nneka", "ifunanya", "chinyere", "amarachi",
    "ebunoluwa", "tolulope", "taiwo", "kehinde", "omolara", "modupe",
    "funmilayo", "sekinat", "ramat", "jumoke", "titilope", "belinda",
    "constance", "dorothy", "eunice", "florence", "gladys", "harriet",
    "irene", "josephine", "kathleen", "leticia",
]

LAST_NAMES = [
    "okonkwo", "adeyemi", "ibrahim", "hassan", "ali", "osei", "mensah",
    "nkrumah", "diallo", "toure", "kamara", "keita", "coulibaly", "traore",
    "ndiaye", "fall", "ba", "sow", "mwangi", "kamau", "odhiambo", "otieno",
    "chukwu", "eze", "obi", "nwachukwu", "abiodun", "olawale", "adeleke",
    "mwamba", "banda", "phiri", "tembo", "mutale", "dlamini", "ndlovu",
    "moyo", "ncube", "zimba", "achebe",
]

# (country_id, country_name, weight) — heavier weight = more profiles
COUNTRIES = [
    ("NG", "Nigeria", 18),
    ("KE", "Kenya", 12),
    ("GH", "Ghana", 12),
    ("ZA", "South Africa", 10),
    ("ET", "Ethiopia", 8),
    ("TZ", "Tanzania", 7),
    ("UG", "Uganda", 7),
    ("SN", "Senegal", 6),
    ("CI", "Ivory Coast", 6),
    ("CM", "Cameroon", 6),
    ("AO", "Angola", 5),
    ("BJ", "Benin", 5),
    ("RW", "Rwanda", 5),
    ("ZM", "Zambia", 4),
    ("MW", "Malawi", 4),
    ("MZ", "Mozambique", 3),
    ("ZW", "Zimbabwe", 3),
    ("SD", "Sudan", 3),
    ("EG", "Egypt", 3),
    ("MA", "Morocco", 3),
    ("ML", "Mali", 2),
    ("NE", "Niger", 2),
    ("TD", "Chad", 2),
    ("TG", "Togo", 2),
    ("GN", "Guinea", 2),
    ("LR", "Liberia", 2),
    ("US", "United States", 8),
    ("GB", "United Kingdom", 5),
    ("FR", "France", 4),
    ("IN", "India", 5),
    ("BR", "Brazil", 3),
    ("DE", "Germany", 2),
    ("CA", "Canada", 2),
    ("CN", "China", 2),
    ("SA", "Saudi Arabia", 2),
    ("AE", "United Arab Emirates", 2),
]

COLUMNS = (
    "id", "name", "gender", "gender_probability", "sample_size",
    "age", "age_group", "country_id", "country_name",
    "country_probability", "created_at",
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _uuid7() -> str:
    ts_ms = int(time.time() * 1000)
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)
    high = (ts_ms << 16) | (0x7 << 12) | rand_a
    low = (0b10 << 62) | rand_b
    hi = high.to_bytes(8, "big")
    lo = low.to_bytes(8, "big")
    return (
        f"{hi[0:4].hex()}-{hi[4:6].hex()}-{hi[6:8].hex()}"
        f"-{lo[0:2].hex()}-{lo[2:8].hex()}"
    )


def _classify_age(age: int) -> str:
    if age <= 12:
        return "child"
    if age <= 19:
        return "teenager"
    if age <= 59:
        return "adult"
    return "senior"


# Pre-expanded country population for O(1) weighted choice — built once.
_COUNTRY_POP = [(c[0], c[1]) for c in COUNTRIES for _ in range(c[2])]


# ─── Name pool & generator ────────────────────────────────────────────────────

_BASE_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)
_RANGE_DAYS = (datetime(2026, 4, 20, tzinfo=timezone.utc) - _BASE_TS).days


def _build_name_pools(rng: random.Random) -> tuple[list[str], list[str]]:
    """Cartesian product of first × last, shuffled deterministically."""
    male = [f"{fn} {ln}" for fn in MALE_FIRST_NAMES for ln in LAST_NAMES]
    female = [f"{fn} {ln}" for fn in FEMALE_FIRST_NAMES for ln in LAST_NAMES]
    rng.shuffle(male)
    rng.shuffle(female)
    return male, female


def _gen_profile(rng: random.Random, name: str, gender: str) -> dict:
    r = rng.random()
    if r < 0.05:
        age = rng.randint(1, 12)
    elif r < 0.20:
        age = rng.randint(13, 19)
    elif r < 0.85:
        age = rng.randint(20, 59)
    else:
        age = rng.randint(60, 85)

    cid, cname = rng.choice(_COUNTRY_POP)

    created_delta = timedelta(
        days=rng.randint(0, _RANGE_DAYS),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
        seconds=rng.randint(0, 59),
    )
    created_at = (_BASE_TS + created_delta).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "id": _uuid7(),
        "name": name,
        "gender": gender,
        "gender_probability": round(rng.uniform(0.55, 0.99), 2),
        "sample_size": rng.randint(100, 50000),
        "age": age,
        "age_group": _classify_age(age),
        "country_id": cid,
        "country_name": cname,
        "country_probability": round(rng.uniform(0.05, 0.90), 2),
        "created_at": created_at,
    }


def _iter_records(count: int, rng: random.Random) -> Iterator[dict]:
    """
    Yield `count` profile dicts.

    For count <= len(pool), behavior matches the original script exactly:
    half male, half female, shuffled. For count > len(pool), the pool is
    cycled and a numeric suffix is appended to keep names unique
    (e.g. "emmanuel okonkwo 1").
    """
    male_pool, female_pool = _build_name_pools(rng)
    half = count // 2
    male_target = half
    female_target = count - half

    def _stream(pool: list[str], target: int, gender: str) -> Iterator[dict]:
        pool_size = len(pool)
        for i in range(target):
            base = pool[i % pool_size]
            cycle = i // pool_size
            name = base if cycle == 0 else f"{base} {cycle}"
            yield _gen_profile(rng, name, gender)

    # Interleave to keep the original's "shuffled" feel without holding
    # the whole list in memory. Drains males then females; for the default
    # 2026 path we additionally shuffle to preserve byte-for-byte parity.
    if count <= len(male_pool) + len(female_pool):
        records = (
            list(_stream(male_pool, male_target, "male"))
            + list(_stream(female_pool, female_target, "female"))
        )
        rng.shuffle(records)
        yield from records
    else:
        # Large mode: stream without materializing the full list.
        yield from _stream(male_pool, male_target, "male")
        yield from _stream(female_pool, female_target, "female")


def _batched(it: Iterable[dict], size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for item in it:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# ─── Insert paths ─────────────────────────────────────────────────────────────

def _insert_postgres(batches: Iterable[list[dict]]) -> tuple[int, int]:
    """Fast path: psycopg2 execute_values + ON CONFLICT DO NOTHING."""
    from psycopg2.extras import execute_values

    raw = engine.raw_connection()
    inserted = 0
    seen = 0
    sql = (
        f"INSERT INTO profiles ({', '.join(COLUMNS)}) VALUES %s "
        "ON CONFLICT (name) DO NOTHING"
    )
    try:
        with raw.cursor() as cur:
            for batch in batches:
                rows = [tuple(r[c] for c in COLUMNS) for r in batch]
                execute_values(cur, sql, rows, page_size=len(rows))
                # rowcount reflects rows actually inserted (excludes conflicts)
                inserted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                seen += len(batch)
                raw.commit()
                print(f"  …processed {seen:>8} rows (inserted so far: {inserted})", flush=True)
    finally:
        raw.close()
    return inserted, seen


def _insert_sqlite(batches: Iterable[list[dict]]) -> tuple[int, int]:
    """Dev path: ORM bulk_insert_mappings, dedup against existing names per batch."""
    db = SessionLocal()
    inserted = 0
    seen = 0
    try:
        existing: set[str] = {r[0] for r in db.query(Profile.name).all()}
        for batch in batches:
            new_rows = [r for r in batch if r["name"] not in existing]
            if new_rows:
                db.bulk_insert_mappings(Profile, new_rows)
                db.commit()
                existing.update(r["name"] for r in new_rows)
                inserted += len(new_rows)
            seen += len(batch)
            print(f"  …processed {seen:>8} rows (inserted so far: {inserted})", flush=True)
    finally:
        db.close()
    return inserted, seen


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Seed profiles table.")
    parser.add_argument(
        "--count", type=int, default=2026,
        help="Number of profiles to generate (default: 2026)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5000,
        help="Insert batch size (default: 5000)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="RNG seed for deterministic output (default: 42)",
    )
    args = parser.parse_args()

    if args.count < 1:
        print("--count must be >= 1", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    pool_total = (len(MALE_FIRST_NAMES) + len(FEMALE_FIRST_NAMES)) * len(LAST_NAMES)

    print(
        f"Seeding {args.count} profiles "
        f"(pool size: {pool_total}, batch: {args.batch_size}, "
        f"backend: {'sqlite' if IS_SQLITE else 'postgres'})",
        flush=True,
    )
    if args.count > pool_total:
        print(
            f"  note: count exceeds name pool — names beyond {pool_total} "
            "will be suffixed (e.g. 'emmanuel okonkwo 1')",
            flush=True,
        )

    t0 = time.time()
    batches = _batched(_iter_records(args.count, rng), args.batch_size)
    if IS_SQLITE:
        inserted, seen = _insert_sqlite(batches)
    else:
        inserted, seen = _insert_postgres(batches)
    elapsed = time.time() - t0

    skipped = seen - inserted
    print(
        f"Done. Generated {seen}, inserted {inserted}, "
        f"skipped (duplicates) {skipped} in {elapsed:.1f}s.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
