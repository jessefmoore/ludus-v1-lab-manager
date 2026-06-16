"""Public invite endpoints (no auth).

Two routes a student can hit with a tokenised URL:

* ``GET /invite/{token}``         -> HTML landing page.
* ``GET /invite/{token}/config``  -> WireGuard ``.conf`` file download.

Neither endpoint takes ``get_current_user``. Lookup + expiry rules live
in ``app.services.invite``; this module only translates service
exceptions into HTTP status codes and wires up Jinja2 rendering and the
``FileResponse``.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as DBSession

from app.core.config import Settings, get_settings
from app.core.deps import get_db
from app.models import LabTemplate
from app.services import invite as invite_service

router = APIRouter(prefix="/invite", tags=["invite"])

# Resolve the templates directory relative to this module so the path is
# stable regardless of the process CWD (dev shell, pytest, container).
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/{token}", response_class=HTMLResponse)
def invite_page(
    token: str,
    request: Request,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
) -> HTMLResponse:
    """Render the public invite landing page for a valid, unexpired token."""
    try:
        student = invite_service.load_student_by_token(db, token, settings.invite_token_ttl_hours)
    except invite_service.InviteNotFoundOrExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite link not found or expired",
        ) from exc

    lab: LabTemplate | None = None
    if student.session is not None:
        lab = db.get(LabTemplate, student.session.lab_template_id)

    expires_at = student.created_at + timedelta(hours=settings.invite_token_ttl_hours)
    download_url = f"/invite/{token}/config"

    return templates.TemplateResponse(
        request,
        "invite.html",
        {
            "student_name": student.full_name,
            "lab_name": lab.name if lab else "",
            "lab_description": lab.description if lab else None,
            "entry_point_vm": lab.entry_point_vm if lab else None,
            "expires_at": expires_at.isoformat(),
            "download_url": download_url,
        },
    )


@router.get("/{token}/config")
def invite_config(
    token: str,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
) -> FileResponse:
    """Stream the student's WireGuard ``.conf`` file as an attachment.

    Logs the redemption event *before* returning the ``FileResponse`` --
    the response body is written after the handler returns, so if we
    deferred the event write the client could disconnect before it ever
    ran.
    """
    try:
        student, path = invite_service.prepare_config_download(
            db, token, settings.invite_token_ttl_hours
        )
    except invite_service.InviteNotFoundOrExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite link not found or expired",
        ) from exc
    except invite_service.InviteNotReady as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    invite_service.mark_redeemed(db, student)

    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=f"{student.ludus_userid}.conf",
    )
