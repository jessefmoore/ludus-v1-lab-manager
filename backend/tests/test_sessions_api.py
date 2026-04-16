"""Tests for the /api/sessions router (list, create, detail, delete).

The provisioning endpoint (task #21) is deliberately out of scope here:
this suite only exercises the pure-DB CRUD surface and the authorization
gate inherited from ``get_current_user``.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.sessions import router as sessions_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.core.deps import get_current_user
from app.models import (
    Event,
    LabTemplate,
    LabTemplateMode,
    SessionMode,
    SessionStatus,
    Student,
    StudentStatus,
    User,
)
from app.models import (
    Session as SessionRow,
)

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"
PUBLIC_BASE_URL = "https://lab.example.test"


@pytest.fixture
def settings() -> Settings:
    """Test settings with a fixed public_base_url for invite-URL assertions."""
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email=ADMIN_EMAIL,
        admin_password=ADMIN_PASSWORD,
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key",
        public_base_url=PUBLIC_BASE_URL,
        _env_file=None,
    )


@pytest.fixture
def db_session() -> Iterator[OrmSession]:
    """Fresh in-memory SQLite DB with Base metadata applied."""
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
    """Insert a stub instructor used as the authenticated identity."""
    user = User(
        email=ADMIN_EMAIL,
        password_hash="irrelevant-for-sessions-tests",
        role="instructor",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def lab_template(db_session: OrmSession) -> LabTemplate:
    """A lab template the tests can reference from session payloads."""
    template = LabTemplate(
        name="AD Basics",
        description="Intro AD lab",
        range_config_yaml="ludus: []\n",
        default_mode=LabTemplateMode.dedicated,
        ludus_server="default",
        entry_point_vm="KALI",
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


@pytest.fixture
def app_factory(
    db_session: OrmSession,
    settings: Settings,
    fake_user: User,
):
    """Build a FastAPI app wired to the fixture DB/settings/user.

    ``authenticated=False`` simulates a request with no session cookie
    (``get_current_user`` raises 401 by default).
    """

    def _build(authenticated: bool = True) -> FastAPI:
        app = FastAPI()
        app.include_router(sessions_router)

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
    """Authenticated TestClient for the standard happy-path tests."""
    with TestClient(app_factory(authenticated=True)) as tc:
        yield tc


@pytest.fixture
def anon_client(app_factory) -> Iterator[TestClient]:
    """Unauthenticated TestClient used by the 401 test."""
    with TestClient(app_factory(authenticated=False)) as tc:
        yield tc


def _create_session_row(
    db: OrmSession,
    lab_template: LabTemplate,
    *,
    name: str = "Spring 2026 Cohort",
    status: SessionStatus = SessionStatus.draft,
    mode: SessionMode = SessionMode.dedicated,
) -> SessionRow:
    """Helper: direct-ORM insert of a session (bypasses the service layer)."""
    row = SessionRow(
        name=name,
        lab_template_id=lab_template.id,
        mode=mode,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _create_student_row(
    db: OrmSession,
    session_row: SessionRow,
    *,
    ludus_userid: str,
    invite_token: str,
    full_name: str = "Alice Example",
    email: str = "alice@example.com",
    status: StudentStatus = StudentStatus.pending,
) -> Student:
    student = Student(
        session_id=session_row.id,
        full_name=full_name,
        email=email,
        ludus_userid=ludus_userid,
        invite_token=invite_token,
        status=status,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


# --- tests ---------------------------------------------------------------


def test_list_sessions_without_auth_returns_401(anon_client: TestClient) -> None:
    """Unauthenticated GET /api/sessions is rejected by the auth dependency."""
    resp = anon_client.get("/api/sessions")
    assert resp.status_code == 401


def test_create_session_with_missing_lab_template_returns_404(
    client: TestClient,
) -> None:
    """lab_template_id referencing a non-existent row yields 404."""
    resp = client.post(
        "/api/sessions",
        json={
            "name": "Nope",
            "lab_template_id": 9999,
            "mode": "dedicated",
        },
    )
    assert resp.status_code == 404
    assert "lab_template_id=9999" in resp.json()["detail"]


def test_create_session_happy_path_returns_201_and_draft(
    client: TestClient, lab_template: LabTemplate
) -> None:
    """Valid payload returns 201, status=draft, id populated."""
    resp = client.post(
        "/api/sessions",
        json={
            "name": "Spring 2026 Cohort",
            "lab_template_id": lab_template.id,
            "mode": "dedicated",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] > 0
    assert body["name"] == "Spring 2026 Cohort"
    assert body["lab_template_id"] == lab_template.id
    assert body["mode"] == "dedicated"
    assert body["status"] == "draft"
    assert body["created_at"] is not None


def test_list_sessions_contains_created_row(
    client: TestClient, lab_template: LabTemplate
) -> None:
    """A session created through POST appears in the GET list."""
    create = client.post(
        "/api/sessions",
        json={
            "name": "Summer 2026 Cohort",
            "lab_template_id": lab_template.id,
            "mode": "shared",
        },
    )
    assert create.status_code == 201
    created_id = create.json()["id"]

    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(
        row["id"] == created_id and row["name"] == "Summer 2026 Cohort"
        for row in body
    )


def test_get_session_detail_returns_empty_students_list(
    client: TestClient, db_session: OrmSession, lab_template: LabTemplate
) -> None:
    """GET /api/sessions/{id} returns the session with students: []."""
    row = _create_session_row(db_session, lab_template)

    resp = client.get(f"/api/sessions/{row.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == row.id
    assert body["students"] == []


def test_get_session_detail_embeds_students_with_invite_urls(
    client: TestClient, db_session: OrmSession, lab_template: LabTemplate
) -> None:
    """Each embedded student exposes a derived invite_url built from settings."""
    row = _create_session_row(db_session, lab_template)
    _create_student_row(
        db_session,
        row,
        ludus_userid="alice",
        invite_token="tok-alice",
        full_name="Alice Example",
        email="alice@example.com",
    )
    _create_student_row(
        db_session,
        row,
        ludus_userid="bob",
        invite_token="tok-bob",
        full_name="Bob Example",
        email="bob@example.com",
    )

    resp = client.get(f"/api/sessions/{row.id}")
    assert resp.status_code == 200
    body = resp.json()
    students = body["students"]
    assert len(students) == 2

    by_userid = {s["ludus_userid"]: s for s in students}
    assert (
        by_userid["alice"]["invite_url"]
        == f"{PUBLIC_BASE_URL}/invite/tok-alice"
    )
    assert (
        by_userid["bob"]["invite_url"]
        == f"{PUBLIC_BASE_URL}/invite/tok-bob"
    )
    # Raw token must not leak.
    for student in students:
        assert "invite_token" not in student


def test_delete_draft_session_returns_204(
    client: TestClient, db_session: OrmSession, lab_template: LabTemplate
) -> None:
    """Deleting a draft session with no students returns 204 and drops the row."""
    row = _create_session_row(db_session, lab_template, name="To Delete")
    sid = row.id

    resp = client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204

    listing = client.get("/api/sessions").json()
    assert all(r["id"] != sid for r in listing)


def test_delete_active_session_returns_409(
    client: TestClient, db_session: OrmSession, lab_template: LabTemplate
) -> None:
    """Active sessions cannot be deleted via this endpoint."""
    row = _create_session_row(
        db_session, lab_template, status=SessionStatus.active
    )
    resp = client.delete(f"/api/sessions/{row.id}")
    assert resp.status_code == 409


def test_delete_draft_session_with_ready_student_returns_409(
    client: TestClient, db_session: OrmSession, lab_template: LabTemplate
) -> None:
    """A draft session with a ready student is still refused (state conflict)."""
    row = _create_session_row(db_session, lab_template)
    _create_student_row(
        db_session,
        row,
        ludus_userid="ready-user",
        invite_token="tok-ready",
        status=StudentStatus.ready,
    )
    resp = client.delete(f"/api/sessions/{row.id}")
    assert resp.status_code == 409


def test_delete_missing_session_returns_404(client: TestClient) -> None:
    """Deleting an unknown id returns 404."""
    resp = client.delete("/api/sessions/42424242")
    assert resp.status_code == 404


def test_create_session_writes_session_created_event(
    client: TestClient, db_session: OrmSession, lab_template: LabTemplate
) -> None:
    """An ``session.created`` audit row is written on POST."""
    resp = client.post(
        "/api/sessions",
        json={
            "name": "Audited Cohort",
            "lab_template_id": lab_template.id,
            "mode": "shared",
        },
    )
    assert resp.status_code == 201
    created_id = resp.json()["id"]

    event = db_session.execute(
        select(Event).where(Event.action == "session.created")
    ).scalar_one()
    assert event.session_id == created_id
    assert event.details_json is not None
    assert event.details_json["session_id"] == created_id
    assert event.details_json["name"] == "Audited Cohort"
    assert event.details_json["mode"] == "shared"
