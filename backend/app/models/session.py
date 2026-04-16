"""Session ORM model (a class/cohort running a lab template)."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.student import Student


class SessionMode(enum.StrEnum):
    """Whether all students share one range or each gets a dedicated range."""

    shared = "shared"
    dedicated = "dedicated"


class SessionStatus(enum.StrEnum):
    """Lifecycle status of a training session."""

    draft = "draft"
    provisioning = "provisioning"
    active = "active"
    ended = "ended"


class Session(Base):
    """A scheduled run of a lab template for a group of students."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lab_template_id: Mapped[int] = mapped_column(
        ForeignKey("lab_templates.id"), nullable=False
    )
    mode: Mapped[SessionMode] = mapped_column(
        SAEnum(SessionMode, name="session_mode"),
        nullable=False,
    )
    shared_range_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, name="session_status"),
        nullable=False,
        default=SessionStatus.draft,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    students: Mapped[list[Student]] = relationship(
        "Student",
        back_populates="session",
        cascade="all, delete-orphan",
    )
