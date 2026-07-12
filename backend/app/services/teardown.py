"""Session teardown / rebuild orchestration (the inverse of provisioning).

Two operations, both driven per-student and best-effort so one flaky VM
doesn't strand the rest of the batch:

* :func:`rebuild_session` - destroy the range VMs but KEEP the Ludus users,
  invites and WireGuard configs. Students flip back to ``pending`` so a
  subsequent provision redeploys fresh VMs for the same people. For a shared
  session the single shared range is destroyed once and ``shared_range_id`` is
  cleared so provision auto-creates a fresh one.

* :func:`teardown_session` - destroy each student's range VMs (``ludus range
  rm --user``) but KEEP the Ludus users and their WireGuard configs, then mark
  the session ``ended``. Users are intentionally not removed: ``user rm`` drops
  the Proxmox pool and races the asynchronous VM destroy, orphaning VMs.
  Students flip to ``range_removed``.

Both resolve the Ludus client from the lab template's ``ludus_server`` via the
registry (an explicit ``ludus`` client may be passed for tests). Per-student
failures are recorded on the row (``status=error``) and counted; they never
abort the batch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.models import LabTemplate, SessionMode, SessionStatus, Student, StudentStatus
from app.models import Session as SessionRow
from app.models.event import Event
from app.services.exceptions import LudusError, LudusNotFound

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from app.core.deps import LudusClientRegistry
    from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):  # noqa: N818 -- matches provision.SessionNotFound
    """Raised when ``session_id`` does not correspond to an existing session."""


@dataclass
class TeardownResult:
    """Tally returned by teardown/rebuild.

    ``cleaned`` counts students whose Ludus resources were torn down (or were
    already gone); ``failed`` counts per-student errors; ``skipped`` counts
    never-provisioned (``pending``) students that had nothing to remove.
    """

    cleaned: int = 0
    failed: int = 0
    skipped: int = 0
    students: list[Student] = field(default_factory=list)


def _emit(
    db: DBSession, session_id: int, student_id: int | None, action: str, details: dict
) -> None:
    db.add(
        Event(session_id=session_id, student_id=student_id, action=action, details_json=details)
    )


def _resolve(
    db: DBSession,
    session_id: int,
    ludus: LudusClient | None,
    registry: LudusClientRegistry | None,
) -> tuple[SessionRow, LabTemplate, LudusClient]:
    """Load the session (+students), its lab template, and a Ludus client."""
    stmt = (
        select(SessionRow)
        .options(joinedload(SessionRow.students))
        .where(SessionRow.id == session_id)
    )
    session_row = db.execute(stmt).unique().scalar_one_or_none()
    if session_row is None:
        raise SessionNotFound(f"session id={session_id} does not exist")

    lab_template = db.get(LabTemplate, session_row.lab_template_id)
    if lab_template is None:
        raise SessionNotFound(
            f"session id={session_id} references missing lab_template_id="
            f"{session_row.lab_template_id}"
        )

    if ludus is None:
        if registry is None:
            raise ValueError("Either ludus or registry must be provided")
        server_name = getattr(lab_template, "ludus_server", "default") or "default"
        ludus = registry.get(server_name)  # raises ValueError on unknown server
    return session_row, lab_template, ludus


def _is_missing(exc: LudusError) -> bool:
    """True when a Ludus error really means 'already gone' (idempotent)."""
    return isinstance(exc, LudusNotFound) or "not found" in str(exc).lower()


def _finalize(db: DBSession, session_row: SessionRow, result: TeardownResult) -> TeardownResult:
    """Refresh + return the session's students in stable id order."""
    db.commit()
    ordered = select(Student).where(Student.session_id == session_row.id).order_by(Student.id)
    result.students = list(db.execute(ordered).scalars().all())
    return result


def rebuild_session(
    db: DBSession,
    session_id: int,
    settings: Settings,
    *,
    ludus: LudusClient | None = None,
    registry: LudusClientRegistry | None = None,
) -> TeardownResult:
    """Destroy range VMs but keep users/invites so a re-provision rebuilds fresh.

    Dedicated: each provisioned student's range is destroyed. Shared: the one
    shared range is destroyed and ``shared_range_id`` cleared. Provisioned
    students flip to ``pending`` (config kept - provision rewrites it). Session
    status is left as-is so "Provision All" can redeploy.
    """
    session_row, _lab, client = _resolve(db, session_id, ludus, registry)
    if session_row.status == SessionStatus.ended:
        raise ValueError("Cannot rebuild an ended session; recreate it instead")

    result = TeardownResult()

    if session_row.mode == SessionMode.shared:
        # One shared range to destroy (owned by the lead user).
        if session_row.shared_range_id:
            try:
                client.range_destroy(user_id=session_row.shared_range_id, force=True)
            except LudusError as exc:
                if not _is_missing(exc):
                    logger.warning("rebuild: shared range_destroy failed: %s", exc)
                    _emit(db, session_id, None, "session.rebuild_failed",
                          {"session_id": session_id, "reason": repr(exc)})
                    db.commit()
                    raise ValueError(f"Failed to destroy shared range: {exc}") from exc
            _emit(db, session_id, None, "session.shared_range_destroyed",
                  {"session_id": session_id, "range_owner": session_row.shared_range_id})
        session_row.shared_range_id = None
        # Flip provisioned students back to pending; keep their users/configs.
        for student in session_row.students:
            if student.status == StudentStatus.pending:
                result.skipped += 1
                continue
            student.status = StudentStatus.pending
            student.range_id = None
            result.cleaned += 1
    else:
        # Dedicated: destroy each provisioned student's own range.
        for student in session_row.students:
            if student.status == StudentStatus.pending:
                result.skipped += 1
                continue
            try:
                client.range_destroy(user_id=student.ludus_userid, force=True)
            except LudusError as exc:
                if _is_missing(exc):
                    logger.info("rebuild: range for %s already gone", student.ludus_userid)
                else:
                    student.status = StudentStatus.error
                    _emit(db, session_id, student.id, "student.rebuild_failed",
                          {"student_id": student.id, "userid": student.ludus_userid,
                           "reason": repr(exc)})
                    result.failed += 1
                    db.commit()
                    continue
            student.status = StudentStatus.pending
            student.range_id = None
            result.cleaned += 1

    _emit(db, session_id, None, "session.rebuilt",
          {"session_id": session_id, "cleaned": result.cleaned, "failed": result.failed})
    logger.info(
        "session.rebuilt id=%s cleaned=%s failed=%s",
        session_id, result.cleaned, result.failed,
    )
    return _finalize(db, session_row, result)


def teardown_session(
    db: DBSession,
    session_id: int,
    settings: Settings,
    *,
    ludus: LudusClient | None = None,
    registry: LudusClientRegistry | None = None,
) -> TeardownResult:
    """Tear down a session's ranges (``ludus range rm --user``) and end it.

    Each provisioned student's range VMs are destroyed but the Ludus user is
    KEPT, so the user/pool persists and can be redeployed later. We deliberately
    do NOT call ``user_rm``: Ludus's user removal deletes the user's Proxmox
    pool and races the *asynchronous* VM destroy, which fails on a non-empty
    pool and orphans VMs. Students flip to ``range_removed``; a range that is
    already gone still counts as cleaned. Per-student failures are marked
    ``error`` but the session is still marked ``ended``.
    """
    session_row, _lab, client = _resolve(db, session_id, ludus, registry)

    result = TeardownResult()

    for student in session_row.students:
        if student.status == StudentStatus.pending:
            result.skipped += 1
            continue
        # Destroy the range VMs only (range rm --user); keep the Ludus user.
        try:
            client.range_destroy(user_id=student.ludus_userid, force=True)
        except LudusError as exc:
            if _is_missing(exc):
                logger.info("teardown: range for %s already gone", student.ludus_userid)
            else:
                student.status = StudentStatus.error
                _emit(db, session_id, student.id, "student.teardown_failed",
                      {"student_id": student.id, "userid": student.ludus_userid,
                       "step": "range_destroy", "reason": repr(exc)})
                result.failed += 1
                db.commit()
                continue
        # Keep the user and their WireGuard config; only the VMs are gone.
        student.status = StudentStatus.range_removed
        student.range_id = None
        result.cleaned += 1

    session_row.status = SessionStatus.ended
    _emit(db, session_id, None, "session.torn_down",
          {"session_id": session_id, "cleaned": result.cleaned, "failed": result.failed})
    logger.info(
        "session.torn_down id=%s cleaned=%s failed=%s",
        session_id, result.cleaned, result.failed,
    )
    return _finalize(db, session_row, result)


__all__ = [
    "SessionNotFound",
    "TeardownResult",
    "rebuild_session",
    "teardown_session",
]
