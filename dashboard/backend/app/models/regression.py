"""RegressionEvent and Alert models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, DateTime, Boolean, func, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

import enum


class RegressionSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertChannel(str, enum.Enum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class RegressionEvent(Base):
    __tablename__ = "regression_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    cassette_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cassettes.id"), nullable=False)
    golden_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("golden_sets.id"), nullable=True
    )

    severity: Mapped[str] = mapped_column(
        SAEnum(RegressionSeverity, name="regression_severity", create_constraint=False),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    cassette: Mapped["StoredCassette"] = relationship("StoredCassette")  # noqa: F821


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    regression_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regression_events.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(
        SAEnum(AlertChannel, name="alert_channel", create_constraint=False),
        nullable=False,
    )
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    regression_event: Mapped[RegressionEvent] = relationship("RegressionEvent")
