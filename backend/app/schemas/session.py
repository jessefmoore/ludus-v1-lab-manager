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

from pydantic import BaseModel, ConfigDict, model_validator

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

    @model_validator(mode="after")
    def _check_mode_range_consistency(self) -> "SessionCreate":
        """Permit all mode/shared_range_id combinations (see module docstring).

        This hook exists so that a future stricter policy has an obvious
        place to land; for now it is intentionally a no-op beyond documenting
        the allowed combinations.
        """
        return self


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
    status: SessionStatus
    created_at: datetime


class SessionDetailRead(SessionRead):
    """Detailed session view with embedded students.

    The ``students`` list is built by the endpoint layer so that each
    ``StudentRead`` carries a derived ``invite_url`` (see
    ``app.schemas.student`` for why the URL is not stored on the ORM).
    """

    students: list[StudentRead] = []


__all__ = ["SessionCreate", "SessionDetailRead", "SessionRead"]
