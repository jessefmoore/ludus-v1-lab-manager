"""Service layer for student enrollment, removal, and Ludus cleanup.

Pure DB + filesystem logic — the only I/O beyond the database is:

* Optional best-effort unlink of the stored WireGuard ``.conf`` file.
* A delegated ``LudusClient.user_rm`` call when removing a provisioned
  student (never raw HTTP).

Router layer translates these exceptions into HTTP responses:

* ``SessionNotFound``      -> 404
* ``StudentNotFound``      -> 404
* ``SessionEnded``         -> 409
* ``UseridCollision``      -> 500
* ``LudusRemovalFailed``   -> 502
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError

from app.models import Session as SessionRow
from app.models import Student, StudentStatus
from app.models.event import Event
from app.models.session import SessionStatus
from app.schemas.student import StudentCreate
from app.services.exceptions import LudusError, LudusNotFound

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

# Ludus convention caps userIDs well under its internal limits; 20 chars
# is a safe ceiling that fits AD sAMAccountName (<= 20) and leaves room
# for the random suffix below.
_MAX_USERID_LEN = 20
_SLUG_MAX_LEN = 12  # leaves room for "-" + 6 hex chars = 7
_USERID_SUFFIX_BYTES = 3  # 6 hex chars
_INSERT_RETRY_LIMIT = 5
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_RESET_COOLDOWN_SECONDS = 120  # 2-minute cooldown between resets


class SessionNotFound(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when ``session_id`` does not correspond to an existing session."""


