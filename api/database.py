import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

load_dotenv()

_raw_url = os.environ.get("DATABASE_URL", "sqlite:////tmp/profiles.db")
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


def init_db():
    """Create tables and run migrations."""
    from api.models import Profile  # noqa: F811 — ensure model is registered

    Base.metadata.create_all(bind=engine)

    # Migrate: add country_name column if missing, add indexes
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
            pass  # column already exists

        indexes = [
            "CREATE INDEX IF NOT EXISTS ix_profiles_gender ON profiles (gender)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_age ON profiles (age)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_age_group ON profiles (age_group)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_country_id ON profiles (country_id)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_created_at ON profiles (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_gender_prob ON profiles (gender_probability)",
        ]
        for stmt in indexes:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass
