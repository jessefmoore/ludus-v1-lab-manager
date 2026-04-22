"""Tests for ``POST /api/sessions/{session_id}/provision``.

Fixture pattern mirrors ``test_students_api`` / ``test_sessions_api``:
in-memory SQLite with ``StaticPool``, ``get_current_user`` +
``get_ludus_client`` overridden. The ``config_storage_dir`` setting is
pointed at ``tmp_path`` so file-system side effects land in an isolated
temporary directory.

``FakeLudus`` records every call AND lets each method's behavior be
scripted per-userid via dicts of overrides - this gives per-test
granular control over which student's ``user_wireguard`` times out, etc.
"""

from __future__ import annotations

import stat
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

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
from app.core.deps import get_current_user, get_ludus_client_registry
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
from app.services.exceptions import LudusError, LudusTimeout, LudusUserExists

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"
PUBLIC_BASE_URL = "https://lab.example.test"

WG_CONFIG_TEMPLATE = "[Interface]\nPrivateKey = {userid}-priv\n"


# ---------------------------------------------------------------------------
# FakeLudus - scriptable per-userid
# ---------------------------------------------------------------------------


class FakeLudus:
    """Stand-in for ``LudusClient`` used across all provision tests.

    Each method records its calls to the matching ``*_calls`` list and
    consults the matching ``*_overrides`` dict (``userid -> exception or
    value``) so individual tests can make a single student fail without
    affecting the rest of the batch.
    """

    def __init__(self) -> None:
        self._ranges: list[dict] = []

        self.user_add_calls: list[dict[str, str]] = []
        self.user_add_overrides: dict[str, Exception] = {}

        self.range_assign_calls: list[dict[str, str]] = []
        self.range_assign_overrides: dict[str, Exception] = {}

        self.range_deploy_calls: list[dict[str, str]] = []
        self.range_deploy_overrides: dict[str, Exception] = {}

        self.user_wireguard_calls: list[str] = []
        # Either an Exception instance (raised) or a string (returned).
        self.user_wireguard_overrides: dict[str, Exception | str] = {}

    def user_add(self, userid: str, name: str, email: str) -> dict[str, Any]:
        self.user_add_calls.append({"userid": userid, "name": name, "email": email})
        exc = self.user_add_overrides.get(userid)
        if exc is not None:
            raise exc
        return {"userID": userid, "name": name, "email": email}

    def range_list(self) -> list[dict]:
        return self._ranges

    def range_assign(self, userid: str, range_id: str) -> None:
        self.range_assign_calls.append({"userid": userid, "range_id": range_id})
        exc = self.range_assign_overrides.get(userid)
        if exc is not None:
            raise exc

    def range_deploy(self, userid: str, config_yaml: str) -> None:
        self.range_deploy_calls.append({"userid": userid, "config_yaml": config_yaml})
        exc = self.range_deploy_overrides.get(userid)
        if exc is not None:
            raise exc

    def user_wireguard(self, userid: str) -> str:
        self.user_wireguard_calls.append(userid)
        override = self.user_wireguard_overrides.get(userid)
        if isinstance(override, Exception):
            raise override
        if isinstance(override, str):
            return override
        return WG_CONFIG_TEMPLATE.format(userid=userid)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email=ADMIN_EMAIL,
        admin_password=ADMIN_PASSWORD,
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key",
        public_base_url=PUBLIC_BASE_URL,
        config_storage_dir=str(tmp_path),
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
        password_hash="irrelevant-for-provision-tests",
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
        range_config_yaml="ludus:\n  - vm_name: KALI\n",
        default_mode=LabTemplateMode.dedicated,
        ludus_server="default",
        entry_point_vm="KALI",
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


class FakeRegistry:
    """Wraps a FakeLudus so it can be used as a ``LudusClientRegistry``."""

    def __init__(self, fake: FakeLudus) -> None:
        self._fake = fake

    def get(self, name: str = "default") -> FakeLudus:  # type: ignore[override]
        if name != "default":
            raise ValueError(f"Unknown Ludus server '{name}'")
        return self._fake

    @property
    def server_names(self) -> list[str]:
        return ["default"]


@pytest.fixture
def fake_ludus() -> FakeLudus:
    return FakeLudus()


@pytest.fixture
def app_factory(
    db_session: OrmSession,
    settings: Settings,
    fake_user: User,
    fake_ludus: FakeLudus,
) -> Callable[..., FastAPI]:
    def _build(authenticated: bool = True) -> FastAPI:
        app = FastAPI()
        app.include_router(sessions_router)

        def _override_get_db() -> Iterator[OrmSession]:
            yield db_session

        def _override_get_settings() -> Settings:
            return settings

        fake_registry = FakeRegistry(fake_ludus)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_settings] = _override_get_settings
        app.dependency_overrides[get_ludus_client_registry] = lambda: fake_registry
        if authenticated:
            app.dependency_overrides[get_current_user] = lambda: fake_user
        return app

    return _build


