import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL env var is required")
        _engine = create_engine(url)
        _SessionLocal = sessionmaker(bind=_engine)
    return _engine


def get_session() -> Session:
    _get_engine()
    return _SessionLocal()


def init_db():
    from .models import Base
    Base.metadata.create_all(bind=_get_engine())
