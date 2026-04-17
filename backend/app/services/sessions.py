"""Service layer for training session persistence.

Pure DB logic; no FastAPI imports. The router layer is responsible for
translating these exceptions into HTTP responses:

* ``LabTemplateNotFound`` -> 404
* ``SessionNotFound`` -> 404
* ``SessionDeleteConflict`` -> 409

Provisioning (spinning up Ludus ranges) is deliberately out of scope here
and lives in a separate service introduced by task #21.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import joinedload

from app.models import Session as SessionRow
from app.models import Student, StudentStatus
from app.models.event import Event
from app.models.lab_template import LabTemplate
from app.models.session import SessionStatus
from app.schemas.session import SessionCreate

logger = logging.getLogger(__name__)

_DELETABLE_STATUSES = {SessionStatus.draft, SessionStatus.ended}
_ENDABLE_STATUSES = {SessionStatus.active, SessionStatus.provisioning}


class LabTemplateNotFound(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when a create_session payload references a missing lab template."""


class SessionNotFound(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when a lookup/delete targets a session id that doesn't exist."""


class SessionDeleteConflict(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when a session cannot be deleted due to status/student state."""


class SessionEndConflict(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when a session cannot be ended (e.g. already ended or still draft)."""


def list_sessions(db: DBSession) -> list[SessionRow]:
    """Return every session, oldest first (stable id order)."""
    stmt = select(SessionRow).order_by(SessionRow.id)
    return list(db.execute(stmt).scalars().all())


def get_session(db: DBSession, sid: int) -> SessionRow | None:
    """Return one session by id, or ``None`` if it doesn't exist."""
    return db.get(SessionRow, sid)


def get_session_with_students(db: DBSession, sid: int) -> SessionRow | None:
    """Return one session by id with its ``students`` collection eagerly loaded."""
    stmt = (
        select(SessionRow)
        .options(joinedload(SessionRow.students))
        .where(SessionRow.id == sid)
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def create_session(db: DBSession, payload: SessionCreate) -> SessionRow:
    """Persist a new Session in ``draft`` status after validating the lab template.

    Raises ``LabTemplateNotFound`` if ``payload.lab_template_id`` does not
    match a row; the router maps that to HTTP 404.
    """
    lab = db.get(LabTemplate, payload.lab_template_id)
    if lab is None:
        logger.info(
            "session.create rejected: lab_template_id=%s not found",
            payload.lab_template_id,
        )
        raise LabTemplateNotFound(
            f"lab_template_id={payload.lab_template_id} does not exist"
        )

    session_row = SessionRow(
        name=payload.name,
        lab_template_id=payload.lab_template_id,
        mode=payload.mode,
        start_date=payload.start_date,
        end_date=payload.end_date,
        shared_range_id=payload.shared_range_id,
        status=SessionStatus.draft,
    )
    db.add(session_row)
    db.flush()  # assign session_row.id before referencing it in the event

    event = Event(
        session_id=session_row.id,
        student_id=None,
        action="session.created",
        details_json={
            "session_id": session_row.id,
            "name": session_row.name,
            "mode": session_row.mode.value,
        },
    )
    db.add(event)

    db.commit()
    db.refresh(session_row)
    logger.info(
        "session.created id=%s name=%s mode=%s",
        session_row.id,
        session_row.name,
        session_row.mode.value,
    )
    return session_row


def delete_session(db: DBSession, sid: int) -> None:
    """Delete a session if its status and students permit it.

    Rules (enforced here so the router stays thin):
    * ``status`` must be in ``{draft, ended}``.
    * No attached student may have ``status == ready``.

    Violations raise ``SessionDeleteConflict`` (mapped to 409). A missing id
    raises ``SessionNotFound`` (mapped to 404).

    Cascade of child students + orphan events is handled by the ORM relationship
    configured on ``Session.students`` (``cascade="all, delete-orphan"``).
    ``events.session_id`` is nullable and not covered by cascade, so audit
    history survives the delete.
    """
    session_row = db.get(SessionRow, sid)
    if session_row is None:
        raise SessionNotFound(f"session id={sid} does not exist")

    if session_row.status not in _DELETABLE_STATUSES:
        raise SessionDeleteConflict(
            f"session is in status={session_row.status.value}; "
            f"only {sorted(s.value for s in _DELETABLE_STATUSES)} may be deleted"
        )

    ready_student_stmt = select(Student.id).where(
        Student.session_id == sid,
        Student.status == StudentStatus.ready,
    )
    has_ready_student = db.execute(ready_student_stmt).first() is not None
    if has_ready_student:
        raise SessionDeleteConflict(
            "session has students in status=ready; "
            "unenroll or reset them before deleting"
        )

    name_snapshot = session_row.name
    db.delete(session_row)

    event = Event(
        session_id=None,
        student_id=None,
        action="session.deleted",
        details_json={"session_id": sid, "name": name_snapshot},
    )
    db.add(event)

    db.commit()
    logger.info("session.deleted id=%s name=%s", sid, name_snapshot)


def end_session(db: DBSession, sid: int) -> SessionRow:
    """Transition a session to ``ended`` status.

    Only ``active`` or ``provisioning`` sessions may be ended. Draft or
    already-ended sessions raise ``SessionEndConflict``.
    """
    session_row = db.get(SessionRow, sid)
    if session_row is None:
        raise SessionNotFound(f"session id={sid} does not exist")

    if session_row.status not in _ENDABLE_STATUSES:
        raise SessionEndConflict(
            f"session is in status={session_row.status.value}; "
            f"only {sorted(s.value for s in _ENDABLE_STATUSES)} may be ended"
        )

    session_row.status = SessionStatus.ended

    event = Event(
        session_id=session_row.id,
        student_id=None,
        action="session.ended",
        details_json={"session_id": session_row.id, "name": session_row.name},
    )
    db.add(event)

    db.commit()
    db.refresh(session_row)
    logger.info("session.ended id=%s name=%s", sid, session_row.name)
    return session_row


__all__ = [
    "LabTemplateNotFound",
    "SessionDeleteConflict",
    "SessionEndConflict",
    "SessionNotFound",
    "create_session",
    "delete_session",
    "end_session",
    "get_session",
    "get_session_with_students",
    "list_sessions",
]
