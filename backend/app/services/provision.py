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

import yaml
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.models import LabTemplate, SessionMode, SessionStatus, Student, StudentStatus
from app.models import Session as SessionRow
from app.models.event import Event
from app.services.exceptions import LudusError, LudusUserExists
from app.services.resources import compute_range_resources, compute_session_demand

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from app.core.deps import LudusClientRegistry
    from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):  # noqa: N818 -- spec-mandated name
    """Raised when ``session_id`` does not correspond to an existing session."""


class QuotaExceeded(Exception):  # noqa: N818 -- consistent with SessionNotFound
    """Raised when a session's resource demand exceeds its configured budget.

    Carries the computed demand and the breached ceilings so the router can
    build an actionable 409 message. Provisioning is aborted *before* any
    Ludus call is made, so no partial range is created.
    """

    def __init__(
        self,
        *,
        demand_cpus: int,
        demand_ram_gb: int,
        cpu_quota: int | None,
        ram_quota_gb: int | None,
        student_count: int,
    ) -> None:
        self.demand_cpus = demand_cpus
        self.demand_ram_gb = demand_ram_gb
        self.cpu_quota = cpu_quota
        self.ram_quota_gb = ram_quota_gb
        self.student_count = student_count
        breaches = []
        if cpu_quota is not None and demand_cpus > cpu_quota:
            breaches.append(f"CPU {demand_cpus} > quota {cpu_quota}")
        if ram_quota_gb is not None and demand_ram_gb > ram_quota_gb:
            breaches.append(f"RAM {demand_ram_gb}GB > quota {ram_quota_gb}GB")
        super().__init__(
            "Session resource demand exceeds its quota ("
            + "; ".join(breaches)
            + f") for {student_count} student(s)"
        )


def check_session_quota(
    session_row: SessionRow,
    lab_template: LabTemplate,
) -> None:
    """Raise :class:`QuotaExceeded` if the session over-runs its budget.

    Demand is the session's *full* footprint (all enrolled students), not
    just the current provisioning batch, so a quota check is stable across
    repeated/partial provision passes. A ``None`` ceiling means unlimited on
    that dimension. No-op when both ceilings are unset.
    """
    cpu_quota = session_row.cpu_quota
    ram_quota_gb = session_row.ram_quota_gb
    if cpu_quota is None and ram_quota_gb is None:
        return

    per_range = compute_range_resources(lab_template.range_config_yaml)
    student_count = len(session_row.students)
    demand = compute_session_demand(per_range, session_row.mode, student_count)

    over_cpu = cpu_quota is not None and demand.cpus > cpu_quota
    over_ram = ram_quota_gb is not None and demand.ram_gb > ram_quota_gb
    if over_cpu or over_ram:
        raise QuotaExceeded(
            demand_cpus=demand.cpus,
            demand_ram_gb=demand.ram_gb,
            cpu_quota=cpu_quota,
            ram_quota_gb=ram_quota_gb,
            student_count=student_count,
        )


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


def _collect_roles(roles_raw: list) -> set[str]:
    """Extract role names from a roles list (string or dict-with-``name``)."""
    names: set[str] = set()
    for entry in roles_raw:
        if isinstance(entry, str) and entry:
            names.add(entry)
        elif isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name:
                names.add(name)
    return names


def extract_role_names(range_config_yaml: str) -> list[str]:
    """Parse ``range_config_yaml`` for Ansible role names.

    Supports both a top-level ``roles:`` key and per-VM roles nested
    under ``ludus[].roles[]`` (the standard Ludus range config format)::

        ludus:
          - vm_name: DC
            roles:
              - ansible-role-foosha          # plain string
              - name: ansible-role-barbaz    # dict with 'name' key

    Returns a sorted, deduplicated list.  Returns ``[]`` on any parse failure.
    """
    try:
        data = yaml.safe_load(range_config_yaml)
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []

    names: set[str] = set()

    # Top-level roles: key
    top_roles = data.get("roles")
    if isinstance(top_roles, list):
        names |= _collect_roles(top_roles)

    # Per-VM roles under ludus[].roles[]
    ludus_vms = data.get("ludus")
    if isinstance(ludus_vms, list):
        for vm in ludus_vms:
            if isinstance(vm, dict):
                vm_roles = vm.get("roles")
                if isinstance(vm_roles, list):
                    names |= _collect_roles(vm_roles)

    return sorted(names)


