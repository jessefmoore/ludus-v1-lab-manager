"""LabTemplate ORM model (reusable lab definitions)."""

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LabTemplateMode(enum.StrEnum):
    """Default provisioning mode for a lab template."""

    shared = "shared"
    dedicated = "dedicated"


class LabTemplate(Base):
    """A reusable lab definition (Ludus range-config) an instructor can spin up."""

    __tablename__ = "lab_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    range_config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    default_mode: Mapped[LabTemplateMode] = mapped_column(
        SAEnum(LabTemplateMode, name="lab_template_mode"),
        nullable=False,
    )
    ludus_server: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    entry_point_vm: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
