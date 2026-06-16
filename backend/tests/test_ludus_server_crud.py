"""Tests for Ludus server CRUD endpoints (POST/PUT/DELETE /api/settings/ludus-servers)."""

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
from app.core.deps import (
    LudusClientRegistry,
    get_current_user,
    get_ludus_client_registry,
)
from app.core.encryption import decrypt_value
from app.core.security import hash_password
from app.models.event import Event
from app.models.ludus_server import LudusServer
from app.models.user import User
from app.services.ludus import LudusClient


@pytest.fixture
def test_settings() -> Settings:
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
    test_settings: Settings,
    mock_ludus: MagicMock,
    current_user: User | None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(settings_router)

    registry = LudusClientRegistry(test_settings.ludus_servers)

    def _override_get_db() -> Iterator[OrmSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_ludus_client_registry] = lambda: registry

    if current_user is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user

    return app


@pytest.fixture
def client(
    db_session: OrmSession,
    test_settings: Settings,
    mock_ludus: MagicMock,
    fake_admin: User,
) -> Iterator[TestClient]:
    app = _build_app(db_session, test_settings, mock_ludus, fake_admin)
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def anon_client(
    db_session: OrmSession,
    test_settings: Settings,
    mock_ludus: MagicMock,
) -> Iterator[TestClient]:
    app = _build_app(db_session, test_settings, mock_ludus, current_user=None)
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# POST /api/settings/ludus-servers (create)
# ---------------------------------------------------------------------------


def test_create_server_201(client: TestClient, db_session: OrmSession) -> None:
    resp = client.post(
        "/api/settings/ludus-servers",
        json={
            "name": "research",
            "url": "https://research.ludus.test",
            "api_key": "research-key-123",
            "verify_tls": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "research"
    assert body["url"] == "https://research.ludus.test"
    assert "****" in body["api_key_masked"]
    assert body["verify_tls"] is True
    assert body["source"] == "db"

    # Verify row in DB
    row = db_session.query(LudusServer).filter(LudusServer.name == "research").first()
    assert row is not None
    assert row.url == "https://research.ludus.test"


def test_create_server_duplicate_409(client: TestClient) -> None:
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "dup", "url": "https://a.test", "api_key": "key1"},
    )
    resp = client.post(
        "/api/settings/ludus-servers",
        json={"name": "dup", "url": "https://b.test", "api_key": "key2"},
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_create_server_invalid_name_422(client: TestClient) -> None:
    resp = client.post(
        "/api/settings/ludus-servers",
        json={"name": "Bad Name!", "url": "https://a.test", "api_key": "key1"},
    )
    assert resp.status_code == 422


def test_create_server_emits_event(
    client: TestClient, db_session: OrmSession
) -> None:
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "ev-test", "url": "https://a.test", "api_key": "key1"},
    )
    stmt = select(Event).where(Event.action == "ludus_server.created")
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].details_json["name"] == "ev-test"


def test_create_server_encrypts_key(
    client: TestClient, db_session: OrmSession, test_settings: Settings
) -> None:
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "enc-test", "url": "https://a.test", "api_key": "plain-key-abc"},
    )
    row = db_session.query(LudusServer).filter(LudusServer.name == "enc-test").first()
    assert row is not None
    assert row.api_key_encrypted != "plain-key-abc"
    assert decrypt_value(row.api_key_encrypted, test_settings.app_secret_key) == "plain-key-abc"


# ---------------------------------------------------------------------------
# PUT /api/settings/ludus-servers/{name} (update)
# ---------------------------------------------------------------------------


def test_update_server_200(client: TestClient) -> None:
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "upd", "url": "https://old.test", "api_key": "key1"},
    )
    resp = client.put(
        "/api/settings/ludus-servers/upd",
        json={"url": "https://new.test"},
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://new.test"
    assert resp.json()["source"] == "db"


def test_update_server_not_found_404(client: TestClient) -> None:
    resp = client.put(
        "/api/settings/ludus-servers/nonexistent",
        json={"url": "https://new.test"},
    )
    assert resp.status_code == 404


def test_update_server_emits_event(
    client: TestClient, db_session: OrmSession
) -> None:
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "upd-ev", "url": "https://a.test", "api_key": "key1"},
    )
    client.put(
        "/api/settings/ludus-servers/upd-ev",
        json={"verify_tls": True},
    )
    stmt = select(Event).where(Event.action == "ludus_server.updated")
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].details_json["name"] == "upd-ev"


# ---------------------------------------------------------------------------
# DELETE /api/settings/ludus-servers/{name}
# ---------------------------------------------------------------------------


def test_delete_server_204(client: TestClient, db_session: OrmSession) -> None:
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "del-me", "url": "https://a.test", "api_key": "key1"},
    )
    resp = client.delete("/api/settings/ludus-servers/del-me")
    assert resp.status_code == 204

    row = db_session.query(LudusServer).filter(LudusServer.name == "del-me").first()
    assert row is None


def test_delete_server_not_found_404(client: TestClient) -> None:
    resp = client.delete("/api/settings/ludus-servers/nonexistent")
    assert resp.status_code == 404


def test_delete_server_emits_event(
    client: TestClient, db_session: OrmSession
) -> None:
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "del-ev", "url": "https://a.test", "api_key": "key1"},
    )
    client.delete("/api/settings/ludus-servers/del-ev")
    stmt = select(Event).where(Event.action == "ludus_server.deleted")
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].details_json["name"] == "del-ev"


# ---------------------------------------------------------------------------
# GET /api/settings/ludus-servers (list)
# ---------------------------------------------------------------------------


def test_list_shows_source_field(client: TestClient) -> None:
    # Initially only env servers
    resp = client.get("/api/settings/ludus-servers")
    assert resp.status_code == 200
    body = resp.json()
    for srv in body["servers"]:
        assert srv["source"] == "env"

    # Add a DB server
    client.post(
        "/api/settings/ludus-servers",
        json={"name": "db-srv", "url": "https://db.test", "api_key": "key1"},
    )
    resp = client.get("/api/settings/ludus-servers")
    body = resp.json()
    sources = {s["name"]: s["source"] for s in body["servers"]}
    assert sources["default"] == "env"
    assert sources["db-srv"] == "db"


# ---------------------------------------------------------------------------
# Auth: unauthenticated returns 401
# ---------------------------------------------------------------------------


def test_create_server_unauthenticated_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/settings/ludus-servers",
        json={"name": "x", "url": "https://a.test", "api_key": "k"},
    )
    assert resp.status_code == 401


def test_update_server_unauthenticated_401(anon_client: TestClient) -> None:
    resp = anon_client.put(
        "/api/settings/ludus-servers/x",
        json={"url": "https://a.test"},
    )
    assert resp.status_code == 401


def test_delete_server_unauthenticated_401(anon_client: TestClient) -> None:
    resp = anon_client.delete("/api/settings/ludus-servers/x")
    assert resp.status_code == 401
