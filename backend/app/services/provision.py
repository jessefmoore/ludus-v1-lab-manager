"""Session provisioning orchestrator.

Replaces the legacy ``add_player.sh`` flow. For each ``Student`` attached to
a ``Session``, this module drives the Ludus lifecycle end-to-end:

1. ``user_add``        -> create the user on Ludus (benign on
   ``LudusUserExists`` for idempotency)
2. ``range_assign`` or ``range_deploy`` depending on ``session.mode``
3. ``user_wireguard``  -> fetch the ``.conf`` text
4. Persist the config to ``{config_storage_dir}/{session_id}/{userid}.conf``
   (parent dir ``0o700``, file mode ``0o600`` - private keys).
5. Flip the student to ``ready`` and emit a ``student.provisioned`` event.

Per-student failures are captured on the student row (``status=error``)
and an event is emitted - the rest of the batch keeps running so that a
single flaky user doesn't stall an entire class.

The orchestration is synchronous (MVP); callers that want async can wrap
this via a background worker later. Each student is committed individually
so partial progress survives a process crash.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.models import LabTemplate, SessionMode, SessionStatus, Student, StudentStatus
from app.models import Session as SessionRow
from app.models.event import Event
from app.services.exceptions import LudusError, LudusNotFound, LudusUserExists

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from app.core.deps import LudusClientRegistry
    from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when ``session_id`` does not correspond to an existing session."""


@dataclass
class ProvisionResult:
    """Tally returned by :func:`provision_session`.

    ``students`` holds the refreshed ``Student`` ORM rows in stable id
    order so the router can render them with derived invite URLs.
    """

    provisioned: int = 0
    failed: int = 0
    skipped: int = 0
    students: list[Student] = field(default_factory=list)


def _emit_event(
    db: DBSession,
    *,
    session_id: int,
    student_id: int | None,
    action: str,
    details: dict,
) -> None:
    """Persist an audit-log ``Event`` row (no commit - caller commits)."""
    db.add(
        Event(
            session_id=session_id,
            student_id=student_id,
            action=action,
            details_json=details,
        )
    )


def _mark_error(
    db: DBSession,
    student: Student,
    *,
    step: str,
    reason: str,
) -> None:
    """Flip a student to ``error`` and emit a ``student.provision_failed`` event."""
    student.status = StudentStatus.error
    _emit_event(
        db,
        session_id=student.session_id,
        student_id=student.id,
        action="student.provision_failed",
        details={
            "student_id": student.id,
            "session_id": student.session_id,
            "ludus_userid": student.ludus_userid,
            "step": step,
            "reason": reason,
        },
    )
    db.commit()
    logger.warning(
        "student.provision_failed id=%s step=%s reason=%s",
        student.id,
        step,
        reason,
    )


