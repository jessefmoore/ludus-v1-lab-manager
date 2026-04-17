"""Tests for the 2-minute reset cooldown feature.

Builds on the existing ``test_students_reset.py`` fixture pattern. Exercises
the cooldown check in ``students_service.reset_student()`` which queries the
most recent ``student.reset`` event to enforce a 120-second window.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"
PUBLIC_BASE_URL = "https://lab.example.test"


# ---------------------------------------------------------------------------
# fakes / fixtures
# ---------------------------------------------------------------------------


class FakeLudus:
    def __init__(self) -> None:
        self.snapshot_revert_calls: list[tuple[str, str]] = []

    def snapshot_revert(self, userid: str, name: str) -> None:
        self.snapshot_revert_calls.append((userid, name))


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
        password_hash="irrelevant",
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


def _make_ready_student(
    db: OrmSession,
    session_row: SessionRow,
    *,
    ludus_userid: str = "ready-user",
    invite_token: str = "a" * 32,
) -> Student:
    student = Student(
        session_id=session_row.id,
        full_name="Alice Example",
        email="alice@example.com",
        ludus_userid=ludus_userid,
        invite_token=invite_token,
        status=StudentStatus.ready,
        range_id="42",
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_first_reset_succeeds(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    """No prior reset event means no cooldown — should return 202."""
    student = _make_ready_student(db_session, draft_session)
    resp = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp.status_code == 202
    assert fake_ludus.snapshot_revert_calls == [(student.ludus_userid, "ctf-initial")]


def test_immediate_second_reset_returns_429(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    """Second reset within cooldown window should return 429."""
    student = _make_ready_student(db_session, draft_session)

    resp1 = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp1.status_code == 202

    resp2 = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp2.status_code == 429
    assert "cooldown" in resp2.json()["detail"].lower()
    # Ludus should only have been called once
    assert len(fake_ludus.snapshot_revert_calls) == 1


def test_reset_after_cooldown_expires_succeeds(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    """Once the cooldown window passes, reset should be allowed again."""
    student = _make_ready_student(db_session, draft_session)

    # First reset
    resp1 = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp1.status_code == 202

    # Manually backdate the event to simulate cooldown expiry
    event = (
        db_session.query(Event)
        .filter(
            Event.action == "student.reset",
            Event.student_id == student.id,
        )
        .one()
    )
    event.created_at = datetime.now(UTC) - timedelta(seconds=130)
    db_session.commit()

    # Second reset should now work
    resp2 = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp2.status_code == 202
    assert len(fake_ludus.snapshot_revert_calls) == 2


def test_cooldown_is_per_student(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
    fake_ludus: FakeLudus,
) -> None:
    """Resetting student A should not block resetting student B."""
    student_a = _make_ready_student(
        db_session,
        draft_session,
        ludus_userid="student-a",
        invite_token="a" * 32,
    )
    student_b = _make_ready_student(
        db_session,
        draft_session,
        ludus_userid="student-b",
        invite_token="b" * 32,
    )

    resp_a = client.post(f"/api/students/{student_a.id}/reset", json={})
    assert resp_a.status_code == 202

    # Student B should not be affected by student A's cooldown
    resp_b = client.post(f"/api/students/{student_b.id}/reset", json={})
    assert resp_b.status_code == 202
    assert len(fake_ludus.snapshot_revert_calls) == 2


def test_429_response_includes_wait_time(
    client: TestClient,
    db_session: OrmSession,
    draft_session: SessionRow,
) -> None:
    """The 429 detail message should include remaining seconds."""
    student = _make_ready_student(db_session, draft_session)

    client.post(f"/api/students/{student.id}/reset", json={})
    resp = client.post(f"/api/students/{student.id}/reset", json={})
    assert resp.status_code == 429
    detail = resp.json()["detail"]
    assert "wait" in detail.lower()
    # Should contain a number (the seconds)
    assert any(c.isdigit() for c in detail)
