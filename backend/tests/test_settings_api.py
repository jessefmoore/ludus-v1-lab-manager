"""Tests for the /api/settings endpoints (view, test-ludus, change-password)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.settings import router as settings_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.core.deps import get_current_user, get_ludus_client
from app.core.security import hash_password, verify_password
from app.models.event import Event
from app.models.user import User
from app.services.exceptions import LudusError
from app.services.ludus import LudusClient


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email="instructor@example.com",
        admin_password="super-secret-test-pw",
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key-abcd",
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
def fake_admin(db_session: OrmSession) -> User:
    user = User(
        email="instructor@example.com",
        password_hash=hash_password("old-password-1234"),
        role="instructor",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def mock_ludus() -> MagicMock:
    return MagicMock(spec=LudusClient)


def _build_app(
    db_session: OrmSession,
    settings: Settings,
    mock_ludus: MagicMock,
    current_user: User | None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(settings_router)

    def _override_get_db() -> Iterator[OrmSession]:
        yield db_session

    def _override_get_settings() -> Settings:
        return settings

    def _override_get_ludus_client() -> MagicMock:
        return mock_ludus

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = _override_get_settings
    app.dependency_overrides[get_ludus_client] = _override_get_ludus_client

    if current_user is not None:

        def _override_get_current_user() -> User:
            return current_user

        app.dependency_overrides[get_current_user] = _override_get_current_user

    return app


@pytest.fixture
def client(
    db_session: OrmSession,
    settings: Settings,
    mock_ludus: MagicMock,
    fake_admin: User,
) -> Iterator[TestClient]:
    app = _build_app(db_session, settings, mock_ludus, fake_admin)
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def anon_client(
    db_session: OrmSession,
    settings: Settings,
    mock_ludus: MagicMock,
) -> Iterator[TestClient]:
    app = _build_app(db_session, settings, mock_ludus, current_user=None)
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------


def test_get_settings_returns_masked_key(client: TestClient) -> None:
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ludus_server_url"] == "https://ludus.test:8080"
    assert body["ludus_api_key_masked"] == "****...abcd"
    assert body["ludus_verify_tls"] is False
    assert body["admin_email"] == "instructor@example.com"
    assert body["invite_token_ttl_hours"] == 168
    assert body["public_base_url"] == "http://localhost:8000"


def test_get_settings_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/settings")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/settings/test-ludus
# ---------------------------------------------------------------------------


def test_test_ludus_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_list.return_value = []

    resp = client.post("/api/settings/test-ludus")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0


def test_test_ludus_failure_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_list.side_effect = LudusError("connection refused", status_code=503)

    resp = client.post("/api/settings/test-ludus")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/settings/change-password
# ---------------------------------------------------------------------------


def test_change_password_success(
    client: TestClient, fake_admin: User, db_session: OrmSession
) -> None:
    resp = client.post(
        "/api/settings/change-password",
        json={"current_password": "old-password-1234", "new_password": "new-password-5678"},
    )
    assert resp.status_code == 204

    # Verify old password no longer works and new one does.
    db_session.refresh(fake_admin)
    assert not verify_password("old-password-1234", fake_admin.password_hash)
    assert verify_password("new-password-5678", fake_admin.password_hash)


def test_change_password_wrong_current_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/api/settings/change-password",
        json={"current_password": "wrong-password", "new_password": "new-password-5678"},
    )
    assert resp.status_code == 401
    assert "incorrect" in resp.json()["detail"].lower()


def test_change_password_too_short_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/settings/change-password",
        json={"current_password": "old-password-1234", "new_password": "short"},
    )
    assert resp.status_code == 422


def test_change_password_emits_audit_event(
    client: TestClient, fake_admin: User, db_session: OrmSession
) -> None:
    client.post(
        "/api/settings/change-password",
        json={"current_password": "old-password-1234", "new_password": "new-password-5678"},
    )

    stmt = select(Event).where(Event.action == "admin.password_changed")
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].details_json["user_id"] == fake_admin.id
