"""Event ORM model (audit log of mutating actions)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Event(Base):
    """An audit-log entry emitted for every mutating action in the platform."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
