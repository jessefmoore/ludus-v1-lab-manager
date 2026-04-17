"""Student endpoints: enroll a student into a session and remove a student.

Two endpoints, mounted on a single ``APIRouter`` with no shared prefix
because they live under different base paths:

* ``POST   /api/sessions/{session_id}/students``  -> enroll (no Ludus call)
* ``DELETE /api/students/{student_id}``           -> remove + cleanup

All routes require an authenticated instructor session (cookie-based).
Provisioning (calling ``user_add`` / ``range_deploy``) is a separate
flow in task #21 — this router deliberately never provisions on add.
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session as DBSession

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user, get_db, get_ludus_client
from app.models import Student
from app.models.user import User
from app.schemas.student import StudentCreate, StudentRead
from app.services import students as students_service
from app.services.ludus import LudusClient

_DEFAULT_SNAPSHOT_NAME = "ctf-initial"


class StudentResetRequest(BaseModel):
    """Optional body for ``POST /api/students/{id}/reset``.

    ``snapshot_name`` defaults to ``ctf-initial`` so callers can POST an
    empty body (or omit the field entirely) for the common case.
    """

    snapshot_name: str = Field(default=_DEFAULT_SNAPSHOT_NAME, min_length=1)


class StudentResetResponse(BaseModel):
    """Acknowledgement that Ludus accepted the rollback request."""

    status: str
    snapshot_name: str


class CSVImportResponse(BaseModel):
    """Summary of a CSV bulk import."""

    created: int
    failed: int
    errors: list[str]

router = APIRouter(tags=["students"])


def _student_to_read(student: Student, settings: Settings) -> StudentRead:
    """Build the ``StudentRead`` response shape with a derived invite URL.

    The raw ``invite_token`` is intentionally not surfaced — only the
    full invite URL callers should share with students.
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


@router.post(
    "/api/sessions/{session_id}/students",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_student(
    session_id: int,
    payload: StudentCreate,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> StudentRead:
    """Enroll a new student in an existing (non-ended) session."""
    try:
        student = students_service.create_student(db, session_id, payload)
    except students_service.SessionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        ) from exc
    except students_service.SessionEnded as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except students_service.UseridCollision as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return _student_to_read(student, settings)


@router.post(
    "/api/sessions/{session_id}/students/import",
    response_model=CSVImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_students_csv(
    session_id: int,
    file: UploadFile,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> CSVImportResponse:
    """Bulk-import students from a CSV file with ``full_name`` and ``email`` columns.

    Returns 201 with a summary even when some rows fail (validation or
    collision errors); the successfully imported students are committed.
    """
    if file.content_type and file.content_type not in (
        "text/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected CSV file, got {file.content_type}",
        )

    raw = await file.read()

    if len(raw) > 1_048_576:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV file exceeds 1 MB limit",
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file must be UTF-8 encoded",
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"full_name", "email"}.issubset(
        set(reader.fieldnames)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must have 'full_name' and 'email' columns",
        )

    created = 0
    errors: list[str] = []
    max_rows = 500
    for row_num, row in enumerate(reader, start=2):
        if row_num - 1 > max_rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV exceeds {max_rows} row limit",
            )
        try:
            payload = StudentCreate(
                full_name=row.get("full_name", "").strip(),
                email=row.get("email", "").strip(),
            )
        except ValidationError as exc:
            errors.append(f"Row {row_num}: {exc.errors()[0]['msg']}")
            continue
        try:
            students_service.create_student(db, session_id, payload)
            created += 1
        except (
            students_service.SessionNotFound,
            students_service.SessionEnded,
        ) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except students_service.UseridCollision:
            errors.append(f"Row {row_num}: userid collision for {row.get('email', '')}")
        except Exception as exc:
            errors.append(f"Row {row_num}: {exc}")

    return CSVImportResponse(created=created, failed=len(errors), errors=errors)


@router.delete(
    "/api/students/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_student(
    student_id: int,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    ludus_client: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> None:
    """Delete a student, calling Ludus ``user_rm`` only if provisioned.

    Returns 502 if Ludus refuses the removal with any non-404 error, so
    the caller can decide whether to retry or intervene manually. The DB
    row is preserved in that case to preserve the 1:1 platform -> Ludus
    mapping.
    """
    try:
        students_service.delete_student(db, ludus_client, student_id)
    except students_service.StudentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        ) from exc
    except students_service.LudusRemovalFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return None


@router.post(
    "/api/students/{student_id}/reset",
    response_model=StudentResetResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reset_student(
    student_id: int,
    payload: StudentResetRequest | None = None,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    ludus_client: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> StudentResetResponse:
    """Trigger a Ludus snapshot revert for the student's range.

    The endpoint returns ``202 Accepted`` as soon as Ludus accepts the
    rollback -- Ludus runs the actual revert asynchronously, so the
    platform does not wait for it to finish. Only students in the
    ``ready`` state are eligible; ``pending`` or ``error`` rows yield
    ``409``.

    A 2-minute cooldown between resets is enforced at the service layer;
    repeated calls within the window return ``429``.
    """
    snapshot_name = (
        payload.snapshot_name if payload is not None else _DEFAULT_SNAPSHOT_NAME
    )
    try:
        students_service.reset_student(
            db,
            ludus_client,
            student_id,
            snapshot_name,
        )
    except students_service.StudentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        ) from exc
    except students_service.StudentNotReady as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except students_service.ResetCooldown as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except students_service.LudusResetFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ludus snapshot revert failed",
        ) from exc
    return StudentResetResponse(
        status="reset_triggered",
        snapshot_name=snapshot_name,
    )
