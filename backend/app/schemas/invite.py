"""Pydantic schemas for the public invite flow."""

from datetime import datetime

from pydantic import BaseModel


class InvitePageData(BaseModel):
    """Data rendered on the public invite landing page."""

    student_name: str
    lab_name: str
    lab_description: str | None = None
    entry_point_vm: str | None = None
    expires_at: datetime
    download_url: str


__all__ = ["InvitePageData"]
