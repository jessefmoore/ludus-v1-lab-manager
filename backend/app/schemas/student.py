"""Pydantic schemas for Student create/read operations.

Design note on ``invite_url``:

* ``invite_token`` is intentionally NOT exposed on ``StudentRead`` - the
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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import StudentStatus


class StudentCreate(BaseModel):
    """Payload to enroll a new student into a session.

    Two modes:
    * **Manual** - ``full_name`` + ``email`` required, ``ludus_userid`` absent.
    * **Ludus user** - ``ludus_userid`` set, ``full_name``/``email`` optional.
    """

    full_name: str | None = None
    # A lightly-validated string, NOT EmailStr: these are lab identifiers and
    # the app deliberately uses reserved ``.local`` domains (e.g.
    # ``RTA1@ludus.local``) that EmailStr rejects as "special-use". We only
    # require a basic ``local@domain`` shape.
    email: str | None = Field(default=None, max_length=254)
    # Ludus enforces ^[A-Za-z0-9]{1,20}$ for userIDs (no hyphens/punctuation).
    # Validate it here so a bad ID fails at enrollment, not deep in provisioning.
    ludus_userid: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{1,20}$")

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # Minimal sanity: exactly one '@' with non-empty local and domain parts.
        local, sep, domain = v.partition("@")
        if not sep or not local or not domain:
            raise ValueError("email must be of the form name@domain")
        return v

    @model_validator(mode="after")
    def check_either_manual_or_ludus(self) -> Self:
        if self.ludus_userid:
            return self  # Ludus user mode - name/email are optional
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
