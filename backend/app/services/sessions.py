"""Service layer for training session persistence.

Pure DB logic; no FastAPI imports. The router layer is responsible for
translating these exceptions into HTTP responses:

* ``LabTemplateNotFound`` -> 404
* ``SessionNotFound`` -> 404
* ``SessionDeleteConflict`` -> 409

Provisioning (spinning up Ludus ranges) is deliberately out of scope here
and lives in a separate service introduced by task #21.
"""

import contextlib
import logging
import os
import secrets
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import joinedload

from app.models import Session as SessionRow
from app.models import Student, StudentStatus
from app.models.event import Event
from app.models.lab_template import LabTemplate
from app.models.session import SessionMode, SessionStatus
from app.schemas.session import SessionCreate
from app.services.exceptions import LudusError, LudusNotFound

if TYPE_CHECKING:
    from app.core.deps import LudusClientRegistry

logger = logging.getLogger(__name__)

_ENDABLE_STATUSES = {SessionStatus.active, SessionStatus.provisioning}
# Students that were provisioned at some point still own a Ludus user even
# after their range is removed; clean these up on delete so nothing orphans.
_PROVISIONED_STATUSES = {StudentStatus.error, StudentStatus.range_removed}


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
    stmt = select(SessionRow).options(joinedload(SessionRow.students)).where(SessionRow.id == sid)
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
        raise LabTemplateNotFound(f"lab_template_id={payload.lab_template_id} does not exist")

    session_row = SessionRow(
        name=payload.name,
        lab_template_id=payload.lab_template_id,
        mode=payload.mode,
        start_date=payload.start_date,
        end_date=payload.end_date,
        shared_range_id=payload.shared_range_id,
        cpu_quota=payload.cpu_quota,
        ram_quota_gb=payload.ram_quota_gb,
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

    # In shared mode with a pre-selected range, auto-enrol the range owner
    # (== shared_range_id) as the first student so they appear on the session
    # page as the range owner; "Add User" then adds additional users who share
    # the range. Skipped if that Ludus user is already enrolled anywhere
    # (ludus_userid is globally unique).
    if session_row.mode == SessionMode.shared and payload.shared_range_id:
        owner_uid = payload.shared_range_id
        already_enrolled = db.execute(
            select(Student).where(Student.ludus_userid == owner_uid)
        ).scalar_one_or_none()
        if already_enrolled is None:
            owner = Student(
                session_id=session_row.id,
                full_name=owner_uid,
                email=f"{owner_uid}@ludus.local",
                ludus_userid=owner_uid,
                invite_token=secrets.token_hex(16),
                status=StudentStatus.pending,
            )
            db.add(owner)
            db.flush()
            db.add(
                Event(
                    session_id=session_row.id,
                    student_id=owner.id,
                    action="student.range_owner_enrolled",
                    details_json={"session_id": session_row.id, "userid": owner_uid},
                )
            )
            logger.info(
                "session.create auto-enrolled range owner %s for session id=%s",
                owner_uid, session_row.id,
            )

    db.commit()
    db.refresh(session_row)
    logger.info(
        "session.created id=%s name=%s mode=%s",
        session_row.id,
        session_row.name,
        session_row.mode.value,
    )
    return session_row


def delete_session(
    db: DBSession,
    sid: int,
    *,
    registry: "LudusClientRegistry | None" = None,
    destroy_ranges: bool = False,
) -> None:
    """Delete a session if its state permits it, cleaning up Ludus users.

    Rules (enforced here so the router stays thin):
    * A ``provisioning`` session cannot be deleted (wait for it to finish).
    * By default a session with any ``ready`` student (live deployed range)
      cannot be deleted - tear those down first so their VMs aren't orphaned.
      Pass ``destroy_ranges=True`` to override: every provisioned user is then
      removed (``user_rm`` also destroys their Proxmox pool / range VMs), so the
      delete tears the whole session down.
    * Otherwise it is deleted. Lingering Ludus users for provisioned students
      are removed best-effort via *registry* so nothing orphans.

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

    if session_row.status == SessionStatus.provisioning:
        raise SessionDeleteConflict(
            "session is provisioning; wait for it to finish before deleting"
        )

    students = list(
        db.execute(select(Student).where(Student.session_id == sid)).scalars().all()
    )
    # A session with live deployed ranges must be torn down first - a plain
    # delete would orphan those ranges/VMs on Ludus. ``destroy_ranges`` opts in
    # to destroying them as part of the delete instead.
    if not destroy_ranges and any(s.status == StudentStatus.ready for s in students):
        raise SessionDeleteConflict(
            "session has live deployed ranges; tear them down first, or delete "
            "with the 'destroy VMs' option"
        )

    # Users to remove: with destroy_ranges, every provisioned student (incl.
    # ready -> user_rm destroys their live range VMs); otherwise just the
    # lingering error/range-removed users so nothing orphans.
    if destroy_ranges:
        to_clean = [s for s in students if s.status != StudentStatus.pending]
    else:
        to_clean = [s for s in students if s.status in _PROVISIONED_STATUSES]
    if to_clean and registry is not None:
        lab = db.get(LabTemplate, session_row.lab_template_id)
        server = getattr(lab, "ludus_server", "default") or "default"
        try:
            ludus = registry.get(server)
        except ValueError:
            ludus = None
        if ludus is not None:
            for s in to_clean:
                try:
                    ludus.user_rm(s.ludus_userid)
                except LudusNotFound:
                    pass
                except LudusError as exc:
                    if "not found" not in str(exc).lower():
                        logger.warning(
                            "session.delete: user_rm failed for %s: %s",
                            s.ludus_userid, exc,
                        )
                if s.wg_config_path:
                    with contextlib.suppress(OSError):
                        os.unlink(s.wg_config_path)

    name_snapshot = session_row.name

    # Collect student ids before cascade deletes them.
    student_ids = [s.id for s in students]

    # Null out FK references in events to avoid Postgres FK violations.
    # The audit rows survive with session_id/student_id = NULL.
    db.execute(
        update(Event).where(Event.session_id == sid).values(session_id=None)
    )
    if student_ids:
        db.execute(
            update(Event).where(Event.student_id.in_(student_ids)).values(student_id=None)
        )

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
