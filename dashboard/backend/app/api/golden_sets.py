"""CRUD API for golden sets."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_team_id
from app.database import get_db
from app.models.cassette import StoredCassette
from app.models.golden_set import StoredGoldenSet
from app.models.project import Project
from app.schemas.api import (
    GoldenSetCreateRequest,
    GoldenSetDetailResponse,
    GoldenSetResponse,
    GoldenSetUpdateRequest,
)

try:
    from evalcraft.core.models import Cassette as CoreCassette
    from evalcraft.golden.manager import GoldenSet as CoreGoldenSet, Thresholds
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from evalcraft.core.models import Cassette as CoreCassette
    from evalcraft.golden.manager import GoldenSet as CoreGoldenSet, Thresholds

router = APIRouter(prefix="/golden-sets", tags=["golden-sets"])


@router.post("", response_model=GoldenSetResponse, status_code=status.HTTP_201_CREATED)
async def create_golden_set(
    body: GoldenSetCreateRequest,
    project_id: uuid.UUID = Query(...),
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a golden set, optionally seeded from existing cassette IDs."""
    # Verify project
    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Build core golden set
    thresholds = Thresholds.from_dict(body.thresholds.model_dump())
    core_gs = CoreGoldenSet(name=body.name, description=body.description, thresholds=thresholds)

    # Load cassettes if specified
    for cid in body.cassette_ids:
        result = await db.execute(
            select(StoredCassette).where(StoredCassette.id == cid, StoredCassette.project_id == project_id)
        )
        stored = result.scalar_one_or_none()
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cassette {cid} not found in project",
            )
        core = CoreCassette.from_dict(stored.raw_data)
        core_gs.add_cassette(core)

    row = StoredGoldenSet(
        project_id=project_id,
        name=body.name,
        description=body.description,
        version=core_gs.version,
        thresholds=body.thresholds.model_dump(),
        raw_data=core_gs.to_dict(),
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


@router.get("", response_model=list[GoldenSetResponse])
async def list_golden_sets(
    project_id: uuid.UUID = Query(...),
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    # Verify project
    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = await db.execute(
        select(StoredGoldenSet)
        .where(StoredGoldenSet.project_id == project_id)
        .order_by(StoredGoldenSet.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{golden_set_id}", response_model=GoldenSetDetailResponse)
async def get_golden_set(
    golden_set_id: uuid.UUID,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_golden_set(golden_set_id, team_id, db)
    return row


@router.patch("/{golden_set_id}", response_model=GoldenSetResponse)
async def update_golden_set(
    golden_set_id: uuid.UUID,
    body: GoldenSetUpdateRequest,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_golden_set(golden_set_id, team_id, db)

    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.thresholds is not None:
        row.thresholds = body.thresholds.model_dump()
        # Also update raw_data thresholds
        raw = dict(row.raw_data)
        raw["thresholds"] = row.thresholds
        row.raw_data = raw

    row.version += 1
    await db.flush()
    await db.refresh(row)
    return row


@router.delete("/{golden_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_golden_set(
    golden_set_id: uuid.UUID,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_golden_set(golden_set_id, team_id, db)
    await db.delete(row)


async def _get_golden_set(
    golden_set_id: uuid.UUID, team_id: uuid.UUID, db: AsyncSession
) -> StoredGoldenSet:
    result = await db.execute(
        select(StoredGoldenSet)
        .join(Project, StoredGoldenSet.project_id == Project.id)
        .where(StoredGoldenSet.id == golden_set_id, Project.team_id == team_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found")
    return row