def _write_wg_config(
    storage_dir: Path,
    session_id: int,
    userid: str,
    cfg_text: str,
) -> Path:
    """Write ``cfg_text`` to ``{storage_dir}/{session_id}/{userid}.conf``.

    The parent directory is (re)created with mode ``0o700`` and the file
    is written via ``os.open(..., O_WRONLY|O_CREAT|O_TRUNC, 0o600)`` so
    the on-disk permissions are immune to the process umask.
    """
    parent = storage_dir / str(session_id)
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Enforce parent mode even if it pre-existed with looser bits.
    os.chmod(parent, 0o700)

    path = parent / f"{userid}.conf"
    fd = os.open(
        str(path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(cfg_text)
    except Exception:
        # os.fdopen takes ownership of fd on success; only close on
        # the rare path where fdopen itself raises.
        os.close(fd)
        raise
    # Re-assert mode in case the file pre-existed with looser bits.
    os.chmod(path, 0o600)
    return path


def _resolve_range_number(ludus: LudusClient, shared_range_id: str) -> int | None:
    """Resolve a shared_range_id (rangeID string like "BL") to its rangeNumber.

    Ludus v2 assign endpoint needs the rangeNumber, not the rangeID string.
    Returns ``None`` if no matching range is found.
    """
    try:
        ranges = ludus.range_list()
    except LudusError:
        return None
    for r in ranges:
        if isinstance(r, dict) and r.get("rangeID") == shared_range_id:
            rn = r.get("rangeNumber")
            if isinstance(rn, int):
                return rn
    return None


def _provision_one(
    db: DBSession,
    ludus: LudusClient,
    session_row: SessionRow,
    lab_template: LabTemplate,
    student: Student,
    storage_dir: Path,
    *,
    resolved_range_number: int | None = None,
) -> bool:
    """Drive the Ludus lifecycle for a single student.

    Returns ``True`` if the student ends in ``ready``, ``False`` otherwise.
    All error paths commit a ``student.provision_failed`` event and flip
    the row to ``error`` via :func:`_mark_error`.
    """
    # Short-circuit: if we already have a config on disk for a ready
    # student, don't re-call Ludus. This keeps the endpoint idempotent
    # across retries.
    if (
        student.status == StudentStatus.ready
        and student.wg_config_path
        and Path(student.wg_config_path).exists()
    ):
        return True

    userid = student.ludus_userid

    # 1. user_add (idempotent on LudusUserExists).
    try:
        ludus.user_add(
            userid=userid,
            name=student.full_name,
            email=f"{userid}@ctf.local",
        )
    except LudusUserExists:
        logger.debug("provision: ludus user %s already exists, continuing", userid)
    except LudusError as exc:
        _mark_error(db, student, step="user_add", reason=repr(exc))
        return False

    # 2. range_assign (shared) or range_deploy (dedicated).
    if session_row.mode == SessionMode.shared:
        if not session_row.shared_range_id:
            _mark_error(
                db,
                student,
                step="range_assign",
                reason="session.shared_range_id is None",
            )
            return False
        # Ludus v2 assign endpoint may not recognise the rangeID string
        # returned by /range/all; pass the rangeNumber instead.
        assign_id = (
            str(resolved_range_number)
            if resolved_range_number is not None
            else session_row.shared_range_id
        )
        try:
            ludus.range_assign(userid=userid, range_id=assign_id)
        except LudusNotFound:
            # Fallback: try the original rangeID string if rangeNumber failed.
            if assign_id != session_row.shared_range_id:
                try:
                    ludus.range_assign(
                        userid=userid, range_id=session_row.shared_range_id
                    )
                except LudusError as exc2:
                    _mark_error(db, student, step="range_assign", reason=repr(exc2))
                    return False
            else:
                _mark_error(
                    db,
                    student,
                    step="range_assign",
                    reason=f"Range {assign_id} not found on Ludus",
                )
                return False
        except LudusError as exc:
            _mark_error(db, student, step="range_assign", reason=repr(exc))
            return False
        assigned_range_id: str | None = session_row.shared_range_id
    else:
        try:
            ludus.range_deploy(
                userid=userid,
                config_yaml=lab_template.range_config_yaml,
            )
        except LudusError as exc:
            _mark_error(db, student, step="range_deploy", reason=repr(exc))
            return False
        # TODO: LudusClient.range_deploy currently returns None. Once
        # Ludus exposes the newly-created range identifier via the
        # deploy response, surface it here instead of leaving None.
        assigned_range_id = None

    # 3. user_wireguard -> raw .conf text.
    try:
        cfg_text = ludus.user_wireguard(userid=userid)
    except LudusError as exc:
        _mark_error(db, student, step="user_wireguard", reason=repr(exc))
        return False

    # 4. Persist the config to disk.
    try:
        cfg_path = _write_wg_config(
            storage_dir,
            session_row.id,
            userid,
            cfg_text,
        )
    except OSError as exc:
        _mark_error(db, student, step="write_config", reason=repr(exc))
        return False

    # 5. Persist on the student + emit success event.
    student.wg_config_path = str(cfg_path)
    student.status = StudentStatus.ready
    student.range_id = assigned_range_id

    _emit_event(
        db,
        session_id=session_row.id,
        student_id=student.id,
        action="student.provisioned",
        details={
            "student_id": student.id,
            "session_id": session_row.id,
            "userid": userid,
            "mode": session_row.mode.value,
            "range_id": assigned_range_id,
            "config_path": str(cfg_path),
        },
    )
    db.commit()
    logger.info(
        "student.provisioned id=%s userid=%s mode=%s",
        student.id,
        userid,
        session_row.mode.value,
    )
    return True


def provision_session(
    db: DBSession,
    session_id: int,
    settings: Settings,
    *,
    ludus: LudusClient | None = None,
    registry: LudusClientRegistry | None = None,
) -> ProvisionResult:
    """Drive the full Ludus provisioning flow for every student in a session.

    See module docstring for the per-student pipeline. Returns a
    :class:`ProvisionResult` with counts + the refreshed student rows.

    The Ludus client is resolved from the lab template's ``ludus_server``
    field via *registry*. For backwards compatibility, a single *ludus*
    client can be passed directly (used by older call-sites / tests).

    Raises :class:`SessionNotFound` if the session id is unknown; the
    caller maps that to HTTP 404. Raises ``ValueError`` if the lab
    template's ``ludus_server`` is not configured in the registry.
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
    if lab_template is None:
        # Defensive: the FK should prevent this, but guard anyway so a
        # dangling reference doesn't NPE deep in the per-student loop.
        raise SessionNotFound(
            f"session id={session_id} references missing lab_template_id="
            f"{session_row.lab_template_id}"
        )

    # Resolve the Ludus client: prefer registry (server-aware), fall back
    # to the explicitly-passed client for backwards compat.
    if ludus is None:
        if registry is None:
            raise ValueError("Either ludus or registry must be provided")
        server_name = getattr(lab_template, "ludus_server", "default") or "default"
        ludus = registry.get(server_name)  # raises ValueError on unknown

    result = ProvisionResult()

    if not session_row.students:
        logger.info("provision: session id=%s has no students, nothing to do", session_id)
        return result

    # For shared-mode sessions, resolve the rangeID to a rangeNumber once
    # before the student loop (avoids repeated range_list API calls).
    resolved_range_number: int | None = None
    if (
        session_row.mode == SessionMode.shared
        and session_row.shared_range_id
    ):
        resolved_range_number = _resolve_range_number(
            ludus, session_row.shared_range_id
        )
        if resolved_range_number is not None:
            logger.info(
                "provision: resolved shared_range_id=%s -> rangeNumber=%d",
                session_row.shared_range_id,
                resolved_range_number,
            )

    # Signal that a provisioning pass is in flight before we start
    # calling Ludus, so concurrent callers see the state transition.
    prior_status = session_row.status
    session_row.status = SessionStatus.provisioning
    db.commit()

    for student in list(session_row.students):
        if student.status == StudentStatus.ready:
            result.skipped += 1
            logger.debug(
                "provision: skipping already-ready student id=%s userid=%s",
                student.id,
                student.ludus_userid,
            )
            continue

        storage_dir = Path(settings.config_storage_dir)
        ok = _provision_one(
            db,
            ludus,
            session_row,
            lab_template,
            student,
            storage_dir,
            resolved_range_number=resolved_range_number,
        )
        if ok:
            result.provisioned += 1
        else:
            result.failed += 1

    # Decide the final session status. If any student is ready (either
    # from this pass or a previous skipped/ready row), promote to active.
    db.refresh(session_row)
    any_ready = any(s.status == StudentStatus.ready for s in session_row.students)
    session_row.status = SessionStatus.active if any_ready else prior_status
    db.commit()

    # Return students in a stable order so the response is deterministic.
    ordered_stmt = select(Student).where(Student.session_id == session_id).order_by(Student.id)
    result.students = list(db.execute(ordered_stmt).scalars().all())
    return result


__all__ = [
    "ProvisionResult",
    "SessionNotFound",
    "provision_session",
]
