from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from api.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    gender = Column(String, index=True)
    gender_probability = Column(Float)
    sample_size = Column(Integer)
    age = Column(Integer, index=True)
    age_group = Column(String, index=True)
    country_id = Column(String, index=True)
    country_name = Column(String)
    country_probability = Column(Float)
    created_at = Column(String, index=True)


def row_to_dict(p: Profile) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "gender": p.gender,
        "gender_probability": p.gender_probability,
        "age": p.age,
        "age_group": p.age_group,
        "country_id": p.country_id,
        "country_name": p.country_name,
        "country_probability": p.country_probability,
        "created_at": p.created_at,
    }


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    github_id = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, nullable=False)
    email = Column(String)
    avatar_url = Column(String)
    role = Column(String, default="analyst", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id = Column(String, primary_key=True)
    state = Column(String, unique=True, nullable=False, index=True)
    code_challenge = Column(String)
    code_verifier = Column(String)
    cli_port = Column(Integer)
    source = Column(String, nullable=False)  # 'web' or 'cli'
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
