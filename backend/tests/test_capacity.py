"""Tests for the host-capacity service (app.services.capacity).

Allocation is derived from *this app's own sessions* - only live
(active/provisioning) sessions on the target server count, scaled by mode
exactly like the provisioning quota check. Capacity comes from env (default)
or the ludus_servers row (managed).
"""

from __future__ import annotations

from collections.abc import Iterator

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
from app.models.ludus_server import LudusServer
from app.services import capacity as cap
from app.services.resources import RangeResources

# One range = 4+2 CPU, 8+4 GB = 6 CPU / 12 GB.
RANGE_YAML = (
    "ludus:\n"
    "  - {vm_name: dc, ram_gb: 8, cpus: 4}\n"
    "  - {vm_name: kali, ram_gb: 4, cpus: 2}\n"
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


def _settings(**over) -> Settings:
    base = {
        "app_env": "testing",
        "app_secret_key": "unit-test-secret",
        "admin_email": "a@example.com",
        "admin_password": "super-secret-test-pw",
        "ludus_default_url": "https://ludus.test:8080",
        "ludus_default_api_key": "unit-test-api-key",
        "_env_file": None,
    }
    base.update(over)
    return Settings(**base)


def _lab(db: OrmSession, *, server: str = "default", yaml_text: str = RANGE_YAML) -> LabTemplate:
    lab = LabTemplate(
        name="Lab",
        range_config_yaml=yaml_text,
        default_mode=LabTemplateMode.dedicated,
        ludus_server=server,
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def _session(
    db: OrmSession,
    lab: LabTemplate,
    *,
    mode: SessionMode,
    status: SessionStatus,
    n_students: int,
) -> SessionRow:
    row = SessionRow(
        name="S", lab_template_id=lab.id, mode=mode, status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    for i in range(n_students):
        db.add(
            Student(
                session_id=row.id, full_name=f"S{i}", email=f"s{i}@example.com",
                ludus_userid=f"u{i}_{row.id}", invite_token=f"t{i}_{row.id}",
                # ready = a deployed range that counts toward allocation.
                status=StudentStatus.ready,
            )
        )
    db.commit()
    return row


def test_allocation_sums_active_dedicated(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    _session(db_session, lab, mode=SessionMode.dedicated, status=SessionStatus.active, n_students=2)
    alloc = cap.compute_sessions_allocation(db_session, "default")
    # dedicated 2 students x (6 CPU / 12 GB) = 12 CPU / 24 GB.
    assert alloc.resources == RangeResources(cpus=12, ram_gb=24, vm_count=4)
    assert alloc.session_count == 1


def test_allocation_excludes_removed_ranges(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session(
        db_session, lab, mode=SessionMode.dedicated,
        status=SessionStatus.active, n_students=3,
    )
    # Remove one student's range -> it no longer consumes resources.
    removed = row.students[0]
    removed.status = StudentStatus.range_removed
    db_session.commit()
    alloc = cap.compute_sessions_allocation(db_session, "default")
    # 2 deployed x 6 CPU / 12 GB = 12 / 24 (the removed one drops out).
    assert alloc.resources == RangeResources(cpus=12, ram_gb=24, vm_count=4)


def test_allocation_shared_counts_one_range(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    _session(db_session, lab, mode=SessionMode.shared, status=SessionStatus.active, n_students=10)
    alloc = cap.compute_sessions_allocation(db_session, "default")
    assert alloc.resources == RangeResources(cpus=6, ram_gb=12, vm_count=2)


def test_allocation_excludes_draft_and_ended(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    _session(db_session, lab, mode=SessionMode.dedicated, status=SessionStatus.draft, n_students=5)
    _session(db_session, lab, mode=SessionMode.dedicated, status=SessionStatus.ended, n_students=5)
    alloc = cap.compute_sessions_allocation(db_session, "default")
    assert alloc.resources == RangeResources()  # nothing consuming
    assert alloc.session_count == 0


def test_allocation_includes_provisioning(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    _session(
        db_session, lab, mode=SessionMode.dedicated,
        status=SessionStatus.provisioning, n_students=1,
    )
    alloc = cap.compute_sessions_allocation(db_session, "default")
    assert alloc.resources == RangeResources(cpus=6, ram_gb=12, vm_count=2)
    assert alloc.session_count == 1


def test_allocation_filters_by_server(db_session: OrmSession) -> None:
    lab_default = _lab(db_session, server="default")
    lab_other = _lab(db_session, server="lab2")
    _session(
        db_session, lab_default, mode=SessionMode.dedicated,
        status=SessionStatus.active, n_students=1,
    )
    _session(
        db_session, lab_other, mode=SessionMode.dedicated,
        status=SessionStatus.active, n_students=3,
    )
    assert cap.compute_sessions_allocation(db_session, "default").resources.cpus == 6
    assert cap.compute_sessions_allocation(db_session, "lab2").resources.cpus == 18


def test_resolve_capacity_default_and_db(db_session: OrmSession) -> None:
    s = _settings(ludus_default_cpu_capacity=16, ludus_default_ram_capacity_gb=100)
    assert cap.resolve_capacity(db_session, s, "default") == (16, 100)
    db_session.add(
        LudusServer(
            name="lab2", url="https://x", api_key_encrypted="enc",
            cpu_capacity=32, ram_capacity_gb=256,
        )
    )
    db_session.commit()
    assert cap.resolve_capacity(db_session, s, "lab2") == (32, 256)
    assert cap.resolve_capacity(db_session, _settings(), "default") == (None, None)


def test_build_view_available_and_session_count(db_session: OrmSession) -> None:
    s = _settings(ludus_default_cpu_capacity=16, ludus_default_ram_capacity_gb=100)
    lab = _lab(db_session)
    _session(db_session, lab, mode=SessionMode.dedicated, status=SessionStatus.active, n_students=2)
    view = cap.build_capacity_view(db_session, s, "default")
    assert view.configured is True
    assert view.cpu_allocated == 12 and view.ram_allocated_gb == 24
    assert view.cpu_available == 4  # 16 - 12
    assert view.ram_available_gb == 76  # 100 - 24
    assert view.session_count == 1


def test_build_view_unconfigured(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    _session(db_session, lab, mode=SessionMode.shared, status=SessionStatus.active, n_students=1)
    view = cap.build_capacity_view(db_session, _settings(), "default")
    assert view.configured is False
    assert view.cpu_available is None and view.ram_available_gb is None
    assert view.cpu_allocated == 6  # allocation still computed


def test_build_view_overcommit_negative(db_session: OrmSession) -> None:
    s = _settings(ludus_default_cpu_capacity=4, ludus_default_ram_capacity_gb=8)
    lab = _lab(db_session)
    _session(db_session, lab, mode=SessionMode.dedicated, status=SessionStatus.active, n_students=2)
    view = cap.build_capacity_view(db_session, s, "default")
    assert view.cpu_available == -8  # 4 - 12
    assert view.ram_available_gb == -16  # 8 - 24
