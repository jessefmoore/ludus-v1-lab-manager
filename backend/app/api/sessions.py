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
from app.core.deps import get_current_user, get_db, get_ludus_client
from app.models import Session as SessionRow
from app.models import Student
from app.models.user import User
from app.schemas.session import SessionCreate, SessionDetailRead, SessionRead
from app.schemas.student import StudentRead
from app.services import provision as provision_service
from app.services import sessions as sessions_service
from app.services.ludus import LudusClient

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


@router.post(
    "/{session_id}/provision",
    response_model=SessionProvisionResponse,
)
def provision_session(
    session_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    ludus_client: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> SessionProvisionResponse:
    """Drive the full Ludus provisioning flow for every student in a session.

    Synchronous for MVP; per-student failures are captured on the
    returned ``students`` list (``status="error"``) and never abort the
    batch. Already-``ready`` students are counted as ``skipped`` and do
    not touch Ludus.
    """
    try:
        result = provision_service.provision_session(
            db=db,
            ludus=ludus_client,
            session_id=session_id,
            settings=settings,
        )
    except provision_service.SessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from exc

    return SessionProvisionResponse(
        provisioned=result.provisioned,
        failed=result.failed,
        skipped=result.skipped,
        students=[_student_to_read(s, settings) for s in result.students],
    )
