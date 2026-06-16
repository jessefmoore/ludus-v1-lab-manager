"""Tests for the public invite endpoints (``/invite/{token}`` + ``/config``).

Mirrors the StaticPool + dependency-override pattern of
``test_students_reset.py``. The invite router has NO
``get_current_user`` dependency, so we do not override it.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.invite import router as invite_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.models import (
    Event,
    LabTemplate,
    LabTemplateMode,
    SessionMode,
    SessionStatus,
    Student,
    StudentStatus,
)
from app.models import (
    Session as SessionRow,
)

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"
PUBLIC_BASE_URL = "https://lab.example.test"
TTL_HOURS = 168


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
        public_base_url=PUBLIC_BASE_URL,
        invite_token_ttl_hours=TTL_HOURS,
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
def lab_template(db_session: OrmSession) -> LabTemplate:
    template = LabTemplate(
        name="AD Basics",
        description="Intro Active Directory lab",
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
def active_session(db_session: OrmSession, lab_template: LabTemplate) -> SessionRow:
    row = SessionRow(
        name="Spring 2026 Cohort",
        lab_template_id=lab_template.id,
        mode=SessionMode.dedicated,
        status=SessionStatus.active,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture
def config_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def app(
    db_session: OrmSession,
    settings: Settings,
) -> FastAPI:
    app = FastAPI()
    app.include_router(invite_router)

    def _override_get_db() -> Iterator[OrmSession]:
        yield db_session

    def _override_get_settings() -> Settings:
        return settings

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = _override_get_settings
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as tc:
        yield tc


def _make_student(
    db: OrmSession,
    session_row: SessionRow,
    *,
    ludus_userid: str,
    invite_token: str,
    status: StudentStatus,
    wg_config_path: str | None = None,
    created_at: datetime | None = None,
    full_name: str = "Alice Example",
) -> Student:
    student = Student(
        session_id=session_row.id,
        full_name=full_name,
        email="alice@example.com",
        ludus_userid=ludus_userid,
        invite_token=invite_token,
        status=status,
        wg_config_path=wg_config_path,
    )
    if created_at is not None:
        student.created_at = created_at
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# GET /invite/{token}
# ---------------------------------------------------------------------------


def test_invite_page_unknown_token_returns_404(client: TestClient) -> None:
    resp = client.get("/invite/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invite link not found or expired"


def test_invite_page_valid_token_returns_html_with_context(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
) -> None:
    _make_student(
        db_session,
        active_session,
        ludus_userid="alice-abcd12",
        invite_token="a" * 32,
        status=StudentStatus.ready,
        full_name="Alice Example",
    )
    resp = client.get(f"/invite/{'a' * 32}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "Alice Example" in body
    assert "AD Basics" in body
    assert "KALI" in body


def test_invite_page_expired_token_returns_404(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
) -> None:
    expired_created_at = datetime.now(UTC) - timedelta(hours=TTL_HOURS + 1)
    _make_student(
        db_session,
        active_session,
        ludus_userid="expired-user",
        invite_token="b" * 32,
        status=StudentStatus.ready,
        created_at=expired_created_at,
    )
    resp = client.get(f"/invite/{'b' * 32}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invite link not found or expired"


# ---------------------------------------------------------------------------
# GET /invite/{token}/config
# ---------------------------------------------------------------------------


def test_invite_config_ready_student_returns_file(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
    config_dir: Path,
) -> None:
    conf_path = config_dir / "alice.conf"
    conf_bytes = b"[Interface]\nPrivateKey = fake\n"
    conf_path.write_bytes(conf_bytes)

    _make_student(
        db_session,
        active_session,
        ludus_userid="alice-abcd12",
        invite_token="c" * 32,
        status=StudentStatus.ready,
        wg_config_path=str(conf_path),
    )

    resp = client.get(f"/invite/{'c' * 32}/config")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["content-disposition"] == 'attachment; filename="alice-abcd12.conf"'
    assert resp.content == conf_bytes


def test_invite_config_pending_student_returns_409(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
) -> None:
    _make_student(
        db_session,
        active_session,
        ludus_userid="pending-user",
        invite_token="d" * 32,
        status=StudentStatus.pending,
    )
    resp = client.get(f"/invite/{'d' * 32}/config")
    assert resp.status_code == 409
    assert "not ready" in resp.json()["detail"].lower()


def test_invite_config_unknown_token_returns_404(client: TestClient) -> None:
    resp = client.get("/invite/unknown-token/config")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Invite link not found or expired"


def test_invite_config_first_call_sets_redeemed_and_logs_event(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
    config_dir: Path,
) -> None:
    conf_path = config_dir / "first.conf"
    conf_path.write_bytes(b"first-call-bytes")
    student = _make_student(
        db_session,
        active_session,
        ludus_userid="first-user",
        invite_token="e" * 32,
        status=StudentStatus.ready,
        wg_config_path=str(conf_path),
    )
    assert student.invite_redeemed_at is None

    resp = client.get(f"/invite/{'e' * 32}/config")
    assert resp.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(Student, student.id)
    assert refreshed is not None
    assert isinstance(refreshed.invite_redeemed_at, datetime)

    events = (
        db_session.execute(select(Event).where(Event.action == "invite.redeemed")).scalars().all()
    )
    assert len(events) == 1
    assert events[0].student_id == student.id
    assert events[0].session_id == active_session.id


def test_invite_config_second_call_logs_redownloaded_and_keeps_timestamp(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
    config_dir: Path,
) -> None:
    conf_path = config_dir / "second.conf"
    conf_path.write_bytes(b"second-call-bytes")
    student = _make_student(
        db_session,
        active_session,
        ludus_userid="second-user",
        invite_token="f" * 32,
        status=StudentStatus.ready,
        wg_config_path=str(conf_path),
    )

    # First call: marks redeemed.
    first = client.get(f"/invite/{'f' * 32}/config")
    assert first.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(Student, student.id)
    assert refreshed is not None
    first_redeemed_at = refreshed.invite_redeemed_at
    assert isinstance(first_redeemed_at, datetime)

    # Second call: should log redownloaded and leave timestamp unchanged.
    second = client.get(f"/invite/{'f' * 32}/config")
    assert second.status_code == 200

    db_session.expire_all()
    refreshed2 = db_session.get(Student, student.id)
    assert refreshed2 is not None
    assert refreshed2.invite_redeemed_at == first_redeemed_at

    redownloaded_events = (
        db_session.execute(select(Event).where(Event.action == "invite.redownloaded"))
        .scalars()
        .all()
    )
    assert len(redownloaded_events) == 1
    assert redownloaded_events[0].student_id == student.id

    redeemed_events = (
        db_session.execute(select(Event).where(Event.action == "invite.redeemed")).scalars().all()
    )
    assert len(redeemed_events) == 1


def test_invite_config_none_wg_config_path_returns_409(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
) -> None:
    _make_student(
        db_session,
        active_session,
        ludus_userid="nopath-user",
        invite_token="1" * 32,
        status=StudentStatus.ready,
        wg_config_path=None,
    )
    resp = client.get(f"/invite/{'1' * 32}/config")
    assert resp.status_code == 409
    assert "not ready" in resp.json()["detail"].lower()


def test_invite_config_missing_file_on_disk_returns_409(
    client: TestClient,
    db_session: OrmSession,
    active_session: SessionRow,
    config_dir: Path,
) -> None:
    missing_path = config_dir / "does-not-exist.conf"
    _make_student(
        db_session,
        active_session,
        ludus_userid="ghost-user",
        invite_token="2" * 32,
        status=StudentStatus.ready,
        wg_config_path=str(missing_path),
    )
    resp = client.get(f"/invite/{'2' * 32}/config")
    assert resp.status_code == 409
    assert "not ready" in resp.json()["detail"].lower()