@pytest.fixture
def client(app_factory: Callable[..., FastAPI]) -> Iterator[TestClient]:
    with TestClient(app_factory(authenticated=True)) as tc:
        yield tc


def _make_session(
    db: OrmSession,
    lab_template: LabTemplate,
    *,
    mode: SessionMode = SessionMode.shared,
    shared_range_id: str | None = "7",
    status: SessionStatus = SessionStatus.draft,
    name: str = "Spring 2026 Cohort",
) -> SessionRow:
    row = SessionRow(
        name=name,
        lab_template_id=lab_template.id,
        mode=mode,
        shared_range_id=shared_range_id,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_student(
    db: OrmSession,
    session_row: SessionRow,
    *,
    ludus_userid: str,
    invite_token: str,
    full_name: str = "Alice Example",
    email: str = "alice@example.com",
    status: StudentStatus = StudentStatus.pending,
    wg_config_path: str | None = None,
    range_id: str | None = None,
) -> Student:
    student = Student(
        session_id=session_row.id,
        full_name=full_name,
        email=email,
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
# tests
# ---------------------------------------------------------------------------


def test_provision_missing_session_returns_404(client: TestClient) -> None:
    resp = client.post("/api/sessions/99999/provision")
    assert resp.status_code == 404


def test_provision_session_with_no_students_returns_zero_counts(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    fake_ludus: FakeLudus,
) -> None:
    session_row = _make_session(db_session, lab_template)

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"provisioned": 0, "failed": 0, "skipped": 0, "students": []}

    # Ludus never touched.
    assert fake_ludus.user_add_calls == []
    assert fake_ludus.user_wireguard_calls == []


def test_provision_shared_session_happy_path_two_students(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    settings: Settings,
    fake_ludus: FakeLudus,
) -> None:
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.shared,
        shared_range_id="42",
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
        full_name="Alice",
        email="alice@example.com",
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="bob-bbb",
        invite_token="b" * 32,
        full_name="Bob",
        email="bob@example.com",
    )

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provisioned"] == 2
    assert body["failed"] == 0
    assert body["skipped"] == 0
    assert len(body["students"]) == 2

    # All students persisted as ready + range_id bound to shared_range_id.
    db_session.expire_all()
    rows = db_session.execute(select(Student).order_by(Student.id)).scalars().all()
    assert [r.status for r in rows] == [StudentStatus.ready, StudentStatus.ready]
    assert [r.range_id for r in rows] == ["42", "42"]

    # Session promoted to active.
    db_session.refresh(session_row)
    assert session_row.status == SessionStatus.active

    # Files exist on disk with mode 0o600 and parent dir mode 0o700.
    storage_root = Path(settings.config_storage_dir)
    session_dir = storage_root / str(session_row.id)
    for userid in ("alice-aaa", "bob-bbb"):
        cfg_path = session_dir / f"{userid}.conf"
        assert cfg_path.exists()
        assert stat.S_IMODE(cfg_path.stat().st_mode) == 0o600
        assert cfg_path.read_text().startswith("[Interface]")

    # Verify Ludus call log.
    assert {c["userid"] for c in fake_ludus.user_add_calls} == {"alice-aaa", "bob-bbb"}
    assert {c["userid"] for c in fake_ludus.range_assign_calls} == {"alice-aaa", "bob-bbb"}
    assert fake_ludus.range_deploy_calls == []
    assert set(fake_ludus.user_wireguard_calls) == {"alice-aaa", "bob-bbb"}

    # Provisioned events emitted.
    provisioned_events = (
        db_session.execute(select(Event).where(Event.action == "student.provisioned"))
        .scalars()
        .all()
    )
    assert len(provisioned_events) == 2


def test_provision_shared_session_wireguard_timeout_marks_error(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    settings: Settings,
    fake_ludus: FakeLudus,
) -> None:
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.shared,
        shared_range_id="42",
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="bob-bbb",
        invite_token="b" * 32,
    )

    fake_ludus.user_wireguard_overrides["bob-bbb"] = LudusTimeout("wireguard endpoint timed out")

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provisioned"] == 1
    assert body["failed"] == 1
    assert body["skipped"] == 0

    db_session.expire_all()
    alice = db_session.execute(
        select(Student).where(Student.ludus_userid == "alice-aaa")
    ).scalar_one()
    bob = db_session.execute(select(Student).where(Student.ludus_userid == "bob-bbb")).scalar_one()
    assert alice.status == StudentStatus.ready
    assert bob.status == StudentStatus.error
    assert bob.wg_config_path is None

    # Only alice's config file exists.
    storage_root = Path(settings.config_storage_dir)
    session_dir = storage_root / str(session_row.id)
    assert (session_dir / "alice-aaa.conf").exists()
    assert not (session_dir / "bob-bbb.conf").exists()

    # Failure event carries the step + repr of the exception.
    failure = db_session.execute(
        select(Event).where(Event.action == "student.provision_failed")
    ).scalar_one()
    assert failure.details_json is not None
    assert failure.details_json["step"] == "user_wireguard"
    assert "LudusTimeout" in failure.details_json["reason"]

    # Session still active because alice succeeded.
    db_session.refresh(session_row)
    assert session_row.status == SessionStatus.active


