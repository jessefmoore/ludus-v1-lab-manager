"""Tests for baseline snapshot creation (app.services.snapshots)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from app.models.event import Event
from app.services import snapshots as snap
from app.services.exceptions import LudusError

RANGE_YAML = "ludus:\n  - {vm_name: dc, ram_gb: 8, cpus: 4}\n"


class FakeLudus:
    """Scriptable range states + snapshot_create recorder."""

    def __init__(self, states: dict[str, str]) -> None:
        self.states = states  # userID -> rangeState
        self.snapshot_calls: list[tuple[str, str]] = []  # (name, userID)
        self.create_error: Exception | None = None

    def range_list(self) -> list[dict]:
        return [{"userID": uid, "rangeState": st} for uid, st in self.states.items()]

    def snapshot_create(self, name, *, user_id=None, description="", include_ram=True, vmids=None):
        if self.create_error is not None:
            raise self.create_error
        self.snapshot_calls.append((name, user_id))
        return {"result": "ok"}


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


def _lab(db: OrmSession) -> LabTemplate:
    lab = LabTemplate(
        name="Lab", range_config_yaml=RANGE_YAML,
        default_mode=LabTemplateMode.dedicated, ludus_server="default",
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def _session(db, lab, *, mode=SessionMode.dedicated, shared_range_id=None) -> SessionRow:
    row = SessionRow(
        name="S", lab_template_id=lab.id, mode=mode,
        status=SessionStatus.active, shared_range_id=shared_range_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _student(db, session, uid, status=StudentStatus.ready) -> Student:
    s = Student(
        session_id=session.id, full_name=uid, email=f"{uid}@example.com",
        ludus_userid=uid, invite_token=f"tok-{uid}", status=status,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_snapshots_deployed_ranges_only(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab)
    _student(db_session, row, "u1")
    _student(db_session, row, "u2")
    fake = FakeLudus({"u1": "SUCCESS", "u2": "DEPLOYING"})

    result = snap.ensure_baseline_snapshots(db_session, fake, row.id, "snapshot-1")

    assert fake.snapshot_calls == [("snapshot-1", "u1")]  # only the SUCCESS range
    assert result.created == 1 and result.pending == 1
    assert result.done is False  # u2 still deploying


def test_snapshots_idempotent_second_pass(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab)
    _student(db_session, row, "u1")
    fake = FakeLudus({"u1": "SUCCESS"})

    first = snap.ensure_baseline_snapshots(db_session, fake, row.id, "snapshot-1")
    second = snap.ensure_baseline_snapshots(db_session, fake, row.id, "snapshot-1")

    assert first.created == 1
    assert second.created == 0 and second.existing == 1
    assert len(fake.snapshot_calls) == 1  # not re-created
    assert second.done is True


def test_snapshots_ignores_pending_students(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab)
    _student(db_session, row, "u1", status=StudentStatus.pending)
    fake = FakeLudus({"u1": "SUCCESS"})
    result = snap.ensure_baseline_snapshots(db_session, fake, row.id, "snapshot-1")
    assert fake.snapshot_calls == []
    assert result.created == 0 and result.done is True


def test_snapshots_shared_range_once(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab, mode=SessionMode.shared, shared_range_id="lead")
    _student(db_session, row, "lead")
    _student(db_session, row, "u2")
    fake = FakeLudus({"lead": "SUCCESS", "u2": "SUCCESS"})

    result = snap.ensure_baseline_snapshots(db_session, fake, row.id, "snapshot-1")

    assert fake.snapshot_calls == [("snapshot-1", "lead")]  # only the shared range
    assert result.created == 1 and result.done is True
    # A shared-baseline event with no student_id is recorded.
    ev = db_session.execute(
        select(Event).where(Event.action == "session.baseline_snapshotted")
    ).scalars().all()
    assert len(ev) == 1 and ev[0].student_id is None


def test_snapshots_preexisting_name_counts_as_existing(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab)
    _student(db_session, row, "u1")
    fake = FakeLudus({"u1": "SUCCESS"})
    fake.create_error = LudusError("snapshot already exists", status_code=400)
    result = snap.ensure_baseline_snapshots(db_session, fake, row.id, "snapshot-1")
    assert result.existing == 1 and result.failed == 0 and result.created == 0


def test_snapshots_create_failure_counted(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session(db_session, lab)
    _student(db_session, row, "u1")
    fake = FakeLudus({"u1": "SUCCESS"})
    fake.create_error = LudusError("proxmox busy", status_code=500)
    result = snap.ensure_baseline_snapshots(db_session, fake, row.id, "snapshot-1")
    assert result.failed == 1 and result.done is False
