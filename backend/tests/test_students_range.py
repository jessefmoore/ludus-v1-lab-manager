"""Tests for remove_student_range (destroy range, keep user)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
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
from app.services import students as students_service
from app.services.exceptions import LudusError, LudusNotFound


class FakeLudus:
    def __init__(self) -> None:
        self.range_destroy_calls: list[str] = []
        self.user_rm_calls: list[str] = []
        self.error: Exception | None = None

    def range_destroy(self, *, user_id: str | None = None, force: bool = False) -> None:
        if self.error is not None:
            raise self.error
        self.range_destroy_calls.append(user_id or "")

    def user_rm(self, userid: str) -> None:  # must NOT be called
        self.user_rm_calls.append(userid)


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


def _student(db: OrmSession, *, status: StudentStatus, wg: str | None = "/tmp/x.conf") -> Student:
    lab = LabTemplate(
        name="L", range_config_yaml="ludus: []\n",
        default_mode=LabTemplateMode.dedicated, ludus_server="default",
    )
    db.add(lab)
    db.commit()
    row = SessionRow(name="S", lab_template_id=lab.id, mode=SessionMode.dedicated,
                     status=SessionStatus.active)
    db.add(row)
    db.commit()
    s = Student(
        session_id=row.id, full_name="A", email="a@example.com", ludus_userid="u1",
        invite_token="tok", status=status, range_id="u1" if status == StudentStatus.ready else None,
        wg_config_path=wg,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_remove_range_destroys_range_keeps_user(db_session: OrmSession) -> None:
    s = _student(db_session, status=StudentStatus.ready)
    fake = FakeLudus()
    out = students_service.remove_student_range(db_session, fake, s.id)
    assert fake.range_destroy_calls == ["u1"]
    assert fake.user_rm_calls == []           # user preserved
    assert out.status == StudentStatus.range_removed
    assert out.range_id is None
    assert out.wg_config_path == "/tmp/x.conf"  # config kept


def test_remove_range_pending_is_noop(db_session: OrmSession) -> None:
    s = _student(db_session, status=StudentStatus.pending)
    fake = FakeLudus()
    students_service.remove_student_range(db_session, fake, s.id)
    assert fake.range_destroy_calls == []


def test_remove_range_missing_range_is_success(db_session: OrmSession) -> None:
    s = _student(db_session, status=StudentStatus.ready)
    fake = FakeLudus()
    fake.error = LudusNotFound("no range", status_code=404)
    out = students_service.remove_student_range(db_session, fake, s.id)
    assert out.status == StudentStatus.range_removed  # treated as already-gone


def test_remove_range_error_raises_removal_failed(db_session: OrmSession) -> None:
    s = _student(db_session, status=StudentStatus.ready)
    fake = FakeLudus()
    fake.error = LudusError("proxmox busy", status_code=500)
    with pytest.raises(students_service.LudusRemovalFailed):
        students_service.remove_student_range(db_session, fake, s.id)
