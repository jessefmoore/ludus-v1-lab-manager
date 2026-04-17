"""Tests for ``POST /api/students/{student_id}/reset`` (snapshot revert).

Mirrors the fixture pattern in ``test_students_api.py``: in-memory SQLite
with ``StaticPool``, ``get_current_user`` overridden, and a recording
``FakeLudus`` swapped in via ``get_ludus_client``. Fixtures are
duplicated (rather than factored into a conftest) to keep the Phase 1
test layout flat.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.students import router as students_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.core.deps import get_current_user, get_ludus_client
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
from app.services.exceptions import LudusError

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"
PUBLIC_BASE_URL = "https://lab.example.test"


# ---------------------------------------------------------------------------
# fakes / fixtures
# ---------------------------------------------------------------------------


class FakeLudus:
    """Stand-in for ``LudusClient`` that records ``snapshot_revert`` calls.

    Mirrors the real ``LudusClient.snapshot_revert(userid, name)``
    signature so tests catch signature drift. ``snapshot_revert_exc``
    lets a test force a specific exception from the Ludus call.
    """

    def __init__(self) -> None:
        self.snapshot_revert_calls: list[tuple[str, str]] = []
        self.snapshot_revert_exc: Exception | None = None

    def snapshot_revert(self, userid: str, name: str) -> None:
        self.snapshot_revert_calls.append((userid, name))
        if self.snapshot_revert_exc is not None:
            raise self.snapshot_revert_exc


@pytest.fixture
def settings() -> Settings:
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
        password_hash="irrelevant-for-reset-tests",
        role="instructor",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def lab_template(db_session: OrmSession) -> LabTemplate:
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
def draft_session(db_session: OrmSession, lab_template: LabTemplate) -> SessionRow:
    row = SessionRow(
        name="Spring 2026 Cohort",
        lab_template_id=lab_template.id,
        mode=SessionMode.dedicated,
        status=SessionStatus.draft,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def fake_ludus() -> FakeLudus:
    return FakeLudus()


@pytest.fixture
def app_factory(
    db_session: OrmSession,
    settings: Settings,
    fake_user: User,
    fake_ludus: FakeLudus,
):
    def _build(authenticated: bool = True) -> FastAPI:
        app = FastAPI()
        app.include_router(students_router)

        def _override_get_db() -> Iterator[OrmSession]:
            yield db_session

        def _override_get_settings() -> Settings:
            return settings

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_settings] = _override_get_settings
        app.dependency_overrides[get_ludus_client] = lambda: fake_ludus
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


def _make_student(
    db: OrmSession,
    session_row: SessionRow,
    *,
    ludus_userid: str,
    invite_token: str,
    status: StudentStatus,
    range_id: str | None = None,
) -> Student:
    student = Student(
        session_id=session_row.id,
        full_name="Alice Example",
        email="alice@example.com",
        ludus_userid=ludus_userid,
        invite_token=invite_token,
        status=status,
        range_id=range_id,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# POST /api/students/{student_id}/reset
# ---------------------------------------------------------------------------


def test_reset_without_auth_returns_401(
    anon_client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="ready-user",
        invite_token="a" * 32,
        status=StudentStatus.ready,
        range_id="42",
    )
    resp = anon_client.post(f"/api/students/{student.id}/reset", json={})
    assert resp.status_code == 401


def test_reset_missing_student_returns_404(client: TestClient, fake_ludus: FakeLudus) -> None:
    resp = client.post("/api/students/9999/reset", json={})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Student not found"
    assert fake_ludus.snapshot_revert_calls == []


def test_reset_pending_student_returns_409_and_does_not_call_ludus(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="pending-user",
        invite_token="b" * 32,
        status=StudentStatus.pending,
    )
    resp = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp.status_code == 409
    assert "ready state" in resp.json()["detail"].lower()
    assert fake_ludus.snapshot_revert_calls == []


def test_reset_error_student_returns_409(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="error-user",
        invite_token="c" * 32,
        status=StudentStatus.error,
    )
    resp = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp.status_code == 409
    assert fake_ludus.snapshot_revert_calls == []


def test_reset_ready_student_default_snapshot_returns_202(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="ready-user",
        invite_token="d" * 32,
        status=StudentStatus.ready,
        range_id="42",
    )
    sid = student.id
    userid = student.ludus_userid

    resp = client.post(f"/api/students/{sid}/reset", json={})
    assert resp.status_code == 202
    assert resp.json() == {
        "status": "reset_triggered",
        "snapshot_name": "ctf-initial",
    }
    assert fake_ludus.snapshot_revert_calls == [(userid, "ctf-initial")]

    event = db_session.execute(select(Event).where(Event.action == "student.reset")).scalar_one()
    assert event.student_id == sid
    assert event.session_id == draft_session.id
    assert event.details_json is not None
    assert event.details_json["userid"] == userid
    assert event.details_json["snapshot_name"] == "ctf-initial"
    assert event.details_json["range_id"] == "42"


def test_reset_ready_student_no_body_uses_default_snapshot(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    """Calling with no body at all should still default to ctf-initial."""
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="ready-nobody",
        invite_token="f" * 32,
        status=StudentStatus.ready,
    )
    resp = client.post(f"/api/students/{student.id}/reset")
    assert resp.status_code == 202
    assert resp.json()["snapshot_name"] == "ctf-initial"
    assert fake_ludus.snapshot_revert_calls == [(student.ludus_userid, "ctf-initial")]


def test_reset_ready_student_custom_snapshot(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="custom-user",
        invite_token="e" * 32,
        status=StudentStatus.ready,
    )
    resp = client.post(
        f"/api/students/{student.id}/reset",
        json={"snapshot_name": "lab-clean"},
    )
    assert resp.status_code == 202
    assert resp.json() == {
        "status": "reset_triggered",
        "snapshot_name": "lab-clean",
    }
    assert fake_ludus.snapshot_revert_calls == [(student.ludus_userid, "lab-clean")]


def test_reset_ludus_error_returns_502(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="broken-user",
        invite_token="9" * 32,
        status=StudentStatus.ready,
    )
    fake_ludus.snapshot_revert_exc = LudusError("ludus is on fire", status_code=500)

    resp = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp.status_code == 502
    assert "ludus" in resp.json()["detail"].lower()

    # No reset event should have been recorded on failure.
    events = (
        db_session.execute(select(Event).where(Event.action == "student.reset")).scalars().all()
    )
    assert events == []