def test_provision_ludus_user_exists_is_benign(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    fake_ludus: FakeLudus,
) -> None:
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.shared,
        shared_range_id="42",
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
    )

    fake_ludus.user_add_overrides["alice-aaa"] = LudusUserExists(
        "user already exists", status_code=409
    )

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provisioned"] == 1
    assert body["failed"] == 0

    # range_assign + user_wireguard must have been attempted regardless.
    assert fake_ludus.range_assign_calls == [{"userid": "alice-aaa", "range_id": "42"}]
    assert fake_ludus.user_wireguard_calls == ["alice-aaa"]

    db_session.expire_all()
    alice = db_session.execute(
        select(Student).where(Student.ludus_userid == "alice-aaa")
    ).scalar_one()
    assert alice.status == StudentStatus.ready


def test_provision_dedicated_session_calls_range_deploy(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    fake_ludus: FakeLudus,
) -> None:
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.dedicated,
        shared_range_id=None,
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
    )

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provisioned"] == 1

    # range_deploy called, range_assign NOT called.
    assert fake_ludus.range_assign_calls == []
    assert fake_ludus.range_deploy_calls == [
        {
            "userid": "alice-aaa",
            "config_yaml": lab_template.range_config_yaml,
        }
    ]


def test_provision_is_idempotent_second_call_skips_ready_students(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    fake_ludus: FakeLudus,
) -> None:
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.shared,
        shared_range_id="42",
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
    )

    resp1 = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp1.status_code == 200
    assert resp1.json()["provisioned"] == 1

    # Snapshot call counts, then re-invoke.
    before_add = len(fake_ludus.user_add_calls)
    before_assign = len(fake_ludus.range_assign_calls)
    before_wg = len(fake_ludus.user_wireguard_calls)

    resp2 = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["provisioned"] == 0
    assert body2["failed"] == 0
    assert body2["skipped"] == 1

    # Not a single additional Ludus call for the already-ready student.
    assert len(fake_ludus.user_add_calls) == before_add
    assert len(fake_ludus.range_assign_calls) == before_assign
    assert len(fake_ludus.user_wireguard_calls) == before_wg


def test_provision_shared_session_missing_range_id_errors_everyone(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    fake_ludus: FakeLudus,
) -> None:
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.shared,
        shared_range_id=None,
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="bob-bbb",
        invite_token="b" * 32,
    )

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provisioned"] == 0
    assert body["failed"] == 2
    assert body["skipped"] == 0

    # No one reached range_assign/user_wireguard.
    assert fake_ludus.range_assign_calls == []
    assert fake_ludus.user_wireguard_calls == []

    db_session.expire_all()
    rows = db_session.execute(select(Student).order_by(Student.id)).scalars().all()
    assert [r.status for r in rows] == [StudentStatus.error, StudentStatus.error]

    # Session status is NOT active because nothing succeeded.
    db_session.refresh(session_row)
    assert session_row.status == SessionStatus.draft

    # Failure events name the reason.
    failures = (
        db_session.execute(select(Event).where(Event.action == "student.provision_failed"))
        .scalars()
        .all()
    )
    assert len(failures) == 2
    for ev in failures:
        assert ev.details_json is not None
        assert "shared_range_id" in ev.details_json["reason"]


def test_provision_parent_directory_has_mode_0o700(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    settings: Settings,
) -> None:
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.shared,
        shared_range_id="42",
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
    )

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200

    parent = Path(settings.config_storage_dir) / str(session_row.id)
    assert parent.is_dir()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700


def test_provision_user_add_error_short_circuits_student(
    client: TestClient,
    db_session: OrmSession,
    lab_template: LabTemplate,
    fake_ludus: FakeLudus,
) -> None:
    """A non-``LudusUserExists`` failure on ``user_add`` must NOT proceed."""
    session_row = _make_session(
        db_session,
        lab_template,
        mode=SessionMode.shared,
        shared_range_id="42",
    )
    _make_student(
        db_session,
        session_row,
        ludus_userid="alice-aaa",
        invite_token="a" * 32,
    )

    fake_ludus.user_add_overrides["alice-aaa"] = LudusError(
        "internal server error", status_code=500
    )

    resp = client.post(f"/api/sessions/{session_row.id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provisioned"] == 0
    assert body["failed"] == 1

    # Downstream calls NOT attempted for this student.
    assert fake_ludus.range_assign_calls == []
    assert fake_ludus.user_wireguard_calls == []

    failure = db_session.execute(
        select(Event).where(Event.action == "student.provision_failed")
    ).scalar_one()
    assert failure.details_json is not None
    assert failure.details_json["step"] == "user_add"
