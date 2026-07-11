"""Host resource-capacity view for the dashboard.

"How much CPU/RAM can I still assign" is derived from two sources:

* **Capacity** (physical total): configured manually - env settings for the
  ``default`` server, ``cpu_capacity``/``ram_capacity_gb`` columns for
  DB-managed servers.
* **Allocated** (in use): summed from *this app's own sessions* - the CPU/RAM
  each live session commits, using the same demand math as the quota feature
  (:mod:`app.services.resources`). Only sessions that are actually consuming
  resources count: ``active`` and ``provisioning`` (``draft`` has not
  provisioned yet, ``ended`` has been torn down). This deliberately ignores
  ranges created outside the app so the dashboard reflects what you deployed.

``available = capacity - allocated`` (may go negative when overcommitted; the
router/UI surface that rather than clamping the truth).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models import LabTemplate, SessionStatus, StudentStatus
from app.models import Session as SessionRow
from app.services.resources import (
    RangeResources,
    compute_range_resources,
    compute_session_demand,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

    from app.core.config import Settings

logger = logging.getLogger(__name__)

# Sessions in these states are actively holding resources on the host.
_CONSUMING_STATUSES = (SessionStatus.active, SessionStatus.provisioning)


@dataclass(frozen=True)
class Allocation:
    """Summed resources across a server's live sessions."""

    resources: RangeResources
    session_count: int


def compute_sessions_allocation(db: DBSession, server: str) -> Allocation:
    """Sum the CPU/RAM committed by this app's live sessions on *server*.

    A session's demand is its lab template's per-range cost scaled by mode
    (shared = one range; dedicated = one per student) - identical to what the
    provision-time quota check enforces. Only sessions whose lab template
    targets *server* and whose status is consuming are counted.
    """
    stmt = (
        select(SessionRow)
        .options(joinedload(SessionRow.students))
        .join(LabTemplate, LabTemplate.id == SessionRow.lab_template_id)
        .where(
            SessionRow.status.in_(_CONSUMING_STATUSES),
            LabTemplate.ludus_server == server,
        )
    )
    sessions = db.execute(stmt).unique().scalars().all()

    total = RangeResources()
    for session in sessions:
        lab = db.get(LabTemplate, session.lab_template_id)
        if lab is None:
            continue
        per_range = compute_range_resources(lab.range_config_yaml)
        # Only ranges actually deployed (ready students) consume resources; a
        # student whose range was removed / never provisioned does not count.
        deployed = sum(1 for s in session.students if s.status == StudentStatus.ready)
        demand = compute_session_demand(per_range, session.mode, deployed)
        total = total + demand
    return Allocation(resources=total, session_count=len(sessions))


def resolve_capacity(
    db: DBSession,
    settings: Settings,
    server: str,
) -> tuple[int | None, int | None]:
    """Return (cpu_capacity, ram_capacity_gb) for *server* (None = unset).

    The ``default`` server's capacity comes from env settings; DB-managed
    servers store theirs on the ``ludus_servers`` row.
    """
    if server == "default":
        return settings.ludus_default_cpu_capacity, settings.ludus_default_ram_capacity_gb

    from app.models.ludus_server import LudusServer

    row = db.query(LudusServer).filter(LudusServer.name == server).first()
    if row is None:
        return None, None
    return row.cpu_capacity, row.ram_capacity_gb


@dataclass(frozen=True)
class CapacityView:
    """Everything the dashboard needs for one server's capacity card."""

    server: str
    configured: bool
    cpu_capacity: int | None
    ram_capacity_gb: int | None
    cpu_allocated: int
    ram_allocated_gb: int
    cpu_available: int | None
    ram_available_gb: int | None
    session_count: int


def build_capacity_view(
    db: DBSession,
    settings: Settings,
    server: str,
) -> CapacityView:
    """Assemble the capacity/allocation/available view for one server."""
    cpu_cap, ram_cap = resolve_capacity(db, settings, server)
    alloc = compute_sessions_allocation(db, server)
    cpu_used = alloc.resources.cpus
    ram_used = alloc.resources.ram_gb
    return CapacityView(
        server=server,
        configured=cpu_cap is not None or ram_cap is not None,
        cpu_capacity=cpu_cap,
        ram_capacity_gb=ram_cap,
        cpu_allocated=cpu_used,
        ram_allocated_gb=ram_used,
        cpu_available=(cpu_cap - cpu_used) if cpu_cap is not None else None,
        ram_available_gb=(ram_cap - ram_used) if ram_cap is not None else None,
        session_count=alloc.session_count,
    )


__all__ = [
    "Allocation",
    "CapacityView",
    "build_capacity_view",
    "compute_sessions_allocation",
    "resolve_capacity",
]
