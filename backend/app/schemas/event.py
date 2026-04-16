"""Pydantic schemas for Event (audit log) read operations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    """Public representation of an audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int | None = None
    student_id: int | None = None
    action: str
    details_json: dict[str, Any] | None = None
    created_at: datetime


__all__ = ["EventRead"]
