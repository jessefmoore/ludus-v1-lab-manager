"""Tests for the student endpoints (enroll + delete).

Mirrors the ``test_sessions_api`` fixture pattern: in-memory SQLite with
``StaticPool``, the ``get_current_user`` dependency overridden, and the
``get_ludus_client`` dependency overridden with a fake that records
calls so tests never touch the real Ludus server.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

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
from app.services import students as students_service
from app.services.exceptions import LudusError, LudusNotFound

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"
PUBLIC_BASE_URL = "https://lab.example.test"


# ---------------------------------------------------------------------------
# fakes / fixtures
# ---------------------------------------------------------------------------


class FakeLudus:
    """Stand-in for ``LudusClient`` that records ``user_rm`` invocations.

    Test code mutates ``user_rm_exc`` to force a specific exception path
    inside ``students_service.delete_student``.
    """

    def __init__(self) -> None:
        self.user_rm_calls: list[str] = []
        self.user_rm_exc: Exception | None = None

    def user_rm(self, userid: str) -> None:
        self.user_rm_calls.append(userid)
        if self.user_rm_exc is not None:
            raise self.user_rm_exc


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
        password_hash="irrelevant-for-students-tests",
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
def draft_session(
    db_session: OrmSession, lab_template: LabTemplate
) -> SessionRow:
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
def ended_session(
    db_session: OrmSession, lab_template: LabTemplate
) -> SessionRow:
    row = SessionRow(
        name="Old Cohort",
        lab_template_id=lab_template.id,
        mode=SessionMode.dedicated,
        status=SessionStatus.ended,
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
    status: StudentStatus = StudentStatus.pending,
    wg_config_path: str | None = None,
    range_id: str | None = None,
) -> Student:
    student = Student(
        session_id=session_row.id,
        full_name="Alice Example",
        email="alice@example.com",
        ludus_userid=ludus_userid,
        invite_token=invite_token,
        status=status,
        wg_config_path=wg_config_path,
        range_id=range_id,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# POST /api/sessions/{session_id}/students
# ---------------------------------------------------------------------------


def test_create_student_without_auth_returns_401(
    anon_client: TestClient, draft_session: SessionRow
) -> None:
    resp = anon_client.post(
        f"/api/sessions/{draft_session.id}/students",
        json={"full_name": "Alice Example", "email": "alice@example.com"},
    )
    assert resp.status_code == 401


def test_create_student_missing_session_returns_404(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/sessions/9999/students",
        json={"full_name": "Alice Example", "email": "alice@example.com"},
    )
    assert resp.status_code == 404


def test_create_student_ended_session_returns_409(
    client: TestClient, ended_session: SessionRow
) -> None:
    resp = client.post(
        f"/api/sessions/{ended_session.id}/students",
        json={"full_name": "Alice Example", "email": "alice@example.com"},
    )
    assert resp.status_code == 409
    assert "ended" in resp.json()["detail"].lower()


def test_create_student_happy_path_returns_201(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students",
        json={"full_name": "Alice Example", "email": "alice@example.com"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "Alice Example"
    assert body["email"] == "alice@example.com"
    assert body["status"] == "pending"
    assert body["range_id"] is None
    assert len(body["ludus_userid"]) <= 20
    assert body["ludus_userid"]
    assert body["invite_url"].startswith(f"{PUBLIC_BASE_URL}/invite/")
    token = body["invite_url"].rsplit("/", 1)[-1]
    assert len(token) == 32
    assert all(c in "0123456789abcdef" for c in token)

    # Verify persisted row matches and Ludus was NOT called on add.
    row = db_session.execute(
        select(Student).where(Student.id == body["id"])
    ).scalar_one()
    assert row.status == StudentStatus.pending
    assert row.range_id is None
    assert row.wg_config_path is None
    assert row.invite_redeemed_at is None
    assert fake_ludus.user_rm_calls == []


def test_create_student_twice_generates_distinct_userids(
    client: TestClient, draft_session: SessionRow
) -> None:
    resp1 = client.post(
        f"/api/sessions/{draft_session.id}/students",
        json={"full_name": "Alice Example", "email": "alice1@example.com"},
    )
    resp2 = client.post(
        f"/api/sessions/{draft_session.id}/students",
        json={"full_name": "Alice Example", "email": "alice2@example.com"},
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["ludus_userid"] != resp2.json()["ludus_userid"]


def test_create_student_writes_created_event(
    client: TestClient, db_session: OrmSession, draft_session: SessionRow
) -> None:
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students",
        json={"full_name": "Bob Example", "email": "bob@example.com"},
    )
    assert resp.status_code == 201
    student_id = resp.json()["id"]

    event = db_session.execute(
        select(Event).where(Event.action == "student.created")
    ).scalar_one()
    assert event.session_id == draft_session.id
    assert event.student_id == student_id
    assert event.details_json is not None
    assert event.details_json["student_id"] == student_id
    assert event.details_json["session_id"] == draft_session.id


def test_create_student_retries_on_userid_collision(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force the first two insert attempts to collide on ``ludus_userid``.

    Pre-seeds a row with the deterministic id the stub returns, then
    monkeypatches ``_make_userid`` so the first two attempts reuse it
    (triggering the IntegrityError path) before falling through to a
    fresh value that succeeds.
    """
    # Seed a student that will own the "colliding" userid.
    _make_student(
        db_session,
        draft_session,
        ludus_userid="existing-userid",
        invite_token="0" * 32,
    )

    call_count = {"n": 0}

    def fake_make_userid(base: str) -> str:
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return "existing-userid"
        return f"fresh-{call_count['n']}"

    monkeypatch.setattr(students_service, "_make_userid", fake_make_userid)

    resp = client.post(
        f"/api/sessions/{draft_session.id}/students",
        json={"full_name": "Carol Example", "email": "carol@example.com"},
    )
    assert resp.status_code == 201
    assert call_count["n"] >= 3, "expected retry loop to fire at least twice"
    assert resp.json()["ludus_userid"] == "fresh-3"


