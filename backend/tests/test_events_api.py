"""Tests for ``GET /api/events`` (audit log endpoint).

Mirrors the flat-fixture pattern from the rest of the Phase 1 test suite:
in-memory SQLite, ``get_current_user`` overridden, no external deps.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.events import router as events_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.core.deps import get_current_user
from app.models import User
from app.models.event import Event

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email=ADMIN_EMAIL,
        admin_password=ADMIN_PASSWORD,
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key",
        public_base_url="https://lab.example.test",
        _env_file=None,
    )


@pytest.fixture
def db_session() -> Iterator[OrmSession]:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def fake_user(db_session: OrmSession) -> User:
    user = User(
        email=ADMIN_EMAIL,
        password_hash="irrelevant",
        role="instructor",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def app_factory(
    db_session: OrmSession,
    settings: Settings,
    fake_user: User,
):
    def _build(authenticated: bool = True) -> FastAPI:
        app = FastAPI()
        app.include_router(events_router)

        def _override_get_db() -> Iterator[OrmSession]:
            yield db_session

        def _override_get_settings() -> Settings:
            return settings

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_settings] = _override_get_settings
        if authenticated:
            app.dependency_overrides[get_current_user] = lambda: fake_user
        return app

    return _build


@pytest.fixture
def client(app_factory) -> Iterator[TestClient]:
    with TestClient(app_factory(authenticated=True)) as tc:
        yield tc


@pytest.fixture
def anon_client(app_factory) -> Iterator[TestClient]:
    with TestClient(app_factory(authenticated=False)) as tc:
        yield tc


def _seed_events(db: OrmSession, count: int, session_id: int | None = 1) -> list[Event]:
    events = []
    for i in range(count):
        ev = Event(
            session_id=session_id,
            student_id=None,
            action=f"test.action.{i}",
            details_json={"index": i},
        )
        db.add(ev)
        events.append(ev)
    db.commit()
    for ev in events:
        db.refresh(ev)
    return events


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_list_events_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/events")
    assert resp.status_code == 401


def test_list_events_empty_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_events_returns_seeded_events(client: TestClient, db_session: OrmSession) -> None:
    _seed_events(db_session, 3)
    resp = client.get("/api/events")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    # Newest first (reverse chronological)
    assert body[0]["action"] == "test.action.2"
    assert body[2]["action"] == "test.action.0"


def test_list_events_filter_by_session_id(client: TestClient, db_session: OrmSession) -> None:
    _seed_events(db_session, 2, session_id=1)
    _seed_events(db_session, 3, session_id=2)
    resp = client.get("/api/events?session_id=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert all(ev["session_id"] == 2 for ev in body)


def test_list_events_respects_limit(client: TestClient, db_session: OrmSession) -> None:
    _seed_events(db_session, 10)
    resp = client.get("/api/events?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_list_events_respects_offset(client: TestClient, db_session: OrmSession) -> None:
    _seed_events(db_session, 5)
    resp = client.get("/api/events?offset=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_events_includes_details_json(client: TestClient, db_session: OrmSession) -> None:
    _seed_events(db_session, 1)
    resp = client.get("/api/events")
    body = resp.json()
    assert body[0]["details_json"] == {"index": 0}


def test_list_events_includes_expected_fields(client: TestClient, db_session: OrmSession) -> None:
    _seed_events(db_session, 1)
    resp = client.get("/api/events")
    ev = resp.json()[0]
    assert "id" in ev
    assert "session_id" in ev
    assert "student_id" in ev
    assert "action" in ev
    assert "details_json" in ev
    assert "created_at" in ev
