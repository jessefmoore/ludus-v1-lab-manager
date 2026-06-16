"""Tests for the /api/labs endpoints (list, create, detail)."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.labs import router as labs_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.core.deps import get_current_user
from app.models.event import Event
from app.models.lab_template import LabTemplate
from app.models.session import Session, SessionMode, SessionStatus
from app.models.user import User

VALID_YAML = """\
ludus:
  - vm_name: "{{ range_id }}-web"
    hostname: "{{ range_id }}-web"
    template: debian-12-x64-server-template
    vlan: 10
    ip_last_octet: 10
    ram_gb: 2
    cpus: 2
    linux: true
"""


@pytest.fixture
def settings() -> Settings:
    """Minimal Settings object that avoids touching a real .env file."""
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email="instructor@example.com",
        admin_password="super-secret-test-pw",
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key",
        _env_file=None,
    )


@pytest.fixture
def db_session() -> Iterator[OrmSession]:
    """Fresh in-memory SQLite with all ORM metadata applied."""
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
    """A User row the fake get_current_user override will hand back."""
    user = User(
        email="instructor@example.com",
        password_hash="irrelevant-for-these-tests",
        role="instructor",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _build_app(
    db_session: OrmSession,
    settings: Settings,
    current_user: User | None,
) -> FastAPI:
    """Assemble a FastAPI app wired to the fixture DB.

    If ``current_user`` is None the real ``get_current_user`` runs, which
    yields 401 when no session cookie is present. Otherwise the dependency
    is overridden to hand back the supplied user row.
    """
    app = FastAPI()
    app.include_router(labs_router)

    def _override_get_db() -> Iterator[OrmSession]:
        yield db_session

    def _override_get_settings() -> Settings:
        return settings

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = _override_get_settings

    if current_user is not None:

        def _override_get_current_user() -> User:
            return current_user

        app.dependency_overrides[get_current_user] = _override_get_current_user

    return app


@pytest.fixture
def client(
    db_session: OrmSession,
    settings: Settings,
    fake_admin: User,
) -> Iterator[TestClient]:
    """Authenticated TestClient: get_current_user returns the fake admin."""
    app = _build_app(db_session, settings, fake_admin)
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def anon_client(
    db_session: OrmSession,
    settings: Settings,
) -> Iterator[TestClient]:
    """Unauthenticated TestClient: real get_current_user runs."""
    app = _build_app(db_session, settings, current_user=None)
    with TestClient(app) as tc:
        yield tc


def _create_payload(**overrides: object) -> dict:
    """Build a full LabTemplateCreate payload, overridable per test."""
    base: dict = {
        "name": "Grand Line AD",
        "description": "Bidirectional forest trust lab.",
        "range_config_yaml": VALID_YAML,
        "default_mode": "shared",
        "ludus_server": "default",
        "entry_point_vm": "thousand-sunny",
    }
    base.update(overrides)
    return base


def test_list_labs_without_auth_returns_401(anon_client: TestClient) -> None:
    """GET /api/labs without a session cookie must be rejected."""
    resp = anon_client.get("/api/labs")
    assert resp.status_code == 401


def test_create_lab_with_valid_yaml_persists_and_returns_201(
    client: TestClient, db_session: OrmSession
) -> None:
    """POST /api/labs stores the row and returns a read-model with id/created_at."""
    resp = client.post("/api/labs", json=_create_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body and isinstance(body["id"], int)
    assert "created_at" in body
    assert body["name"] == "Grand Line AD"
    assert body["default_mode"] == "shared"
    assert body["ludus_server"] == "default"
    assert body["entry_point_vm"] == "thousand-sunny"

    stored = db_session.get(LabTemplate, body["id"])
    assert stored is not None
    assert stored.name == "Grand Line AD"
    assert stored.range_config_yaml == VALID_YAML


def test_list_labs_returns_created_lab(client: TestClient) -> None:
    """After POST, the row appears in the GET list output."""
    created = client.post("/api/labs", json=_create_payload()).json()

    resp = client.get("/api/labs")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["id"] == created["id"]
    assert rows[0]["name"] == "Grand Line AD"


def test_get_lab_by_id_returns_row_or_404(client: TestClient) -> None:
    """GET /api/labs/{id} returns the row; unknown id yields 404."""
    created = client.post("/api/labs", json=_create_payload()).json()

    ok = client.get(f"/api/labs/{created['id']}")
    assert ok.status_code == 200
    assert ok.json()["id"] == created["id"]

    missing = client.get("/api/labs/999999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Lab template not found"


def test_create_lab_with_malformed_yaml_returns_422(client: TestClient) -> None:
    """Unparseable YAML is rejected with a helpful 422 message."""
    resp = client.post(
        "/api/labs",
        json=_create_payload(range_config_yaml="not: : valid: yaml"),
    )
    assert resp.status_code == 422
    assert "not valid YAML" in resp.json()["detail"]


def test_create_lab_with_non_dict_yaml_returns_422(client: TestClient) -> None:
    """YAML that parses to a non-mapping (e.g., a list) is rejected."""
    resp = client.post(
        "/api/labs",
        json=_create_payload(range_config_yaml="- foo\n- bar\n"),
    )
    assert resp.status_code == 422
    assert "mapping" in resp.json()["detail"]


def test_create_lab_emits_audit_event(client: TestClient, db_session: OrmSession) -> None:
    """A successful create writes an Event row with action=lab_template.created."""
    created = client.post("/api/labs", json=_create_payload()).json()

    stmt = select(Event).where(Event.action == "lab_template.created")
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    event = events[0]
    assert event.session_id is None
    assert event.student_id is None
    assert event.details_json is not None
    assert event.details_json.get("lab_template_id") == created["id"]
    assert event.details_json.get("name") == "Grand Line AD"


# ---------------------------------------------------------------------------
# PUT /api/labs/{lab_id}
# ---------------------------------------------------------------------------


def _create_lab_via_api(client: TestClient, **overrides: object) -> dict:
    """Helper: POST a lab and return the response body."""
    resp = client.post("/api/labs", json=_create_payload(**overrides))
    assert resp.status_code == 201
    return resp.json()


def test_update_lab_name(client: TestClient, db_session: OrmSession) -> None:
    created = _create_lab_via_api(client)

    resp = client.put(f"/api/labs/{created['id']}", json={"name": "Renamed Lab"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed Lab"
    assert body["description"] == created["description"]

    stored = db_session.get(LabTemplate, created["id"])
    assert stored is not None
    assert stored.name == "Renamed Lab"


def test_update_lab_invalid_yaml_returns_422(client: TestClient) -> None:
    created = _create_lab_via_api(client)

    resp = client.put(
        f"/api/labs/{created['id']}",
        json={"range_config_yaml": "not: : valid: yaml"},
    )
    assert resp.status_code == 422
    assert "not valid YAML" in resp.json()["detail"]


def test_update_lab_not_found_returns_404(client: TestClient) -> None:
    resp = client.put("/api/labs/999999", json={"name": "Ghost"})
    assert resp.status_code == 404


def test_update_lab_emits_event(client: TestClient, db_session: OrmSession) -> None:
    created = _create_lab_via_api(client)

    client.put(f"/api/labs/{created['id']}", json={"name": "Updated"})

    stmt = select(Event).where(Event.action == "lab_template.updated")
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].details_json["lab_template_id"] == created["id"]
    assert "name" in events[0].details_json["changed_fields"]


# ---------------------------------------------------------------------------
# DELETE /api/labs/{lab_id}
# ---------------------------------------------------------------------------


def test_delete_lab_success_returns_204(client: TestClient, db_session: OrmSession) -> None:
    created = _create_lab_via_api(client)

    resp = client.delete(f"/api/labs/{created['id']}")
    assert resp.status_code == 204

    assert db_session.get(LabTemplate, created["id"]) is None


def test_delete_lab_not_found_returns_404(client: TestClient) -> None:
    resp = client.delete("/api/labs/999999")
    assert resp.status_code == 404


def test_delete_lab_with_active_session_returns_409(
    client: TestClient, db_session: OrmSession
) -> None:
    created = _create_lab_via_api(client)

    session = Session(
        name="Active Session",
        lab_template_id=created["id"],
        mode=SessionMode.shared,
        status=SessionStatus.active,
    )
    db_session.add(session)
    db_session.commit()

    resp = client.delete(f"/api/labs/{created['id']}")
    assert resp.status_code == 409

    # Lab should still exist.
    assert db_session.get(LabTemplate, created["id"]) is not None


def test_delete_lab_with_ended_sessions_succeeds(
    client: TestClient, db_session: OrmSession
) -> None:
    created = _create_lab_via_api(client)

    session = Session(
        name="Ended Session",
        lab_template_id=created["id"],
        mode=SessionMode.shared,
        status=SessionStatus.ended,
    )
    db_session.add(session)
    db_session.commit()

    resp = client.delete(f"/api/labs/{created['id']}")
    assert resp.status_code == 204


def test_delete_lab_emits_event(client: TestClient, db_session: OrmSession) -> None:
    created = _create_lab_via_api(client)

    client.delete(f"/api/labs/{created['id']}")

    stmt = select(Event).where(Event.action == "lab_template.deleted")
    events = list(db_session.execute(stmt).scalars().all())
    assert len(events) == 1
    assert events[0].details_json["lab_template_id"] == created["id"]
    assert events[0].details_json["name"] == "Grand Line AD"
