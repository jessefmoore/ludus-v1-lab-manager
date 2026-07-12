"""Tests for session rebuild / teardown (app.services.teardown)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.db import Base
from app.models import (
    LabTemplate,
    LabTemplateMode,
    SessionMode,
    SessionStatus,
    Student,
    StudentStatus,
)
from app.models import Session as SessionRow
from app.services import teardown as td
from app.services.exceptions import LudusError, LudusNotFound

RANGE_YAML = "ludus:\n  - {vm_name: dc, ram_gb: 8, cpus: 4}\n"


class FakeLudus:
    """Records range_destroy / user_rm; can raise per userid."""

    def __init__(self) -> None:
        self.range_destroy_calls: list[str] = []
        self.user_rm_calls: list[str] = []
        self.errors: dict[str, Exception] = {}  # userid -> exception to raise

    def range_destroy(self, *, user_id: str | None = None, force: bool = False) -> None:
        if user_id in self.errors:
            raise self.errors[user_id]
        self.range_destroy_calls.append(user_id or "")

    def user_rm(self, userid: str) -> None:
        if userid in self.errors:
            raise self.errors[userid]
        self.user_rm_calls.append(userid)


class FakeRegistry:
    def __init__(self, fake: FakeLudus) -> None:
        self._fake = fake

    def get(self, name: str = "default") -> FakeLudus:
        if name != "default":
            raise ValueError(f"Unknown Ludus server '{name}'")
        return self._fake


@pytest.fixture
def db_session() -> Iterator[OrmSession]:
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
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
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="testing", app_secret_key="x", admin_email="a@example.com",
        admin_password="super-secret-test-pw", ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="k", config_storage_dir=str(tmp_path), _env_file=None,
    )


def _lab(db: OrmSession) -> LabTemplate:
    lab = LabTemplate(
        name="Lab", range_config_yaml=RANGE_YAML,
        default_mode=LabTemplateMode.dedicated, ludus_server="default",
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def _session(
    db: OrmSession, lab: LabTemplate, *, mode: SessionMode,
    status: SessionStatus = SessionStatus.active, shared_range_id: str | None = None,
) -> SessionRow:
    row = SessionRow(
        name="S", lab_template_id=lab.id, mode=mode, status=status,
        shared_range_id=shared_range_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _student(
    db: OrmSession, session: SessionRow, *, uid: str,
    status: StudentStatus = StudentStatus.ready, wg: str | None = None,
) -> Student:
    s = Student(
        session_id=session.id, full_name=uid, email=f"{uid}@example.com",
        ludus_userid=uid, invite_token=f"tok-{uid}", status=status,
        range_id=uid if status == StudentStatus.ready else None, wg_config_path=wg,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# --- rebuild -----------------------------------------------------------------


def test_rebuild_dedicated_destroys_each_range_keeps_users(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.dedicated)
    _student(db_session, row, uid="u1")
    _student(db_session, row, uid="u2")
    fake = FakeLudus()

    result = td.rebuild_session(db_session, row.id, settings, registry=FakeRegistry(fake))

    assert sorted(fake.range_destroy_calls) == ["u1", "u2"]
    assert fake.user_rm_calls == []  # users kept
    assert result.cleaned == 2 and result.failed == 0
    db_session.refresh(row)
    assert all(s.status == StudentStatus.pending and s.range_id is None for s in row.students)
    assert row.status == SessionStatus.active  # unchanged


def test_rebuild_shared_destroys_one_range_and_clears_id(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.shared, shared_range_id="lead")
    _student(db_session, row, uid="lead")
    _student(db_session, row, uid="u2")
    fake = FakeLudus()

    result = td.rebuild_session(db_session, row.id, settings, registry=FakeRegistry(fake))

    assert fake.range_destroy_calls == ["lead"]  # only the shared range
    db_session.refresh(row)
    assert row.shared_range_id is None
    assert result.cleaned == 2
    assert all(s.status == StudentStatus.pending for s in row.students)


def test_rebuild_skips_pending_students(db_session: OrmSession, settings: Settings) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.dedicated)
    _student(db_session, row, uid="u1", status=StudentStatus.pending)
    fake = FakeLudus()
    result = td.rebuild_session(db_session, row.id, settings, registry=FakeRegistry(fake))
    assert fake.range_destroy_calls == []
    assert result.skipped == 1 and result.cleaned == 0


def test_rebuild_ended_session_raises(db_session: OrmSession, settings: Settings) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.dedicated, status=SessionStatus.ended)
    with pytest.raises(ValueError, match="ended"):
        td.rebuild_session(db_session, row.id, settings, registry=FakeRegistry(FakeLudus()))


# --- teardown ----------------------------------------------------------------


def test_teardown_removes_users_and_ends_session(
    db_session: OrmSession, settings: Settings, tmp_path: Path
) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.dedicated)
    cfg = tmp_path / "u1.conf"
    cfg.write_text("[Interface]\n")
    _student(db_session, row, uid="u1", wg=str(cfg))
    _student(db_session, row, uid="u2")
    fake = FakeLudus()

    result = td.teardown_session(db_session, row.id, settings, registry=FakeRegistry(fake))

    assert sorted(fake.user_rm_calls) == ["u1", "u2"]
    # Ranges must be destroyed too, so user_rm doesn't fail on a non-empty pool.
    assert sorted(fake.range_destroy_calls) == ["u1", "u2"]
    assert result.cleaned == 2 and result.failed == 0
    assert not cfg.exists()  # config unlinked
    db_session.refresh(row)
    assert row.status == SessionStatus.ended
    assert row.shared_range_id is None
    for s in row.students:
        assert s.status == StudentStatus.pending
        assert s.range_id is None and s.wg_config_path is None


def test_teardown_treats_missing_user_as_cleaned(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.dedicated)
    _student(db_session, row, uid="u1")
    fake = FakeLudus()
    fake.errors["u1"] = LudusNotFound("no such user", status_code=404)
    result = td.teardown_session(db_session, row.id, settings, registry=FakeRegistry(fake))
    assert result.cleaned == 1 and result.failed == 0
    db_session.refresh(row)
    assert row.status == SessionStatus.ended


def test_teardown_marks_failed_student_error_but_still_ends(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.dedicated)
    _student(db_session, row, uid="u1")
    _student(db_session, row, uid="u2")
    fake = FakeLudus()
    fake.errors["u1"] = LudusError("proxmox busy", status_code=500)
    result = td.teardown_session(db_session, row.id, settings, registry=FakeRegistry(fake))
    assert result.failed == 1 and result.cleaned == 1
    db_session.refresh(row)
    assert row.status == SessionStatus.ended  # ended despite one failure
    statuses = {s.ludus_userid: s.status for s in row.students}
    assert statuses["u1"] == StudentStatus.error
    assert statuses["u2"] == StudentStatus.pending


def test_teardown_unknown_server_raises_value_error(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = LabTemplate(
        name="L", range_config_yaml=RANGE_YAML,
        default_mode=LabTemplateMode.dedicated, ludus_server="ghost",
    )
    db_session.add(lab)
    db_session.commit()
    db_session.refresh(lab)
    row = _session(db_session, lab, mode=SessionMode.dedicated)
    _student(db_session, row, uid="u1")
    with pytest.raises(ValueError, match="Unknown Ludus server"):
        td.teardown_session(db_session, row.id, settings, registry=FakeRegistry(FakeLudus()))
