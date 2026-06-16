"""Event (audit log) endpoints.

Read-only endpoint for fetching audit events, filterable by session_id.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session as DBSession

from app.core.deps import get_current_user, get_db
from app.models.event import Event
from app.models.user import User
from app.schemas.event import EventRead

router = APIRouter(tags=["events"])


@router.get(
    "/api/events",
    response_model=list[EventRead],
)
def list_events(
    session_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> list[EventRead]:
    """List audit events, optionally filtered by session_id.

    Returns events in reverse chronological order (newest first).
    """
    stmt = select(Event).order_by(desc(Event.created_at))
    if session_id is not None:
        stmt = stmt.where(Event.session_id == session_id)
    stmt = stmt.offset(offset).limit(limit)
    rows = db.scalars(stmt).all()
    return [EventRead.model_validate(row) for row in rows]