def _ensure_roles_global_scope(
    db: DBSession,
    ludus: LudusClient,
    session_id: int,
    range_config_yaml: str,
) -> None:
    """Scope Ansible roles globally so new Ludus users can access them.

    Idempotent - safe to call repeatedly.  On failure the warning is logged
    and a ``session.role_scope_failed`` event is emitted, but provisioning
    is **not** aborted.
    """
    roles = extract_role_names(range_config_yaml)
    if not roles:
        return

    try:
        # Ludus v1 has no role-scope endpoint; installing a role globally is
        # how it is made available to all users.
        ludus.ansible_scope_roles_global(roles)
    except Exception as exc:
        logger.warning(
            "provision: failed to scope roles %s globally for session id=%s: %s",
            roles,
            session_id,
            exc,
        )
        _emit_event(
            db,
            session_id=session_id,
            student_id=None,
            action="session.role_scope_failed",
            details={
                "session_id": session_id,
                "roles": roles,
                "reason": repr(exc),
            },
        )
        db.commit()


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


def _auto_create_shared_range(
    db: DBSession,
    ludus: LudusClient,
    session_row: SessionRow,
    lab_template: LabTemplate,
    lead_student: Student,
) -> None:
    """Create the lead student's Ludus user and deploy the shared range.

    On Ludus v1 a user owns exactly one range, addressed by that user's ID.
    The "shared range" is therefore simply the lead student's range: other
    students are granted cross-range access to it (see
    :func:`_provision_one`). ``session_row.shared_range_id`` stores the lead
    student's ``userID`` (the owner of the shared range).

    Steps:
        1. ``user_add`` for the lead student (idempotent).
        2. ``range_deploy`` with the lab template config.
        3. Persist ``shared_range_id = lead userID`` and commit.

    Raises ``LudusError`` on any Ludus failure so the caller can decide how
    to handle it (mark the lead student as error, etc.).
    """
    userid = lead_student.ludus_userid

    # 1. Create the user (idempotent).
    try:
        ludus.user_add(
            userid=userid,
            name=lead_student.full_name,
            email=f"{userid}@ctf.local",
        )
    except LudusUserExists:
        logger.debug("auto_create_range: user %s already exists", userid)

    # 2. Deploy the lab template config for this user's range.
    ludus.range_deploy(
        userid=userid,
        config_yaml=lab_template.range_config_yaml,
    )

    # 3. The shared range is the lead user's range, identified by userID.
    session_row.shared_range_id = userid
    _emit_event(
        db,
        session_id=session_row.id,
        student_id=lead_student.id,
        action="session.range_auto_created",
        details={
            "session_id": session_row.id,
            "range_owner_userid": userid,
            "lead_userid": userid,
        },
    )
    db.commit()
    logger.info(
        "provision: auto-created shared range owned by user %s for session id=%s",
        userid,
        session_row.id,
    )


# Ludus range states that mean "already has live VMs" vs "a deploy is
# already in flight". Anything else (NEVER DEPLOYED, DESTROYED, ERROR, or an
# empty VM list) means the range must be deployed before it is usable.
_LIVE_RANGE_STATE = "SUCCESS"
_ACTIVE_RANGE_STATES = frozenset({"DEPLOYING", "BUILDING", "PENDING", "TESTING"})


def _range_needs_deploy(ludus: LudusClient, userid: str) -> bool:
    """Return True if *userid*'s range must be (re)deployed to have live VMs.

    A missing user/range, a never-deployed/destroyed/errored range, or a
    range with zero VMs all need a deploy. A range that is already
    ``SUCCESS`` with VMs - or one whose deploy is currently in flight - does
    not. Network/Ludus hiccups fall back to "needs deploy" so we err toward
    actually deploying rather than silently skipping.
    """
    try:
        info = ludus.range_get_vms(user_id=userid)
    except LudusError:
        return True
    state = str(info.get("rangeState") or "").upper()
    if state in _ACTIVE_RANGE_STATES:
        return False
    vms = info.get("VMs") or []
    return not (state == _LIVE_RANGE_STATE and len(vms) > 0)


