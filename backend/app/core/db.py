"""SQLAlchemy engine, declarative Base, and FastAPI session dependency."""

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


_settings = get_settings()

# For sqlite, ensure the parent dir exists before the engine touches the file.
if _settings.database_url.startswith("sqlite"):
    db_path = _settings.database_url.replace("sqlite:///", "", 1)
    parent = Path(db_path).parent
    if str(parent) and parent != Path("."):
        os.makedirs(parent, exist_ok=True)

connect_args = (
    {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    _settings.database_url,
    connect_args=connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a Session, ensure close on request end."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
