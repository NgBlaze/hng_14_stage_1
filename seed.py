#!/usr/bin/env python3
"""
Seed the database with 2026 generated profile records.
Re-running this script is safe — existing names are skipped.

Usage:
    python seed.py
"""

import os
import random
import time
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Float, Integer, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

load_dotenv()

# ─── DB setup (mirrors api/index.py) ─────────────────────────────────────────

_raw_url = os.environ.get("DATABASE_URL", "sqlite:////tmp/profiles.db")
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql://", 1)

if _raw_url.startswith("sqlite"):
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
        if _raw_url.startswith("sqlite"):
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


def _weighted_country() -> tuple[str, str]:
    population = [c for (cid, cname, w) in COUNTRIES for _ in range(w)]
    choice = random.choice(population)
    return choice[0], choice[1]


# ─── Build profile records ────────────────────────────────────────────────────

TARGET = 2026
rng = random.Random(42)  # fixed seed for reproducibility

# Generate name pools: first_name + " " + last_name
male_names: list[str] = []
for fn in MALE_FIRST_NAMES:
    for ln in LAST_NAMES:
        male_names.append(f"{fn} {ln}")

female_names: list[str] = []
for fn in FEMALE_FIRST_NAMES:
    for ln in LAST_NAMES:
        female_names.append(f"{fn} {ln}")

rng.shuffle(male_names)
rng.shuffle(female_names)

half = TARGET // 2
male_sample = male_names[:half]           # 1013
female_sample = female_names[:TARGET - half]  # 1013

# Base timestamp spread over ~2 years before today
_BASE_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)
_RANGE_DAYS = (datetime(2026, 4, 20, tzinfo=timezone.utc) - _BASE_TS).days


def _make_profile(name: str, gender: str) -> dict:
    # age distribution: child 5%, teenager 15%, adult 65%, senior 15%
    r = rng.random()
    if r < 0.05:
        age = rng.randint(1, 12)
    elif r < 0.20:
        age = rng.randint(13, 19)
    elif r < 0.85:
        age = rng.randint(20, 59)
    else:
        age = rng.randint(60, 85)

    cid, cname = rng.choice(
        [(c[0], c[1]) for c in COUNTRIES for _ in range(c[2])]
    )

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


records = (
    [_make_profile(n, "male") for n in male_sample]
    + [_make_profile(n, "female") for n in female_sample]
)
rng.shuffle(records)

# ─── Insert ───────────────────────────────────────────────────────────────────

db = SessionLocal()
try:
    existing_names: set[str] = {r[0] for r in db.query(Profile.name).all()}
    new_records = [r for r in records if r["name"] not in existing_names]

    if not new_records:
        print(f"Database already has {len(existing_names)} profiles — nothing to insert.")
    else:
        db.bulk_insert_mappings(Profile, new_records)
        db.commit()
        total = db.query(Profile).count()
        print(f"Inserted {len(new_records)} profiles. Total in DB: {total}")
finally:
    db.close()
