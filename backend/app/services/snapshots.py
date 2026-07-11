"""Baseline snapshot management.

After a range finishes deploying (Ludus ``rangeState == "SUCCESS"``) we take a
named baseline snapshot so the per-student "Reset Environment" action has
something to roll back to. Ludus deploys asynchronously, so this can't happen
inside provisioning - instead :func:`ensure_baseline_snapshots` is called
repeatedly (e.g. by the session page while ranges finish building) and is:

* **idempotent** - a student whose baseline already exists (tracked via a
  ``*.baseline_snapshotted`` event) is skipped without another Ludus call;
* **patient** - a range that hasn't reached ``SUCCESS`` yet is counted as
  ``pending`` and retried on the next call;
* **best-effort** - a per-range failure is counted, never fatal.

Dedicated sessions snapshot each student's own range; a shared session snapshots
the single shared range once.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models import Session as SessionRow
from app.models import SessionMode, Student, StudentStatus
from app.models.event import Event
from app.services.exceptions import LudusError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

# Ludus range state that means "fully deployed and safe to snapshot".
_DEPLOYED_STATE = "SUCCESS"
_STUDENT_ACTION = "student.baseline_snapshotted"
_SHARED_ACTION = "session.baseline_snapshotted"


class SessionNotFound(Exception):  # noqa: N818 -- matches sibling services
    """Raised when ``session_id`` does not correspond to an existing session."""


@dataclass
class BaselineResult:
    """Tally for a baseline-snapshot pass over a session."""

    created: int = 0      # snapshots taken this pass
    existing: int = 0     # already had a baseline
    pending: int = 0      # range not yet SUCCESS - try again later
    failed: int = 0       # Ludus error taking the snapshot

    @property
    def done(self) -> bool:
        """True when nothing is left to wait for (no pending, no failures)."""
        return self.pending == 0 and self.failed == 0


def _already_baselined(db: DBSession, *, session_id: int, student_id: int | None) -> bool:
    action = _STUDENT_ACTION if student_id is not None else _SHARED_ACTION
    stmt = select(Event.id).where(Event.action == action).limit(1)
    if student_id is not None:
        stmt = stmt.where(Event.student_id == student_id)
    else:
        stmt = stmt.where(Event.session_id == session_id, Event.student_id.is_(None))
    return db.execute(stmt).first() is not None


def ensure_baseline_snapshots(
    db: DBSession,
    ludus: LudusClient,
    session_id: int,
    snapshot_name: str,
    *,
    include_ram: bool = False,
) -> BaselineResult:
    """Take the baseline snapshot for every deployed range in a session.

    Returns a :class:`BaselineResult`; ``result.done`` is True once every
    eligible range has been snapshotted (callers can stop polling then).
    """
    session_row = db.get(SessionRow, session_id)
    if session_row is None:
        raise SessionNotFound(f"session id={session_id} does not exist")

    # One range_list call gives every range's deploy state.
    try:
        ranges = ludus.range_list()
    except LudusError as exc:
        logger.warning("baseline: range_list failed for session %s: %s", session_id, exc)
        raise

    state_by_uid = {
        r["userID"]: r.get("rangeState")
        for r in ranges
        if isinstance(r, dict) and r.get("userID")
    }

    result = BaselineResult()

    # (student_id, owning userID) targets. Shared => one target on the shared
    # range with no student_id; dedicated => each ready student's own range.
    targets: list[tuple[int | None, str]] = []
    if session_row.mode == SessionMode.shared:
        if session_row.shared_range_id:
            targets.append((None, session_row.shared_range_id))
    else:
        students = db.execute(
            select(Student).where(
                Student.session_id == session_id,
                Student.status == StudentStatus.ready,
            )
        ).scalars().all()
        targets = [(s.id, s.ludus_userid) for s in students]

    for student_id, uid in targets:
        if _already_baselined(db, session_id=session_id, student_id=student_id):
            result.existing += 1
            continue
        if state_by_uid.get(uid) != _DEPLOYED_STATE:
            result.pending += 1
            continue
        try:
            ludus.snapshot_create(
                snapshot_name,
                user_id=uid,
                description="Baseline snapshot (auto) for Reset Environment",
                include_ram=include_ram,
            )
        except LudusError as exc:
            # A pre-existing snapshot of the same name is success, not failure.
            if "already exist" in str(exc).lower():
                _record(db, session_id, student_id, uid, snapshot_name)
                result.existing += 1
                continue
            logger.warning("baseline: snapshot_create failed for %s: %s", uid, exc)
            result.failed += 1
            continue
        _record(db, session_id, student_id, uid, snapshot_name)
        result.created += 1

    db.commit()
    logger.info(
        "baseline id=%s created=%s existing=%s pending=%s failed=%s",
        session_id, result.created, result.existing, result.pending, result.failed,
    )
    return result


def _record(
    db: DBSession, session_id: int, student_id: int | None, uid: str, name: str
) -> None:
    """Emit the dedup event marking this range as baselined."""
    db.add(
        Event(
            session_id=session_id,
            student_id=student_id,
            action=_STUDENT_ACTION if student_id is not None else _SHARED_ACTION,
            details_json={"userid": uid, "snapshot_name": name},
        )
    )


__all__ = ["BaselineResult", "SessionNotFound", "ensure_baseline_snapshots"]
