"""Pydantic schemas for Student create/read operations.

Design note on ``invite_url``:

* ``invite_token`` is intentionally NOT exposed on ``StudentRead`` — the
  raw token is a bearer credential that should only flow through the
  dedicated invite/redeem endpoints.
* ``invite_url`` is a plain ``str`` on the response schema. It must be
  populated by the endpoint layer (e.g.
  ``f"{settings.public_base_url}/invite/{student.invite_token}"``) before
  returning. Keeping settings access out of the schema avoids coupling
  Pydantic models to configuration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

from app.schemas.common import StudentStatus


class StudentCreate(BaseModel):
    """Payload to enroll a new student into a session.

    Two modes:
    * **Manual** — ``full_name`` + ``email`` required, ``ludus_userid`` absent.
    * **Ludus user** — ``ludus_userid`` set, ``full_name``/``email`` optional.
    """

    full_name: str | None = None
    email: EmailStr | None = None
    ludus_userid: str | None = None

    @model_validator(mode="after")
    def check_either_manual_or_ludus(self) -> Self:
        if self.ludus_userid:
            return self  # Ludus user mode — name/email are optional
        if not self.full_name or not self.email:
            raise ValueError("full_name and email are required when ludus_userid is not provided")
        return self


class StudentRead(BaseModel):
    """Public representation of an enrolled student.

    ``invite_url`` is a derived value supplied by the calling endpoint;
    it is not stored on the ORM object. ``invite_token`` is intentionally
    omitted to avoid leaking the bearer credential on list/detail views.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    ludus_userid: str
    range_id: str | None = None
    status: StudentStatus
    invite_redeemed_at: datetime | None = None
    created_at: datetime
    invite_url: str


__all__ = ["StudentCreate", "StudentRead"]
