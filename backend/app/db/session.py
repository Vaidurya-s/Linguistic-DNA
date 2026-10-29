from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def make_engine(url: str | None = None):
    return create_engine(url or settings.database_url, pool_pre_ping=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
