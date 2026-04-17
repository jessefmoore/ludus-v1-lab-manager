"""Service layer for the public invite flow.

No-auth lookup of a ``Student`` by its ``invite_token``, TTL enforcement,
and WireGuard config download preparation. The router layer translates
exceptions into HTTP responses:

* ``InviteNotFoundOrExpired`` -> 404
* ``InviteNotReady``          -> 409
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models import Student, StudentStatus
from app.models.event import Event

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

logger = logging.getLogger(__name__)


class InviteNotFoundOrExpired(Exception):  # noqa: N818 -- router-contract name
    """Raised when the invite token is unknown or past its TTL (router -> 404)."""


class InviteNotReady(Exception):  # noqa: N818 -- router-contract name
    """Raised when the student's lab is not yet provisioned (router -> 409)."""


def _is_expired(student: Student, ttl_hours: int) -> bool:
    """Return True if the invite has expired based on ``created_at`` + TTL."""
    created = student.created_at
    # SQLite may hand back naive datetimes; treat those as UTC.
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return datetime.now(UTC) - created > timedelta(hours=ttl_hours)


def load_student_by_token(db: DBSession, token: str, ttl_hours: int) -> Student:
    """Look up a ``Student`` by invite token, enforcing TTL expiry.

    Raises:
        InviteNotFoundOrExpired: Token does not match any student, or
            ``now - student.created_at > ttl_hours``. The same exception
            is used for both so we do not leak existence via the error.
    """
    student = db.execute(select(Student).where(Student.invite_token == token)).scalar_one_or_none()
    if student is None:
        raise InviteNotFoundOrExpired("Invite link not found or expired")
    if _is_expired(student, ttl_hours):
        raise InviteNotFoundOrExpired("Invite link not found or expired")
    return student


def prepare_config_download(db: DBSession, token: str, ttl_hours: int) -> tuple[Student, Path]:
    """Resolve the ``(student, wg_config_path)`` tuple for a download.

    Applies the same 404 rule as ``load_student_by_token`` before
    enforcing that the student is fully provisioned with a readable
    config file on disk.

    Raises:
        InviteNotFoundOrExpired: Token unknown or expired (router -> 404).
        InviteNotReady: Student is not in ``ready`` state, or the
            ``wg_config_path`` is missing/unreadable (router -> 409).
    """
    student = load_student_by_token(db, token, ttl_hours)
    if student.status != StudentStatus.ready:
        raise InviteNotReady("Lab not ready yet — please check back after provisioning completes")
    if not student.wg_config_path:
        raise InviteNotReady("Lab not ready yet — please check back after provisioning completes")
    path = Path(student.wg_config_path)
    if not path.is_file():
        raise InviteNotReady("Lab not ready yet — please check back after provisioning completes")
    return student, path


def mark_redeemed(db: DBSession, student: Student) -> str:
    """Record the redemption event and, if first time, stamp the student.

    Returns:
        The action string written to the event log: either
        ``"invite.redeemed"`` on the first successful download or
        ``"invite.redownloaded"`` for any subsequent fetch.
    """
    if student.invite_redeemed_at is None:
        student.invite_redeemed_at = datetime.now(UTC)
        action = "invite.redeemed"
    else:
        action = "invite.redownloaded"

    event = Event(
        session_id=student.session_id,
        student_id=student.id,
        action=action,
        details_json={
            "student_id": student.id,
            "session_id": student.session_id,
            "ludus_userid": student.ludus_userid,
        },
    )
    db.add(event)
    db.commit()
    logger.info(
        "%s student_id=%s userid=%s",
        action,
        student.id,
        student.ludus_userid,
    )
    return action


__all__ = [
    "InviteNotFoundOrExpired",
    "InviteNotReady",
    "load_student_by_token",
    "mark_redeemed",
    "prepare_config_download",
]
