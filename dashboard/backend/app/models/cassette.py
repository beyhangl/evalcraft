"""StoredCassette — an uploaded cassette persisted in the database."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, DateTime, Float, Integer, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StoredCassette(Base):
    __tablename__ = "cassettes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    agent_name: Mapped[str] = mapped_column(String(255), default="")
    framework: Mapped[str] = mapped_column(String(100), default="")
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)

    # Aggregate metrics
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)

    # Summary fields
    input_text: Mapped[str] = mapped_column(Text, default="")
    output_text: Mapped[str] = mapped_column(Text, default="")

    # Full cassette JSON (spans + metadata)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Source context
    git_sha: Mapped[str] = mapped_column(String(40), default="")
    branch: Mapped[str] = mapped_column(String(255), default="")
    ci_run_url: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    project: Mapped["Project"] = relationship("Project", back_populates="cassettes")  # noqa: F821
