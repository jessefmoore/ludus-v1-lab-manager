"""Tests for CPU/RAM resource quotas.

Three layers:

1. Pure resource math (``app.services.resources``).
2. Session-budget hard block at provision time
   (``app.services.provision.check_session_quota`` + the 409 path).
3. Per-range cap when creating/updating a lab template
   (``app.services.labs`` -> ValueError -> 422).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.sessions import router as sessions_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.core.deps import get_current_user, get_ludus_client_registry
from app.models import (
    LabTemplate,
    LabTemplateMode,
    SessionMode,
    SessionStatus,
    Student,
    StudentStatus,
    User,
)
from app.models import Session as SessionRow
from app.schemas.lab import LabTemplateCreate, LabTemplateUpdate
from app.services import labs as labs_service
from app.services import provision as provision_service
from app.services.resources import (
    RangeResources,
    compute_range_resources,
    compute_session_demand,
)

# A two-VM range: 4+2 = 6 CPUs, 8+4 = 12 GB RAM.
TWO_VM_YAML = (
    "ludus:\n"
    "  - vm_name: '{{ range_id }}-dc'\n"
    "    ram_gb: 8\n"
    "    cpus: 4\n"
    "  - vm_name: '{{ range_id }}-win11'\n"
    "    ram_gb: 4\n"
    "    cpus: 2\n"
)


# ---------------------------------------------------------------------------
# 1. resource math
# ---------------------------------------------------------------------------


def test_compute_range_resources_sums_vms() -> None:
    res = compute_range_resources(TWO_VM_YAML)
    assert res == RangeResources(cpus=6, ram_gb=12, vm_count=2)


def test_compute_range_resources_handles_missing_fields() -> None:
    yaml_text = "ludus:\n  - vm_name: a\n    cpus: 2\n  - vm_name: b\n    ram_gb: 4\n"
    res = compute_range_resources(yaml_text)
    # b has no cpus, a has no ram -> partial sums, both counted as VMs.
    assert res == RangeResources(cpus=2, ram_gb=4, vm_count=2)


def test_compute_range_resources_coerces_string_scalars() -> None:
    res = compute_range_resources("ludus:\n  - vm_name: a\n    cpus: '4'\n    ram_gb: '8'\n")
    assert res.cpus == 4
    assert res.ram_gb == 8


@pytest.mark.parametrize(
    "bad",
    ["", "not: [a, b", "just a string", "42", "ludus: not-a-list"],
)
def test_compute_range_resources_bad_input_is_zero(bad: str) -> None:
    assert compute_range_resources(bad) == RangeResources()


def test_compute_session_demand_shared_is_single_range() -> None:
    per_range = RangeResources(cpus=6, ram_gb=12, vm_count=2)
    demand = compute_session_demand(per_range, SessionMode.shared, student_count=10)
    assert demand == per_range  # headcount irrelevant for shared


def test_compute_session_demand_dedicated_scales_by_students() -> None:
    per_range = RangeResources(cpus=6, ram_gb=12, vm_count=2)
    demand = compute_session_demand(per_range, SessionMode.dedicated, student_count=3)
    assert demand == RangeResources(cpus=18, ram_gb=36, vm_count=6)


def test_compute_session_demand_zero_students_is_zero() -> None:
    per_range = RangeResources(cpus=6, ram_gb=12, vm_count=2)
    assert compute_session_demand(per_range, SessionMode.dedicated, 0) == RangeResources()


# ---------------------------------------------------------------------------
# shared fixtures for the DB-backed tests
# ---------------------------------------------------------------------------

ADMIN_EMAIL = "instructor@example.com"


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
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email=ADMIN_EMAIL,
        admin_password="super-secret-test-pw",
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key",
        config_storage_dir=str(tmp_path),
        _env_file=None,
    )


def _db_override(db: OrmSession):
    """Return a FastAPI generator dependency yielding ``db``."""
    def _override() -> Iterator[OrmSession]:
        yield db
    return _override


def _lab(db: OrmSession, yaml_text: str = TWO_VM_YAML) -> LabTemplate:
    lab = LabTemplate(
        name="Lab",
        range_config_yaml=yaml_text,
        default_mode=LabTemplateMode.dedicated,
        ludus_server="default",
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def _session_with_students(
    db: OrmSession,
    lab: LabTemplate,
    *,
    mode: SessionMode,
    n_students: int,
    cpu_quota: int | None = None,
    ram_quota_gb: int | None = None,
) -> SessionRow:
    row = SessionRow(
        name="Cohort",
        lab_template_id=lab.id,
        mode=mode,
        cpu_quota=cpu_quota,
        ram_quota_gb=ram_quota_gb,
        status=SessionStatus.draft,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    for i in range(n_students):
        db.add(
            Student(
                session_id=row.id,
                full_name=f"Student {i}",
                email=f"s{i}@example.com",
                ludus_userid=f"user{i}",
                invite_token=f"tok{i}",
                status=StudentStatus.pending,
            )
        )
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# 2. session-budget hard block
# ---------------------------------------------------------------------------


def test_check_quota_passes_when_within_budget(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    # dedicated, 2 students -> 12 CPU / 24 GB. Budget is generous.
    row = _session_with_students(
        db_session, lab, mode=SessionMode.dedicated, n_students=2,
        cpu_quota=20, ram_quota_gb=40,
    )
    provision_service.check_session_quota(row, lab)  # must not raise


def test_check_quota_blocks_on_cpu(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session_with_students(
        db_session, lab, mode=SessionMode.dedicated, n_students=3, cpu_quota=10,
    )
    with pytest.raises(provision_service.QuotaExceeded) as exc:
        provision_service.check_session_quota(row, lab)
    assert exc.value.demand_cpus == 18  # 3 x 6
    assert exc.value.cpu_quota == 10


def test_check_quota_shared_counts_one_range(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    # shared: 20 students still only one range (6 CPU / 12 GB) -> within a
    # tight budget that would blow up under dedicated.
    row = _session_with_students(
        db_session, lab, mode=SessionMode.shared, n_students=20,
        cpu_quota=6, ram_quota_gb=12,
    )
    provision_service.check_session_quota(row, lab)  # must not raise


def test_check_quota_noop_when_unset(db_session: OrmSession) -> None:
    lab = _lab(db_session)
    row = _session_with_students(
        db_session, lab, mode=SessionMode.dedicated, n_students=100,
    )
    provision_service.check_session_quota(row, lab)  # no quota -> never raises


def test_provision_returns_409_when_over_quota(
    db_session: OrmSession, settings: Settings
) -> None:
    """The provision endpoint surfaces QuotaExceeded as 409, no Ludus call."""
    lab = _lab(db_session)
    row = _session_with_students(
        db_session, lab, mode=SessionMode.dedicated, n_students=3, cpu_quota=10,
    )

    class ExplodingLudus:
        def __getattr__(self, name: str):  # any Ludus call is a test failure
            raise AssertionError(f"Ludus.{name} must not be called when over quota")

    class Registry:
        def get(self, name: str = "default") -> ExplodingLudus:
            return ExplodingLudus()

    app = FastAPI()
    app.include_router(sessions_router)
    app.dependency_overrides[get_db] = _db_override(db_session)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_ludus_client_registry] = lambda: Registry()
    app.dependency_overrides[get_current_user] = lambda: User(
        email=ADMIN_EMAIL, password_hash="x", role="instructor"
    )

    with TestClient(app) as client:
        resp = client.post(f"/api/sessions/{row.id}/provision")
    assert resp.status_code == 409
    assert "quota" in resp.json()["detail"].lower()


def test_quota_endpoint_reports_demand(db_session: OrmSession, settings: Settings) -> None:
    lab = _lab(db_session)
    row = _session_with_students(
        db_session, lab, mode=SessionMode.dedicated, n_students=2, cpu_quota=8,
    )

    app = FastAPI()
    app.include_router(sessions_router)
    app.dependency_overrides[get_db] = _db_override(db_session)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_user] = lambda: User(
        email=ADMIN_EMAIL, password_hash="x", role="instructor"
    )

    with TestClient(app) as client:
        resp = client.get(f"/api/sessions/{row.id}/quota")
    assert resp.status_code == 200
    body = resp.json()
    assert body["per_range_cpus"] == 6
    assert body["demand_cpus"] == 12  # 2 x 6
    assert body["demand_ram_gb"] == 24
    assert body["cpu_quota"] == 8
    assert body["within_quota"] is False  # 12 > 8


# ---------------------------------------------------------------------------
# 3. per-range cap on lab templates
# ---------------------------------------------------------------------------


@pytest.fixture
def capped_settings(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Settings:
    """Force get_settings() everywhere to return a settings with a range cap."""
    capped = settings.model_copy(update={"max_range_cpus": 5, "max_range_ram_gb": 100})
    monkeypatch.setattr(labs_service, "get_settings", lambda: capped)
    return capped


def test_create_lab_rejects_over_cpu_cap(
    db_session: OrmSession, capped_settings: Settings
) -> None:
    # TWO_VM_YAML needs 6 CPUs; cap is 5.
    payload = LabTemplateCreate(
        name="Too Big",
        description=None,
        range_config_yaml=TWO_VM_YAML,
        default_mode=LabTemplateMode.dedicated,
        entry_point_vm=None,
    )
    with pytest.raises(ValueError, match="CPU cores"):
        labs_service.create_lab(db_session, payload)


def test_create_lab_allows_within_cap(
    db_session: OrmSession, capped_settings: Settings
) -> None:
    small = "ludus:\n  - vm_name: a\n    cpus: 4\n    ram_gb: 8\n"
    payload = LabTemplateCreate(
        name="Fits",
        description=None,
        range_config_yaml=small,
        default_mode=LabTemplateMode.dedicated,
        entry_point_vm=None,
    )
    lab = labs_service.create_lab(db_session, payload)
    assert lab.id is not None


def test_update_lab_rejects_over_ram_cap(
    db_session: OrmSession, capped_settings: Settings
) -> None:
    lab = _lab(db_session, "ludus:\n  - vm_name: a\n    cpus: 2\n    ram_gb: 8\n")
    over_ram = "ludus:\n  - vm_name: a\n    cpus: 2\n    ram_gb: 200\n"
    with pytest.raises(ValueError, match="RAM"):
        labs_service.update_lab(
            db_session, lab.id, LabTemplateUpdate(range_config_yaml=over_ram)
        )


# ---------------------------------------------------------------------------
# 4. editing a session's quota via PATCH (status rules)
# ---------------------------------------------------------------------------


def _patch_app(db_session: OrmSession, settings: Settings) -> FastAPI:
    from app.core.deps import get_ludus_client_registry

    class _Registry:
        def get(self, name: str = "default"):
            raise AssertionError("Ludus must not be called for a quota-only PATCH")

    app = FastAPI()
    app.include_router(sessions_router)
    app.dependency_overrides[get_db] = _db_override(db_session)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_ludus_client_registry] = lambda: _Registry()
    app.dependency_overrides[get_current_user] = lambda: User(
        email=ADMIN_EMAIL, password_hash="x", role="instructor"
    )
    return app


def test_patch_quota_on_active_session_ok(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session_with_students(
        db_session, lab, mode=SessionMode.dedicated, n_students=1,
    )
    row.status = SessionStatus.active
    db_session.commit()

    with TestClient(_patch_app(db_session, settings)) as client:
        resp = client.patch(f"/api/sessions/{row.id}", json={"cpu_quota": 20, "ram_quota_gb": 40})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cpu_quota"] == 20 and body["ram_quota_gb"] == 40


def test_patch_quota_on_ended_session_409(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session_with_students(db_session, lab, mode=SessionMode.shared, n_students=1)
    row.status = SessionStatus.ended
    db_session.commit()

    with TestClient(_patch_app(db_session, settings)) as client:
        resp = client.patch(f"/api/sessions/{row.id}", json={"cpu_quota": 12})
    assert resp.status_code == 409
    assert "ended" in resp.json()["detail"].lower()


def test_patch_shared_range_on_active_session_409(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session_with_students(db_session, lab, mode=SessionMode.shared, n_students=1)
    row.status = SessionStatus.active
    db_session.commit()

    with TestClient(_patch_app(db_session, settings)) as client:
        resp = client.patch(f"/api/sessions/{row.id}", json={"shared_range_id": "RZ9"})
    assert resp.status_code == 409
    assert "draft" in resp.json()["detail"].lower()


def test_patch_quota_only_preserves_shared_range(
    db_session: OrmSession, settings: Settings
) -> None:
    lab = _lab(db_session)
    row = _session_with_students(db_session, lab, mode=SessionMode.shared, n_students=1)
    row.status = SessionStatus.active
    row.shared_range_id = "keep-me"
    db_session.commit()

    with TestClient(_patch_app(db_session, settings)) as client:
        resp = client.patch(f"/api/sessions/{row.id}", json={"cpu_quota": 8})
    assert resp.status_code == 200
    # Quota-only PATCH must not wipe the existing shared_range_id.
    assert resp.json()["shared_range_id"] == "keep-me"
    assert resp.json()["cpu_quota"] == 8
