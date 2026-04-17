"""Student ORM model (one enrollment per student per session)."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.session import Session


class StudentStatus(enum.StrEnum):
    """Provisioning state of a student's lab access."""

    pending = "pending"
    ready = "ready"
    error = "error"


class Student(Base):
    """A single enrolled student within a session."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ludus_userid: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    range_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wg_config_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    invite_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    invite_redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[StudentStatus] = mapped_column(
        SAEnum(StudentStatus, name="student_status"),
        nullable=False,
        default=StudentStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    session: Mapped[Session] = relationship("Session", back_populates="students")
