from sqlalchemy import Column, String, Float, Integer
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
