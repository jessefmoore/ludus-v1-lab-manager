"""Training session endpoints: list, create, detail, delete.

All routes require an authenticated instructor session (cookie-based).

No Ludus calls are issued from this module: provisioning lives in a
dedicated router (task #21). Delete here is a pure DB operation and
therefore refuses to run while a session is ``active`` / ``provisioning``
or has any ``ready`` students attached.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.core.config import Settings, get_settings
from app.core.deps import (
    LudusClientRegistry,
    get_current_user,
    get_db,
    get_ludus_client_registry,
)
from app.models import LabTemplate, Student, StudentStatus
from app.models import Session as SessionRow
from app.models.event import Event
from app.models.session import SessionStatus
from app.models.user import User
from app.schemas.session import (
    SessionCreate,
    SessionDetailRead,
    SessionPatch,
    SessionQuotaRead,
    SessionRead,
)
from app.schemas.student import StudentRead
from app.services import provision as provision_service
from app.services import sessions as sessions_service
from app.services import snapshots as snapshots_service
from app.services import teardown as teardown_service
from app.services.exceptions import LudusError
from app.services.resources import compute_range_resources, compute_session_demand

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionProvisionResponse(BaseModel):
    """Response body for ``POST /api/sessions/{id}/provision``."""

    provisioned: int
    failed: int
    skipped: int
    students: list[StudentRead]


def _student_to_read(student: Student, settings: Settings) -> StudentRead:
    """Build a ``StudentRead`` with the derived ``invite_url`` populated.

    ``invite_token`` is deliberately dropped from the payload so the raw
    bearer credential does not leak over list/detail endpoints.
    """
    base = settings.public_base_url.rstrip("/")
    return StudentRead.model_validate(
        {
            "id": student.id,
            "full_name": student.full_name,
            "email": student.email,
            "ludus_userid": student.ludus_userid,
            "range_id": student.range_id,
            "status": student.status,
            "invite_redeemed_at": student.invite_redeemed_at,
            "created_at": student.created_at,
            "invite_url": f"{base}/invite/{student.invite_token}",
        }
    )


def _session_detail(row: SessionRow, settings: Settings) -> SessionDetailRead:
    """Build the detail response with the embedded student list."""
    base = SessionRead.model_validate(row).model_dump()
    students = [_student_to_read(s, settings) for s in row.students]
    return SessionDetailRead(**base, students=students)


@router.get("", response_model=list[SessionRead])
def list_sessions(
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> list[SessionRead]:
    """Return every training session the caller can see (no pagination in MVP)."""
    rows = sessions_service.list_sessions(db)
    return [SessionRead.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: SessionCreate,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionRead:
    """Create a session in ``draft`` state. Provisioning is a separate step."""
    try:
        session_row = sessions_service.create_session(db, payload)
    except sessions_service.LabTemplateNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return SessionRead.model_validate(session_row)


@router.get("/{session_id}", response_model=SessionDetailRead)
def get_session(
    session_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionDetailRead:
    """Return a single session with its enrolled students embedded."""
    row = sessions_service.get_session_with_students(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return _session_detail(row, settings)


@router.get("/{session_id}/quota", response_model=SessionQuotaRead)
def get_session_quota(
    session_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionQuotaRead:
    """Return a session's computed CPU/RAM footprint vs its budget.

    A read-only preflight the UI calls before provisioning: it renders a
    usage gauge and can warn/disable the provision button when demand
    exceeds the configured quota (which the backend also hard-blocks).
    """
    row = sessions_service.get_session_with_students(db, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    lab_template = db.get(LabTemplate, row.lab_template_id)
    if lab_template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session lab template not found",
        )

    per_range = compute_range_resources(lab_template.range_config_yaml)
    student_count = len(row.students)
    ready_count = sum(1 for s in row.students if s.status == StudentStatus.ready)
    # Planned footprint (all students) drives the quota gate; allocated footprint
    # (only deployed/ready ranges) is what is actually consuming resources now.
    demand = compute_session_demand(per_range, row.mode, student_count)
    allocated = compute_session_demand(per_range, row.mode, ready_count)

    within_quota = (
        (row.cpu_quota is None or demand.cpus <= row.cpu_quota)
        and (row.ram_quota_gb is None or demand.ram_gb <= row.ram_quota_gb)
    )
    return SessionQuotaRead(
        mode=row.mode,
        student_count=student_count,
        ready_count=ready_count,
        per_range_cpus=per_range.cpus,
        per_range_ram_gb=per_range.ram_gb,
        demand_cpus=demand.cpus,
        demand_ram_gb=demand.ram_gb,
        allocated_cpus=allocated.cpus,
        allocated_ram_gb=allocated.ram_gb,
        cpu_quota=row.cpu_quota,
        ram_quota_gb=row.ram_quota_gb,
        within_quota=within_quota,
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> None:
    """Delete a draft/ended session with no ``ready`` students attached."""
    try:
        sessions_service.delete_session(db, session_id)
    except sessions_service.SessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from exc
    except sessions_service.SessionDeleteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return None


@router.patch("/{session_id}", response_model=SessionRead)
def patch_session(
    session_id: int,
    payload: SessionPatch,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionRead:
    """Partially update a session's ``shared_range_id`` and/or resource quota.

    Every field is a true partial update - only values present in the request
    body are touched (a sent ``null`` clears that field). Status rules:

    * ``shared_range_id`` may only be (re)bound while the session is ``draft``
      (a non-null value is validated against Ludus).
    * ``cpu_quota`` / ``ram_quota_gb`` may be edited any time *except* after
      the session has ``ended`` - so an instructor can raise/lower a running
      cohort's budget before provisioning more students.
    """
    session_row = sessions_service.get_session(db, session_id)
    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    fields_set = payload.model_fields_set
    changing_range = "shared_range_id" in fields_set
    changing_quota = "cpu_quota" in fields_set or "ram_quota_gb" in fields_set

    if changing_range and session_row.status != SessionStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"shared_range_id can only be changed while the session is "
            f"draft (status={session_row.status.value})",
        )
    if changing_quota and session_row.status == SessionStatus.ended:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot change the quota of an ended session",
        )

    # Validate the range exists on Ludus when a non-null value is provided.
    if changing_range and payload.shared_range_id is not None:
        lab_template = db.get(LabTemplate, session_row.lab_template_id)
        server_name = getattr(lab_template, "ludus_server", "default") or "default"
        try:
            ludus = registry.get(server_name)
            ranges = ludus.range_list()
        except (ValueError, LudusError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to validate range: {exc}",
            ) from exc
        found = any(
            isinstance(r, dict) and r.get("rangeID") == payload.shared_range_id
            for r in ranges
        )
        if not found:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Range '{payload.shared_range_id}' not found on "
                f"Ludus server '{server_name}'",
            )

    # Apply only the fields the caller actually sent (true partial update).
    if changing_range:
        session_row.shared_range_id = payload.shared_range_id
    if "cpu_quota" in fields_set:
        session_row.cpu_quota = payload.cpu_quota
    if "ram_quota_gb" in fields_set:
        session_row.ram_quota_gb = payload.ram_quota_gb
    db.add(
        Event(
            session_id=session_row.id,
            student_id=None,
            action="session.updated",
            details_json={
                "session_id": session_row.id,
                "changed": sorted(fields_set),
                "shared_range_id": session_row.shared_range_id,
                "cpu_quota": session_row.cpu_quota,
                "ram_quota_gb": session_row.ram_quota_gb,
            },
        )
    )
    db.commit()
    db.refresh(session_row)
    return SessionRead.model_validate(session_row)


class SessionTeardownResponse(BaseModel):
    """Response body for ``POST /rebuild`` and ``POST /teardown``."""

    cleaned: int
    failed: int
    skipped: int
    students: list[StudentRead]


def _run_teardown_op(
    op,
    session_id: int,
    db: DBSession,
    registry: LudusClientRegistry,
    settings: Settings,
) -> SessionTeardownResponse:
    """Shared runner for rebuild/teardown - maps service errors to HTTP."""
    try:
        result = op(db=db, registry=registry, session_id=session_id, settings=settings)
    except teardown_service.SessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return SessionTeardownResponse(
        cleaned=result.cleaned,
        failed=result.failed,
        skipped=result.skipped,
        students=[_student_to_read(s, settings) for s in result.students],
    )


@router.post("/{session_id}/rebuild", response_model=SessionTeardownResponse)
def rebuild_session(
    session_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionTeardownResponse:
    """Destroy the session's range VMs but keep its Ludus users/invites.

    Provisioned students flip back to ``pending`` so a subsequent
    ``/provision`` redeploys fresh VMs for the same people. Nothing on the
    invite/VPN side changes.
    """
    return _run_teardown_op(
        teardown_service.rebuild_session, session_id, db, registry, settings
    )


class BaselineSnapshotResponse(BaseModel):
    """Response body for ``POST /{id}/baseline-snapshots``."""

    created: int
    existing: int
    pending: int
    failed: int
    done: bool
    snapshot_name: str


@router.post("/{session_id}/baseline-snapshots", response_model=BaselineSnapshotResponse)
def baseline_snapshots(
    session_id: int,
    name: str = "snapshot-1",
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> BaselineSnapshotResponse:
    """Take the baseline snapshot for every range in the session that's deployed.

    Idempotent and safe to call repeatedly: ranges still ``DEPLOYING`` are
    reported as ``pending`` and retried next call; already-baselined ranges are
    skipped. ``done`` is True once nothing is pending/failed, so the caller can
    stop polling.
    """
    session_row = sessions_service.get_session(db, session_id)
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    lab_template = db.get(LabTemplate, session_row.lab_template_id)
    server_name = getattr(lab_template, "ludus_server", "default") or "default"
    try:
        ludus = registry.get(server_name)
        result = snapshots_service.ensure_baseline_snapshots(db, ludus, session_id, name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LudusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ludus error: {exc}"
        ) from exc
    return BaselineSnapshotResponse(
        created=result.created,
        existing=result.existing,
        pending=result.pending,
        failed=result.failed,
        done=result.done,
        snapshot_name=name,
    )


@router.post("/{session_id}/teardown", response_model=SessionTeardownResponse)
def teardown_session(
    session_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionTeardownResponse:
    """Fully tear down a session: remove Ludus users + configs, mark it ended.

    Destroys every provisioned student's range and Ludus user, deletes their
    WireGuard config, and transitions the session to ``ended``. Per-student
    failures are reported but do not stop the session from ending.
    """
    return _run_teardown_op(
        teardown_service.teardown_session, session_id, db, registry, settings
    )


@router.post(
    "/{session_id}/provision",
    response_model=SessionProvisionResponse,
)
def provision_session(
    session_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionProvisionResponse:
    """Drive the full Ludus provisioning flow for every student in a session.

    Synchronous for MVP; per-student failures are captured on the
    returned ``students`` list (``status="error"``) and never abort the
    batch. Already-``ready`` students are counted as ``skipped`` and do
    not touch Ludus.

    The Ludus server is determined by the session's lab template
    ``ludus_server`` field.
    """
    try:
        result = provision_service.provision_session(
            db=db,
            registry=registry,
            session_id=session_id,
            settings=settings,
        )
    except provision_service.SessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from exc
    except provision_service.QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return SessionProvisionResponse(
        provisioned=result.provisioned,
        failed=result.failed,
        skipped=result.skipped,
        students=[_student_to_read(s, settings) for s in result.students],
    )
