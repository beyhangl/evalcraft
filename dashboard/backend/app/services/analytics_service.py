"""Trend computation for token usage, cost, and latency over time."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cassette import StoredCassette
from app.models.project import Project
from app.schemas.api import TrendPoint, TrendsResponse


async def compute_trends(
    project_id: uuid.UUID,
    team_id: uuid.UUID,
    db: AsyncSession,
    days: int = 30,
) -> TrendsResponse:
    """Aggregate daily metrics for a project over the last N days."""
    # Verify project belongs to team
    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )
    if proj.scalar_one_or_none() is None:
        return TrendsResponse(project_id=project_id, points=[])

    cutoff = date.today() - timedelta(days=days)

    stmt = (
        select(
            cast(StoredCassette.created_at, Date).label("day"),
            func.sum(StoredCassette.total_tokens).label("total_tokens"),
            func.sum(StoredCassette.total_cost_usd).label("total_cost_usd"),
            func.sum(StoredCassette.total_duration_ms).label("total_duration_ms"),
            func.count(StoredCassette.id).label("cassette_count"),
        )
        .where(
            StoredCassette.project_id == project_id,
            cast(StoredCassette.created_at, Date) >= cutoff,
        )
        .group_by("day")
        .order_by("day")
    )

    result = await db.execute(stmt)
    rows = result.all()

    points = [
        TrendPoint(
            date=str(row.day),
            total_tokens=int(row.total_tokens or 0),
            total_cost_usd=float(row.total_cost_usd or 0),
            total_duration_ms=float(row.total_duration_ms or 0),
            cassette_count=int(row.cassette_count or 0),
        )
        for row in rows
    ]

    return TrendsResponse(project_id=project_id, points=points)