# ---------------------------------------------------------------------------
# DELETE /api/students/{student_id}
# ---------------------------------------------------------------------------


def test_delete_missing_student_returns_404(client: TestClient) -> None:
    resp = client.delete("/api/students/424242")
    assert resp.status_code == 404


def test_delete_pending_student_skips_ludus(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="pending-user",
        invite_token="a" * 32,
        status=StudentStatus.pending,
    )
    sid = student.id

    resp = client.delete(f"/api/students/{sid}")
    assert resp.status_code == 204

    assert fake_ludus.user_rm_calls == []
    assert db_session.get(Student, sid) is None

    event = db_session.execute(
        select(Event).where(Event.action == "student.deleted")
    ).scalar_one()
    assert event.session_id == draft_session.id
    assert event.details_json is not None
    assert event.details_json["ludus_userid"] == "pending-user"
    assert event.details_json["student_id"] == sid


def test_delete_ready_student_calls_ludus(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="ready-user",
        invite_token="b" * 32,
        status=StudentStatus.ready,
        range_id="42",
    )
    sid = student.id

    resp = client.delete(f"/api/students/{sid}")
    assert resp.status_code == 204
    assert fake_ludus.user_rm_calls == ["ready-user"]
    assert db_session.get(Student, sid) is None


def test_delete_ready_student_ludus_not_found_is_ok(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="already-gone",
        invite_token="c" * 32,
        status=StudentStatus.ready,
    )
    sid = student.id
    fake_ludus.user_rm_exc = LudusNotFound("user not found", status_code=404)

    resp = client.delete(f"/api/students/{sid}")
    assert resp.status_code == 204
    assert fake_ludus.user_rm_calls == ["already-gone"]
    assert db_session.get(Student, sid) is None


def test_delete_ready_student_ludus_error_returns_502(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    student = _make_student(
        db_session,
        draft_session,
        ludus_userid="broken-user",
        invite_token="d" * 32,
        status=StudentStatus.ready,
    )
    sid = student.id
    fake_ludus.user_rm_exc = LudusError("ludus is on fire", status_code=500)

    resp = client.delete(f"/api/students/{sid}")
    assert resp.status_code == 502
    # Row must survive so an operator can retry.
    assert db_session.get(Student, sid) is not None


def test_delete_student_unlinks_wg_config_file(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".conf", delete=False
    ) as tf:
        tf.write("[Interface]\n")
        cfg_path = tf.name

    try:
        student = _make_student(
            db_session,
            draft_session,
            ludus_userid="file-owner",
            invite_token="e" * 32,
            status=StudentStatus.ready,
            wg_config_path=cfg_path,
        )
        sid = student.id

        resp = client.delete(f"/api/students/{sid}")
        assert resp.status_code == 204
        assert not Path(cfg_path).exists()
        assert db_session.get(Student, sid) is None
    finally:
        # Belt and braces: ensure cleanup if the assertion above fires.
        Path(cfg_path).unlink(missing_ok=True)
