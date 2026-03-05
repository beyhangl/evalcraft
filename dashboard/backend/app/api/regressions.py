"""Regressions list and trend endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_team_id
from app.database import get_db
from app.models.project import Project
from app.models.regression import RegressionEvent
from app.schemas.api import RegressionEventResponse

router = APIRouter(prefix="/regressions", tags=["regressions"])


@router.get("", response_model=list[RegressionEventResponse])
async def list_regressions(
    project_id: uuid.UUID = Query(...),
    severity: str | None = Query(None, description="Filter: INFO, WARNING, CRITICAL"),
    resolved: bool | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """List regression events with optional severity and resolved filters."""
    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    stmt = (
        select(RegressionEvent)
        .where(RegressionEvent.project_id == project_id)
        .order_by(RegressionEvent.created_at.desc())
    )

    if severity:
        stmt = stmt.where(RegressionEvent.severity == severity.upper())
    if resolved is not None:
        stmt = stmt.where(RegressionEvent.resolved.is_(resolved))

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/{event_id}/resolve", response_model=RegressionEventResponse)
async def resolve_regression(
    event_id: uuid.UUID,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark a regression event as resolved."""
    result = await db.execute(
        select(RegressionEvent)
        .join(Project, RegressionEvent.project_id == Project.id)
        .where(RegressionEvent.id == event_id, Project.team_id == team_id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regression not found")

    event.resolved = True
    await db.flush()
    await db.refresh(event)
    return event
