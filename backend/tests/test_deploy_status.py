"""Tests for the deploy-status reconciler (deploying -> ready/error)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.db import Base
from app.models import LabTemplate, LabTemplateMode, SessionMode, SessionStatus, Student, StudentStatus
from app.models import Session as SessionRow
from app.services import deploy_status as deploy_status_service
from app.services.exceptions import LudusError


class FakeLudus:
    """Range-state stand-in: ``states[userid]`` -> dict returned by range_get_vms."""

    def __init__(self, states: dict[str, dict | Exception]) -> None:
        self.states = states
        self.calls: list[str] = []

    def range_get_vms(self, *, user_id: str) -> dict:
        self.calls.append(user_id)
        val = self.states.get(user_id)
        if isinstance(val, Exception):
            raise val
        if val is None:
            raise LudusError(f"User {user_id} not found", status_code=400)
        return val


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email="admin@example.com",
        admin_password="pw",
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="k",
        public_base_url="https://mgr.test",
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


def _seed(
    db: OrmSession,
    *,
    mode: SessionMode,
    shared_range_id: str | None,
    students: list[tuple[str, StudentStatus]],
) -> SessionRow:
    template = LabTemplate(
        name="Lab",
        description="",
        range_config_yaml="ludus:\n  - vm_name: KALI\n",
        default_mode=LabTemplateMode.shared,
        ludus_server="default",
        entry_point_vm="KALI",
    )
    db.add(template)
    db.flush()
    session_row = SessionRow(
        name="S",
        lab_template_id=template.id,
        mode=mode,
        shared_range_id=shared_range_id,
        status=SessionStatus.provisioning,
    )
    db.add(session_row)
    db.flush()
    for i, (userid, st) in enumerate(students):
        db.add(
            Student(
                session_id=session_row.id,
                full_name=userid,
                email=f"{userid}@x.test",
                ludus_userid=userid,
                invite_token=f"{i:0<32}",
                status=st,
                range_id=shared_range_id if mode == SessionMode.shared else userid,
            )
        )
    db.commit()
    return session_row


_UP = {"rangeState": "SUCCESS", "VMs": [{"name": "KALI", "poweredOn": True}]}
_DEPLOYING = {"rangeState": "DEPLOYING", "VMs": [{"name": "KALI", "poweredOn": False}]}
_PARTIAL = {"rangeState": "SUCCESS", "VMs": [{"name": "a", "poweredOn": True}, {"name": "b", "poweredOn": False}]}
_ERRORED = {"rangeState": "ERROR", "VMs": []}


def test_deploying_promotes_to_ready_when_range_up(db_session: OrmSession) -> None:
    s = _seed(
        db_session, mode=SessionMode.shared, shared_range_id="owner",
        students=[("owner", StudentStatus.deploying), ("share", StudentStatus.deploying)],
    )
    fake = FakeLudus({"owner": _UP})
    res = deploy_status_service.reconcile_deploy_status(db_session, s.id, ludus=fake)

    assert res.ready == 2 and res.deploying == 0 and res.done is True
    db_session.expire_all()
    rows = db_session.execute(select(Student).order_by(Student.id)).scalars().all()
    assert all(r.status == StudentStatus.ready for r in rows)
    assert db_session.get(SessionRow, s.id).status == SessionStatus.active
    # Shared range queried once, not once per student (cached).
    assert fake.calls.count("owner") <= 2  # confirmed_up + state probe


def test_deploying_stays_while_range_building(db_session: OrmSession) -> None:
    s = _seed(
        db_session, mode=SessionMode.shared, shared_range_id="owner",
        students=[("owner", StudentStatus.deploying)],
    )
    fake = FakeLudus({"owner": _DEPLOYING})
    res = deploy_status_service.reconcile_deploy_status(db_session, s.id, ludus=fake)

    assert res.deploying == 1 and res.ready == 0 and res.done is False
    assert db_session.get(SessionRow, s.id).status == SessionStatus.provisioning


def test_partial_power_on_stays_deploying(db_session: OrmSession) -> None:
    s = _seed(
        db_session, mode=SessionMode.dedicated, shared_range_id=None,
        students=[("stu", StudentStatus.deploying)],
    )
    fake = FakeLudus({"stu": _PARTIAL})
    res = deploy_status_service.reconcile_deploy_status(db_session, s.id, ludus=fake)

    # SUCCESS but not every VM powered on -> not confirmed.
    assert res.deploying == 1 and res.done is False


def test_error_state_marks_student_error(db_session: OrmSession) -> None:
    s = _seed(
        db_session, mode=SessionMode.dedicated, shared_range_id=None,
        students=[("stu", StudentStatus.deploying)],
    )
    fake = FakeLudus({"stu": _ERRORED})
    res = deploy_status_service.reconcile_deploy_status(db_session, s.id, ludus=fake)

    assert res.failed == 1 and res.done is True
    db_session.expire_all()
    row = db_session.execute(select(Student)).scalars().one()
    assert row.status == StudentStatus.error


def test_non_deploying_students_untouched(db_session: OrmSession) -> None:
    s = _seed(
        db_session, mode=SessionMode.dedicated, shared_range_id=None,
        students=[("a", StudentStatus.ready), ("b", StudentStatus.pending)],
    )
    fake = FakeLudus({})  # would raise if queried
    res = deploy_status_service.reconcile_deploy_status(db_session, s.id, ludus=fake)

    assert res.ready == 0 and res.deploying == 0 and res.done is True
    assert fake.calls == []  # nothing was deploying, so no Ludus calls
