"""Pydantic schemas for Session create/read operations.

Semantics note on ``shared_range_id``:

* ``mode == "shared"`` + ``shared_range_id is None``: permitted. The provision
  step is allowed to auto-create or auto-pick a shared range.
* ``mode == "shared"`` + ``shared_range_id`` set: permitted. Caller is binding
  the session to an existing range.
* ``mode == "dedicated"`` + ``shared_range_id`` set: permitted but semantically
  redundant; dedicated sessions give each student their own range. The model
  validator keeps this allowed rather than rejecting it so that callers can
  later flip modes without losing data.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import LabMode, SessionStatus
from app.schemas.student import StudentRead


class SessionCreate(BaseModel):
    """Payload to create a new training session."""

    name: str
    lab_template_id: int
    mode: LabMode
    start_date: datetime | None = None
    end_date: datetime | None = None
    shared_range_id: str | None = None
    # Provisioning budget for the whole session. None = unlimited. Enforced
    # as a hard block at provision time (see app.services.resources).
    cpu_quota: int | None = Field(default=None, ge=1)
    ram_quota_gb: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_mode_range_consistency(self) -> "SessionCreate":
        """Permit all mode/shared_range_id combinations (see module docstring).

        This hook exists so that a future stricter policy has an obvious
        place to land; for now it is intentionally a no-op beyond documenting
        the allowed combinations.
        """
        return self


class SessionPatch(BaseModel):
    """Payload to partially update a draft session.

    ``model_fields_set`` distinguishes "field omitted" from "field set to
    None". Setting ``cpu_quota``/``ram_quota_gb`` to null clears the budget
    (unlimited); omitting them leaves the stored value untouched.
    """

    shared_range_id: str | None = None
    cpu_quota: int | None = Field(default=None, ge=1)
    ram_quota_gb: int | None = Field(default=None, ge=1)


class SessionRead(BaseModel):
    """Public representation of a stored training session."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    lab_template_id: int
    mode: LabMode
    start_date: datetime | None = None
    end_date: datetime | None = None
    shared_range_id: str | None = None
    cpu_quota: int | None = None
    ram_quota_gb: int | None = None
    status: SessionStatus
    created_at: datetime


class SessionDetailRead(SessionRead):
    """Detailed session view with embedded students.

    The ``students`` list is built by the endpoint layer so that each
    ``StudentRead`` carries a derived ``invite_url`` (see
    ``app.schemas.student`` for why the URL is not stored on the ORM).
    """

    students: list[StudentRead] = []


class SessionQuotaRead(BaseModel):
    """Computed resource footprint for a session vs its configured budget.

    Powers the provision preflight / usage gauge in the UI. ``within_quota``
    is ``True`` when no budget is set (unlimited) or demand fits the budget.
    """

    mode: LabMode
    student_count: int
    # Students whose range is actually deployed (status == ready).
    ready_count: int = 0
    # Cost of a single deployed range (one student's worth).
    per_range_cpus: int
    per_range_ram_gb: int
    # Planned footprint once every enrolled student is provisioned (quota gate).
    demand_cpus: int
    demand_ram_gb: int
    # Currently-allocated footprint (only deployed ranges) - drops when a range
    # is removed.
    allocated_cpus: int = 0
    allocated_ram_gb: int = 0
    # Configured ceilings (None = unlimited).
    cpu_quota: int | None = None
    ram_quota_gb: int | None = None
    within_quota: bool


__all__ = [
    "SessionCreate",
    "SessionDetailRead",
    "SessionPatch",
    "SessionQuotaRead",
    "SessionRead",
]
