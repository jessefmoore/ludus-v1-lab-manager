"""Pydantic schemas for LabTemplate create/read operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import LabMode


class LabTemplateCreate(BaseModel):
    """Payload to create a new lab template."""

    name: str
    description: str | None = None
    range_config_yaml: str
    default_mode: LabMode
    ludus_server: str = "default"
    entry_point_vm: str | None = None


class LabTemplateRead(BaseModel):
    """Public representation of a stored lab template."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    range_config_yaml: str
    default_mode: LabMode
    ludus_server: str = "default"
    entry_point_vm: str | None = None
    created_at: datetime


__all__ = ["LabTemplateCreate", "LabTemplateRead"]