def _range_confirmed_up(ludus: LudusClient, userid: str) -> bool:
    """Return True once *userid*'s range is fully deployed and powered on.

    The "deploy confirmed" gate: the range must be ``SUCCESS`` with at least
    one VM and *every* VM reporting ``poweredOn``. A range still deploying,
    errored, empty, or with any VM off is not yet confirmed. Any Ludus/network
    error is treated as "not confirmed" so we keep waiting rather than falsely
    flipping a student to ready.
    """
    try:
        info = ludus.range_get_vms(user_id=userid)
    except LudusError:
        return False
    state = str(info.get("rangeState") or "").upper()
    if state != _LIVE_RANGE_STATE:
        return False
    vms = info.get("VMs") or []
    if not vms:
        return False
    return all(bool(vm.get("poweredOn")) for vm in vms)


def _provision_one(
    db: DBSession,
    ludus: LudusClient,
    session_row: SessionRow,
    lab_template: LabTemplate,
    student: Student,
    storage_dir: Path,
    *,
    lead_userid: str | None = None,
    lead_range_deployed: bool = True,
) -> bool:
    """Drive the Ludus lifecycle for a single student.

    Returns ``True`` if the student ends in ``ready``, ``False`` otherwise.
    All error paths commit a ``student.provision_failed`` event and flip
    the row to ``error`` via :func:`_mark_error`.

    When *lead_userid* is set and matches the student's ``ludus_userid``,
    the ``user_add`` and range-access steps are skipped because this student
    already owns the shared range.

    *lead_range_deployed* says whether the lead's shared range is already
    live. It is ``True`` for a just-auto-created range (deploy already fired)
    and ``False`` when a *pre-existing* owner range was picked - which may be
    empty/never-deployed, so the lead still needs a real ``range_deploy``
    before students can use it.
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
    is_lead = lead_userid is not None and userid == lead_userid

    # 1. user_add (idempotent on LudusUserExists).
    # Skipped for the lead user, who already exists (auto-created, or the
    # owner of a pre-existing range that was picked).
    if not is_lead:
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

    # 2. range access grant (shared) or range_deploy (dedicated).
    # Lead user already owns the shared range; skip the access grant.
    if is_lead and session_row.mode == SessionMode.shared:
        assigned_range_id: str | None = session_row.shared_range_id
        # A pre-existing owner range was picked. Reuse it only if it is
        # actually deployed; otherwise deploy the lab config into it now so
        # we never mark students ready against an empty/never-deployed range.
        if not lead_range_deployed and _range_needs_deploy(ludus, userid):
            try:
                ludus.range_deploy(
                    userid=userid,
                    config_yaml=lab_template.range_config_yaml,
                )
            except LudusError as exc:
                _mark_error(db, student, step="range_deploy", reason=repr(exc))
                return False
            _emit_event(
                db,
                session_id=session_row.id,
                student_id=student.id,
                action="session.shared_range_deployed",
                details={
                    "session_id": session_row.id,
                    "range_owner": userid,
                },
            )
    elif session_row.mode == SessionMode.shared:
        if not session_row.shared_range_id:
            _mark_error(
                db,
                student,
                step="range_access_grant",
                reason="session.shared_range_id is None",
            )
            return False
        # Ludus v1: grant this student's user access to the shared range,
        # which is owned by the lead user (shared_range_id == lead userID).
        try:
            ludus.range_access_grant(
                source_user_id=userid,
                target_user_id=session_row.shared_range_id,
            )
        except LudusError as exc:
            _mark_error(db, student, step="range_access_grant", reason=repr(exc))
            return False
        assigned_range_id = session_row.shared_range_id
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

    # 5. Persist config on the student. The status depends on whether the
    #    range the student depends on is actually up yet: a shared student
    #    depends on the owner's range, a dedicated student on its own. The
    #    student is only "ready" once that range is confirmed up (SUCCESS with
    #    every VM powered on); otherwise it is "deploying" and a later
    #    deploy-status poll flips it to ready (or error).
    student.wg_config_path = str(cfg_path)
    student.range_id = assigned_range_id

    range_owner = (
        session_row.shared_range_id
        if session_row.mode == SessionMode.shared
        else userid
    )
    if range_owner and _range_confirmed_up(ludus, range_owner):
        student.status = StudentStatus.ready
        action = "student.provisioned"
    else:
        student.status = StudentStatus.deploying
        action = "student.deploying"

    _emit_event(
        db,
        session_id=session_row.id,
        student_id=student.id,
        action=action,
        details={
            "student_id": student.id,
            "session_id": session_row.id,
            "userid": userid,
            "mode": session_row.mode.value,
            "range_id": assigned_range_id,
            "config_path": str(cfg_path),
            "status": student.status.value,
        },
    )
    db.commit()
    logger.info(
        "%s id=%s userid=%s mode=%s",
        action,
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

    # Enforce the session's resource budget BEFORE any Ludus interaction so
    # a quota breach never leaves a half-created range behind. Hard block.
    check_session_quota(session_row, lab_template)

    # Resolve the Ludus client: prefer registry (server-aware), fall back
    # to the explicitly-passed client for backwards compat.
    if ludus is None:
        if registry is None:
            raise ValueError("Either ludus or registry must be provided")
        server_name = getattr(lab_template, "ludus_server", "default") or "default"
        ludus = registry.get(server_name)  # raises ValueError on unknown

    # Ensure Ansible roles referenced in the lab template are globally
    # scoped so new Ludus users can resolve them during range_deploy.
    _ensure_roles_global_scope(db, ludus, session_id, lab_template.range_config_yaml)

    result = ProvisionResult()

    if not session_row.students:
        logger.info("provision: session id=%s has no students, nothing to do", session_id)
        return result

    # On Ludus v1 the shared range is simply the lead user's range, keyed by
    # that user's ID; there is no rangeID/rangeNumber to resolve.
    lead_userid: str | None = None
    # Whether the lead's shared range is already live. Auto-create fires a
    # deploy, so it is True there; a pre-existing owner range that was picked
    # is not guaranteed to be deployed, so it is False and gets a liveness
    # check + deploy in _provision_one.
    lead_range_deployed = True

    # Auto-create a shared range when shared_range_id is None.
    # Pick the first pending student, create them on Ludus, deploy the lab
    # template config, then discover the newly-created range.
    if (
        session_row.mode == SessionMode.shared
        and not session_row.shared_range_id
    ):
        pending = [s for s in session_row.students if s.status != StudentStatus.ready]
        if pending:
            lead = pending[0]
            lead_userid = lead.ludus_userid
            try:
                _auto_create_shared_range(
                    db, ludus, session_row, lab_template, lead
                )
            except LudusError as exc:
                # Auto-create failed; reset lead_userid so all students
                # go through the normal flow and error with "shared_range_id
                # is None".
                lead_userid = None
                _emit_event(
                    db,
                    session_id=session_row.id,
                    student_id=lead.id,
                    action="session.range_auto_create_failed",
                    details={
                        "session_id": session_row.id,
                        "lead_userid": lead.ludus_userid,
                        "reason": repr(exc),
                    },
                )
                db.commit()
                logger.error(
                    "provision: auto-create range failed for session id=%s: %s",
                    session_id, exc,
                )
            else:
                # Refresh after auto-create committed changes.
                db.refresh(session_row)
    elif session_row.mode == SessionMode.shared and session_row.shared_range_id:
        # A specific existing range was picked: its owner (== shared_range_id)
        # is the lead. Mark them lead so everyone else gets cross-range access
        # to the owner's range. The owner range may be empty/never-deployed
        # (e.g. reusing a fresh user), so flag it as not-yet-deployed - the
        # lead's _provision_one will deploy it if it isn't actually live.
        lead_userid = session_row.shared_range_id
        lead_range_deployed = False

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
            lead_userid=lead_userid,
            lead_range_deployed=lead_range_deployed,
        )
        if ok:
            result.provisioned += 1
        else:
            result.failed += 1

    # Decide the final session status. While any range is still deploying the
    # session stays ``provisioning``; once nothing is deploying it promotes to
    # ``active`` if at least one student is ready, else reverts to its prior
    # status. A deploy-status poll re-runs this transition as ranges settle.
    db.refresh(session_row)
    statuses = [s.status for s in session_row.students]
    if any(s == StudentStatus.deploying for s in statuses):
        session_row.status = SessionStatus.provisioning
    elif any(s == StudentStatus.ready for s in statuses):
        session_row.status = SessionStatus.active
    else:
        session_row.status = prior_status
    db.commit()

    # Return students in a stable order so the response is deterministic.
    ordered_stmt = select(Student).where(Student.session_id == session_id).order_by(Student.id)
    result.students = list(db.execute(ordered_stmt).scalars().all())
    return result


__all__ = [
    "ProvisionResult",
    "QuotaExceeded",
    "SessionNotFound",
    "check_session_quota",
    "extract_role_names",
    "provision_session",
]
