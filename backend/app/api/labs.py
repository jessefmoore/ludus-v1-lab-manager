"""Lab template endpoints: list, create, detail, update, delete, cover image.

All routes require an authenticated instructor session (cookie-based).
"""

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.lab import LabTemplateCreate, LabTemplateRead, LabTemplateUpdate
from app.services import labs as labs_service
from app.services.labs import LabDeleteConflict, LabNotFound

router = APIRouter(prefix="/api/labs", tags=["labs"])


@router.get("", response_model=list[LabTemplateRead])
def list_labs(
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> list[LabTemplateRead]:
    """Return every lab template visible to the caller."""
    rows = labs_service.list_labs(db)
    return [LabTemplateRead(**row) for row in rows]


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


@router.put("/{lab_id}", response_model=LabTemplateRead)
def update_lab(
    lab_id: int,
    payload: LabTemplateUpdate,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> LabTemplateRead:
    """Partially update a lab template."""
    try:
        lab = labs_service.update_lab(db, lab_id, payload)
    except LabNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return LabTemplateRead.model_validate(lab)


@router.delete("/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab(
    lab_id: int,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> Response:
    """Delete a lab template if no active sessions reference it."""
    try:
        labs_service.delete_lab(db, lab_id)
    except LabNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except LabDeleteConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Cover image endpoints ──────────────────────────────────────────────


@router.post("/{lab_id}/image", response_model=LabTemplateRead)
async def upload_lab_image(
    lab_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> LabTemplateRead:
    """Upload a cover image for a lab template (max 5 MB)."""
    data = await file.read()
    content_type = file.content_type or ""
    try:
        lab = labs_service.save_lab_image(db, lab_id, data, content_type)
    except LabNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return LabTemplateRead.model_validate(lab)


@router.get("/{lab_id}/image")
def get_lab_image(
    lab_id: int,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> FileResponse:
    """Serve the cover image for a lab template."""
    path = labs_service.get_lab_image_path(db, lab_id)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cover image set",
        )
    return FileResponse(
        path,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.delete("/{lab_id}/image", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab_image(
    lab_id: int,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> Response:
    """Remove the cover image for a lab template."""
    try:
        labs_service.delete_lab_image(db, lab_id)
    except LabNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
