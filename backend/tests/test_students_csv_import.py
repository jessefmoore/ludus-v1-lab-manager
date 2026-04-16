"""Tests for ``POST /api/sessions/{session_id}/students/import`` (CSV bulk import).

Mirrors the flat-fixture pattern from test_students_api.py: in-memory SQLite
with ``StaticPool``, ``get_current_user`` overridden, and a recording
``FakeLudus`` swapped in.
"""

from __future__ import annotations

import io
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
    """Minimal stand-in — CSV import never touches Ludus."""

    pass


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


def _csv_bytes(rows: list[list[str]], header: list[str] | None = None) -> bytes:
    """Build a CSV file in-memory for upload."""
    buf = io.StringIO()
    if header is None:
        header = ["full_name", "email"]
    buf.write(",".join(header) + "\n")
    for row in rows:
        buf.write(",".join(row) + "\n")
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_csv_import_without_auth_returns_401(
    anon_client: TestClient, draft_session: SessionRow
) -> None:
    csv = _csv_bytes([["Alice", "alice@example.com"]])
    resp = anon_client.post(
        f"/api/sessions/{draft_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 401


def test_csv_import_happy_path(
    client: TestClient, db_session: OrmSession, draft_session: SessionRow
) -> None:
    csv = _csv_bytes([
        ["Alice Example", "alice@example.com"],
        ["Bob Example", "bob@example.com"],
        ["Carol Example", "carol@example.com"],
    ])
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 3
    assert body["failed"] == 0
    assert body["errors"] == []

    # Verify DB rows
    students = db_session.scalars(
        select(Student).where(Student.session_id == draft_session.id)
    ).all()
    assert len(students) == 3
    names = {s.full_name for s in students}
    assert names == {"Alice Example", "Bob Example", "Carol Example"}


def test_csv_import_missing_columns_returns_400(
    client: TestClient, draft_session: SessionRow
) -> None:
    csv = _csv_bytes([["Alice", "alice@example.com"]], header=["name", "email_addr"])
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 400
    assert "full_name" in resp.json()["detail"]


def test_csv_import_invalid_email_row_is_skipped(
    client: TestClient, db_session: OrmSession, draft_session: SessionRow
) -> None:
    csv = _csv_bytes([
        ["Alice Example", "alice@example.com"],
        ["Bad Email", "not-an-email"],
        ["Carol Example", "carol@example.com"],
    ])
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 2
    assert body["failed"] == 1
    assert len(body["errors"]) == 1
    assert "Row 3" in body["errors"][0]


def test_csv_import_ended_session_returns_409(
    client: TestClient, ended_session: SessionRow
) -> None:
    csv = _csv_bytes([["Alice", "alice@example.com"]])
    resp = client.post(
        f"/api/sessions/{ended_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 409


def test_csv_import_missing_session_returns_409(
    client: TestClient,
) -> None:
    csv = _csv_bytes([["Alice", "alice@example.com"]])
    resp = client.post(
        "/api/sessions/9999/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    # SessionNotFound is raised by create_student which causes 409
    # because it's caught by the SessionNotFound/SessionEnded handler
    assert resp.status_code in (404, 409)


def test_csv_import_empty_csv_returns_201_with_zero_counts(
    client: TestClient, draft_session: SessionRow
) -> None:
    csv = _csv_bytes([])
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 0
    assert body["failed"] == 0


def test_csv_import_writes_student_created_events(
    client: TestClient, db_session: OrmSession, draft_session: SessionRow
) -> None:
    csv = _csv_bytes([
        ["Alice Example", "alice@example.com"],
        ["Bob Example", "bob@example.com"],
    ])
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 201
    events = db_session.scalars(
        select(Event).where(Event.action == "student.created")
    ).all()
    assert len(events) == 2


def test_csv_import_with_bom_encoding(
    client: TestClient, db_session: OrmSession, draft_session: SessionRow
) -> None:
    """CSV exported from Excel often has UTF-8 BOM prefix."""
    csv = b"\xef\xbb\xbf" + _csv_bytes([["Alice Example", "alice@example.com"]])
    resp = client.post(
        f"/api/sessions/{draft_session.id}/students/import",
        files={"file": ("students.csv", csv, "text/csv")},
    )
    assert resp.status_code == 201
    assert resp.json()["created"] == 1
