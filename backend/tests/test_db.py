"""Smoke tests for app.core.db (engine, session, Base, get_db)."""

import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings


def _apply_required_env(
    monkeypatch: pytest.MonkeyPatch,
    db_url: str,
) -> None:
    """Set all env vars required to construct Settings plus a custom database_url."""
    monkeypatch.setenv("APP_SECRET_KEY", "unit-test-secret")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "unit-test-password")
    monkeypatch.setenv("LUDUS_DEFAULT_URL", "https://ludus.test:8080")
    monkeypatch.setenv("LUDUS_DEFAULT_API_KEY", "unit-test-api-key")
    monkeypatch.setenv("DATABASE_URL", db_url)


def _reload_db_module():
    """Force reload of app.core.db so it picks up fresh settings at import time."""
    get_settings.cache_clear()
    if "app.core.db" in sys.modules:
        return importlib.reload(sys.modules["app.core.db"])
    return importlib.import_module("app.core.db")


def test_import_creates_parent_dir_for_sqlite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Importing app.core.db creates the sqlite parent directory if missing."""
    db_dir = tmp_path / "nested" / "subdir"
    db_file = db_dir / "test.db"
    assert not db_dir.exists()

    _apply_required_env(monkeypatch, f"sqlite:///{db_file}")

    try:
        _reload_db_module()
        assert db_dir.is_dir(), "parent directory should be created on import"
    finally:
        get_settings.cache_clear()


def test_session_can_execute_select_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SessionLocal opens a working session that can execute SELECT 1."""
    db_file = tmp_path / "data" / "insec.db"
    _apply_required_env(monkeypatch, f"sqlite:///{db_file}")

    try:
        db_module = _reload_db_module()
        session = db_module.SessionLocal()
        try:
            result = session.execute(text("SELECT 1")).scalar_one()
            assert result == 1
        finally:
            session.close()
        assert db_file.parent.is_dir()
    finally:
        get_settings.cache_clear()


def test_get_db_yields_session_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """get_db() yields a Session and closes it when the generator is exhausted."""
    db_file = tmp_path / "data" / "insec.db"
    _apply_required_env(monkeypatch, f"sqlite:///{db_file}")

    try:
        db_module = _reload_db_module()
        gen = db_module.get_db()
        session = next(gen)
        assert isinstance(session, Session)
        # SELECT 1 works while the dependency is live.
        assert session.execute(text("SELECT 1")).scalar_one() == 1

        # Exhaust the generator to trigger the finally branch.
        with pytest.raises(StopIteration):
            next(gen)

        # After close, the session's connection should be released.
        # SQLAlchemy marks a closed Session by clearing its identity map; the cleanest
        # signal is that a fresh query opens a new connection without error.
        # We assert the session object has no active transaction.
        assert not session.in_transaction()
    finally:
        get_settings.cache_clear()


def test_base_is_declarative(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Base is a SQLAlchemy DeclarativeBase subclass with a metadata registry."""
    db_file = tmp_path / "data" / "insec.db"
    _apply_required_env(monkeypatch, f"sqlite:///{db_file}")

    try:
        db_module = _reload_db_module()
        assert hasattr(db_module.Base, "metadata")
        assert hasattr(db_module.Base, "registry")
    finally:
        get_settings.cache_clear()
