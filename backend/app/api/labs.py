"""Lab template endpoints: list, create, detail.

All routes require an authenticated instructor session (cookie-based).
Delete is deliberately omitted from Phase 1.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.lab import LabTemplateCreate, LabTemplateRead
from app.services import labs as labs_service

router = APIRouter(prefix="/api/labs", tags=["labs"])


@router.get("", response_model=list[LabTemplateRead])
def list_labs(
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> list[LabTemplateRead]:
    """Return every lab template visible to the caller."""
    rows = labs_service.list_labs(db)
    return [LabTemplateRead.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=LabTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_lab(
    payload: LabTemplateCreate,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> LabTemplateRead:
    """Persist a new lab template after validating its range-config YAML."""
    try:
        lab = labs_service.create_lab(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return LabTemplateRead.model_validate(lab)


@router.get("/{lab_id}", response_model=LabTemplateRead)
def get_lab(
    lab_id: int,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> LabTemplateRead:
    """Return a single lab template by id, or 404."""
    lab = labs_service.get_lab(db, lab_id)
    if lab is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab template not found",
        )
    return LabTemplateRead.model_validate(lab)
