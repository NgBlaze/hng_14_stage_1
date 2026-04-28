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
    from api.models import Profile, User, RefreshToken, OAuthState  # noqa — register all models

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        # profiles: add country_name if missing
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

        # oauth_states: add code_verifier if missing
        try:
            if _raw_url.startswith("sqlite"):
                conn.execute(text("ALTER TABLE oauth_states ADD COLUMN code_verifier VARCHAR"))
            else:
                conn.execute(text(
                    "ALTER TABLE oauth_states ADD COLUMN IF NOT EXISTS code_verifier VARCHAR"
                ))
            conn.commit()
        except Exception:
            pass

        # profiles: indexes
        for stmt in [
            "CREATE INDEX IF NOT EXISTS ix_profiles_gender ON profiles (gender)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_age ON profiles (age)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_age_group ON profiles (age_group)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_country_id ON profiles (country_id)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_created_at ON profiles (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_profiles_gender_prob ON profiles (gender_probability)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass
