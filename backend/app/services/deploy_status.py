"""Reconcile in-flight range deploys against Ludus.

Provisioning fires ``range_deploy`` (asynchronous on Ludus) and leaves each
student in ``deploying``. This module is polled by the UI to advance those
students as their ranges settle:

* range confirmed up (``SUCCESS`` + every VM powered on)  -> ``ready``
* range deploy failed (``ERROR``)                          -> ``error``
* anything else (still building)                           -> stays ``deploying``

The session is promoted to ``active`` once nothing is deploying and at least
one student is ready. ``done`` is True when no student is still deploying, so
the caller can stop polling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models import LabTemplate, SessionMode, SessionStatus, Student, StudentStatus
from app.models import Session as SessionRow
from app.models.event import Event
from app.services.exceptions import LudusError
from app.services.provision import _range_confirmed_up

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from app.core.deps import LudusClientRegistry
    from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

_ERROR_RANGE_STATE = "ERROR"


class SessionNotFound(Exception):  # noqa: N818 -- matches sibling services
    """Raised when ``session_id`` does not correspond to an existing session."""


@dataclass
class DeployStatusResult:
    """Tally returned by :func:`reconcile_deploy_status`.

    ``done`` is True when no student remains in ``deploying`` (the caller may
    stop polling). ``students`` holds the refreshed rows in stable id order.
    """

    ready: int = 0
    deploying: int = 0
    failed: int = 0
    done: bool = True
    students: list[Student] = field(default_factory=list)


def _range_state(ludus: LudusClient, userid: str) -> str | None:
    """Return the uppercased ``rangeState`` for *userid*, or None on error."""
    try:
        info = ludus.range_get_vms(user_id=userid)
    except LudusError:
        return None
    return str(info.get("rangeState") or "").upper()


def reconcile_deploy_status(
    db: DBSession,
    session_id: int,
    *,
    ludus: LudusClient | None = None,
    registry: LudusClientRegistry | None = None,
) -> DeployStatusResult:
    """Advance a session's ``deploying`` students based on live Ludus state.

    Idempotent and safe to call repeatedly. Students not in ``deploying`` are
    left untouched. The Ludus range backing each student is queried at most
    once per distinct owner within a call.
    """
    stmt = (
        select(SessionRow)
        .options(joinedload(SessionRow.students))
        .where(SessionRow.id == session_id)
    )
    session_row = db.execute(stmt).unique().scalar_one_or_none()
    if session_row is None:
        raise SessionNotFound(f"session id={session_id} does not exist")

    lab_template = db.get(LabTemplate, session_row.lab_template_id)
    if ludus is None:
        if registry is None:
            raise ValueError("Either ludus or registry must be provided")
        server_name = getattr(lab_template, "ludus_server", "default") or "default"
        ludus = registry.get(server_name)  # raises ValueError on unknown server

    result = DeployStatusResult()
    # Cache per-owner liveness/state so a shared session hits Ludus once, not
    # once per student.
    confirmed_cache: dict[str, bool] = {}
    state_cache: dict[str, str | None] = {}

    for student in session_row.students:
        if student.status != StudentStatus.deploying:
            continue

        range_owner = (
            session_row.shared_range_id
            if session_row.mode == SessionMode.shared
            else student.ludus_userid
        )
        if not range_owner:
            # No range to check (shouldn't happen for a deploying student);
            # leave it as-is and count it.
            result.deploying += 1
            continue

        if range_owner not in confirmed_cache:
            confirmed_cache[range_owner] = _range_confirmed_up(ludus, range_owner)
            state_cache[range_owner] = _range_state(ludus, range_owner)

        if confirmed_cache[range_owner]:
            student.status = StudentStatus.ready
            result.ready += 1
            db.add(
                Event(
                    session_id=session_id,
                    student_id=student.id,
                    action="student.provisioned",
                    details_json={
                        "student_id": student.id,
                        "session_id": session_id,
                        "userid": student.ludus_userid,
                        "range_id": student.range_id,
                        "via": "deploy_status_poll",
                    },
                )
            )
        elif state_cache[range_owner] == _ERROR_RANGE_STATE:
            student.status = StudentStatus.error
            result.failed += 1
            db.add(
                Event(
                    session_id=session_id,
                    student_id=student.id,
                    action="student.provision_failed",
                    details_json={
                        "student_id": student.id,
                        "session_id": session_id,
                        "userid": student.ludus_userid,
                        "step": "range_deploy",
                        "reason": "range state ERROR",
                    },
                )
            )
        else:
            result.deploying += 1

    # Recompute session status: still provisioning while anything deploys.
    all_statuses = [s.status for s in session_row.students]
    if any(s == StudentStatus.deploying for s in all_statuses):
        session_row.status = SessionStatus.provisioning
    elif any(s == StudentStatus.ready for s in all_statuses):
        session_row.status = SessionStatus.active

    db.commit()

    result.done = result.deploying == 0
    ordered = select(Student).where(Student.session_id == session_id).order_by(Student.id)
    result.students = list(db.execute(ordered).scalars().all())
    logger.info(
        "deploy_status session=%s ready=%s deploying=%s failed=%s done=%s",
        session_id, result.ready, result.deploying, result.failed, result.done,
    )
    return result


__all__ = ["DeployStatusResult", "SessionNotFound", "reconcile_deploy_status"]