class StudentNotFound(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when ``student_id`` does not correspond to an existing student."""


class SessionEnded(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when attempting to add a student to an ``ended`` session."""


class UseridCollision(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when the retry loop cannot generate a unique userid/token."""


class LudusRemovalFailed(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when Ludus returns a non-404 error during ``user_rm``."""


class StudentNotReady(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when an action requires a student in ``ready`` state."""


class LudusResetFailed(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when Ludus returns an error during ``snapshot_revert``."""


class ResetCooldown(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when a reset is requested within the cooldown window."""


def _slugify(name: str) -> str:
    """Lowercase + collapse non-alphanumerics, truncated to the slug limit."""
    lowered = name.strip().lower()
    cleaned = _NON_ALNUM_RE.sub("", lowered)
    return cleaned[:_SLUG_MAX_LEN]


def _make_userid(base: str) -> str:
    """Build a Ludus-compatible userid: ``<slug><hex>`` or ``usr<hex>``.

    Ludus enforces ``^[A-Za-z0-9]{1,20}$`` — no hyphens, underscores,
    or other punctuation allowed. Total length is always <=
    ``_MAX_USERID_LEN``. The hex suffix gives ~16M variants per slug,
    which combined with the unique-constraint retry loop makes
    collisions vanishingly unlikely in practice.
    """
    slug = _slugify(base)
    suffix = secrets.token_hex(_USERID_SUFFIX_BYTES)
    if not slug:
        # token_hex(4) = 8 chars => "usr" + 8 = 11 chars total.
        return f"usr{secrets.token_hex(4)}"
    candidate = f"{slug}{suffix}"
    return candidate[:_MAX_USERID_LEN]


def create_student(
    db: DBSession,
    session_id: int,
    payload: StudentCreate,
) -> Student:
    """Persist a new ``Student`` in ``pending`` status for an active session.

    Does NOT call Ludus — provisioning is a separate step (task #21).
    The returned row has a generated ``ludus_userid`` and ``invite_token``
    that are guaranteed unique at the DB level.
    """
    session_row = db.get(SessionRow, session_id)
    if session_row is None:
        raise SessionNotFound(f"session id={session_id} does not exist")

    if session_row.status == SessionStatus.ended:
        raise SessionEnded("Cannot add students to ended session")

    last_error: IntegrityError | None = None
    for attempt in range(1, _INSERT_RETRY_LIMIT + 1):
        student = Student(
            session_id=session_id,
            full_name=payload.full_name,
            email=str(payload.email),
            ludus_userid=_make_userid(payload.full_name),
            invite_token=secrets.token_hex(16),
            status=StudentStatus.pending,
            range_id=None,
            wg_config_path=None,
            invite_redeemed_at=None,
        )
        db.add(student)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            logger.info(
                "student.create retrying on unique collision (attempt=%s)",
                attempt,
            )
            continue

        event = Event(
            session_id=session_id,
            student_id=student.id,
            action="student.created",
            details_json={
                "session_id": session_id,
                "student_id": student.id,
                "ludus_userid": student.ludus_userid,
            },
        )
        db.add(event)
        db.commit()
        db.refresh(student)
        logger.info(
            "student.created id=%s session_id=%s userid=%s",
            student.id,
            session_id,
            student.ludus_userid,
        )
        return student

    logger.error(
        "student.create exhausted %s retries without a unique userid/token",
        _INSERT_RETRY_LIMIT,
    )
    raise UseridCollision(
        "Unable to generate a unique ludus_userid/invite_token after "
        f"{_INSERT_RETRY_LIMIT} attempts"
    ) from last_error


def delete_student(
    db: DBSession,
    ludus_client: LudusClient,
    student_id: int,
) -> None:
    """Remove a student, cleaning up Ludus + on-disk config best-effort.

    * If the student was never provisioned (``status=pending``) we skip
      the Ludus call entirely.
    * If the upstream Ludus user is already gone (``LudusNotFound``) we
      treat the operation as a success.
    * Any other ``LudusError`` is re-raised as ``LudusRemovalFailed`` so
      the caller can return 502 and leave the DB row intact.
    * The WireGuard config file, if present on disk, is unlinked
      best-effort — ``FileNotFoundError`` is silent, other ``OSError``s
      are logged as warnings.
    """
    student = db.get(Student, student_id)
    if student is None:
        raise StudentNotFound(f"student id={student_id} does not exist")

    if student.status != StudentStatus.pending:
        try:
            ludus_client.user_rm(student.ludus_userid)
        except LudusNotFound:
            logger.info(
                "student.delete: ludus user %s already gone, proceeding",
                student.ludus_userid,
            )
        except LudusError as exc:
            # Ludus sometimes returns non-404 status codes (e.g. 500)
            # with "not found" in the body when the user doesn't exist.
            if "not found" in str(exc).lower():
                logger.info(
                    "student.delete: ludus user %s already gone (non-404), proceeding",
                    student.ludus_userid,
                )
            else:
                logger.warning(
                    "student.delete: ludus user_rm failed for %s: %s",
                    student.ludus_userid,
                    exc,
                )
                raise LudusRemovalFailed(f"Ludus user_rm failed: {exc}") from exc

    if student.wg_config_path:
        try:
            os.unlink(student.wg_config_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning(
                "student.delete: failed to unlink wg_config_path=%s: %s",
                student.wg_config_path,
                exc,
            )

    session_id = student.session_id
    ludus_userid = student.ludus_userid
    range_id = student.range_id

    # Null out FK references in events to avoid Postgres FK violations.
    db.execute(
        update(Event).where(Event.student_id == student_id).values(student_id=None)
    )

    event = Event(
        session_id=session_id,
        student_id=None,
        action="student.deleted",
        details_json={
            "student_id": student_id,
            "session_id": session_id,
            "ludus_userid": ludus_userid,
            "range_id": range_id,
        },
    )
    db.add(event)
    db.delete(student)
    db.commit()
    logger.info(
        "student.deleted id=%s session_id=%s userid=%s",
        student_id,
        session_id,
        ludus_userid,
    )


def reset_student(
    db: DBSession,
    ludus_client: LudusClient,
    student_id: int,
    snapshot_name: str,
) -> None:
    """Trigger a Ludus snapshot revert for the student's range.

    The revert is fire-and-forget from the platform's point of view --
    Ludus runs the rollback asynchronously, so this function returns as
    soon as Ludus accepts the call. Only ``ready`` students can be
    reset; any other status raises ``StudentNotReady`` so the router can
    return 409.

    Raises:
        StudentNotFound: ``student_id`` is unknown (router -> 404).
        StudentNotReady: student is not in ``ready`` state (router -> 409).
        LudusResetFailed: Ludus returned any error during the rollback
            call (router -> 502).
    """
    student = db.get(Student, student_id)
    if student is None:
        raise StudentNotFound(f"student id={student_id} does not exist")

    if student.status != StudentStatus.ready:
        raise StudentNotReady("Student not in ready state — cannot reset")

    # Check cooldown: find most recent student.reset event for this student.
    last_reset = db.scalars(
        select(Event)
        .where(Event.student_id == student_id, Event.action == "student.reset")
        .order_by(desc(Event.created_at))
        .limit(1)
    ).first()
    if last_reset is not None:
        elapsed = datetime.now(UTC) - last_reset.created_at.replace(tzinfo=UTC)
        remaining = timedelta(seconds=_RESET_COOLDOWN_SECONDS) - elapsed
        if remaining.total_seconds() > 0:
            raise ResetCooldown(f"Reset cooldown: wait {int(remaining.total_seconds())} seconds")

    try:
        ludus_client.snapshot_revert(student.ludus_userid, snapshot_name)
    except LudusError as exc:
        logger.warning(
            "student.reset: ludus snapshot_revert failed for %s: %s",
            student.ludus_userid,
            exc,
        )
        raise LudusResetFailed(f"Ludus snapshot_revert failed: {exc}") from exc

    event = Event(
        session_id=student.session_id,
        student_id=student.id,
        action="student.reset",
        details_json={
            "userid": student.ludus_userid,
            "snapshot_name": snapshot_name,
            "range_id": student.range_id,
        },
    )
    db.add(event)
    db.commit()
    logger.info(
        "student.reset id=%s userid=%s snapshot=%s",
        student.id,
        student.ludus_userid,
        snapshot_name,
    )


__all__ = [
    "LudusRemovalFailed",
    "LudusResetFailed",
    "ResetCooldown",
    "SessionEnded",
    "SessionNotFound",
    "StudentNotFound",
    "StudentNotReady",
    "UseridCollision",
    "create_student",
    "delete_student",
    "reset_student",
]
