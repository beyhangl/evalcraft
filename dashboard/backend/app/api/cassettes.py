"""Cassette upload, list, get, and compare endpoints."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_team_id
from app.database import get_db
from app.models.cassette import StoredCassette
from app.models.golden_set import StoredGoldenSet
from app.models.project import Project
from app.schemas.api import (
    CassetteDetail,
    CassetteListItem,
    CassetteUploadMeta,
    CompareRequest,
    CompareResponse,
    CompareFieldResult,
)
from app.services.cassette_service import process_upload
from app.services.regression_service import check_regressions

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from evalcraft.core.models import Cassette as CoreCassette
from evalcraft.golden.manager import GoldenSet as CoreGoldenSet

router = APIRouter(prefix="/cassettes", tags=["cassettes"])


@router.post("/upload", response_model=CassetteListItem, status_code=status.HTTP_201_CREATED)
async def upload_cassette(
    cassette_json: dict,
    project_id: uuid.UUID = Query(...),
    git_sha: str = Query(""),
    branch: str = Query(""),
    ci_run_url: str = Query(""),
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Upload a cassette JSON. Auto-runs regression detection."""
    # Verify project belongs to team
    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    stored = await process_upload(
        raw_data=cassette_json,
        project_id=project_id,
        git_sha=git_sha,
        branch=branch,
        ci_run_url=ci_run_url,
        db=db,
    )

    # Auto-detect regressions
    await check_regressions(cassette_json, project_id, stored.id, db)

    return stored


@router.get("", response_model=list[CassetteListItem])
async def list_cassettes(
    project_id: uuid.UUID = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    agent_name: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """List cassettes with optional filters."""
    # Verify project belongs to team
    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    stmt = (
        select(StoredCassette)
        .where(StoredCassette.project_id == project_id)
        .order_by(StoredCassette.created_at.desc())
    )

    if date_from:
        stmt = stmt.where(cast(StoredCassette.created_at, Date) >= date_from)
    if date_to:
        stmt = stmt.where(cast(StoredCassette.created_at, Date) <= date_to)
    if agent_name:
        stmt = stmt.where(StoredCassette.agent_name == agent_name)

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{cassette_id}", response_model=CassetteDetail)
async def get_cassette(
    cassette_id: uuid.UUID,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Get full cassette detail including spans."""
    result = await db.execute(
        select(StoredCassette)
        .join(Project, StoredCassette.project_id == Project.id)
        .where(StoredCassette.id == cassette_id, Project.team_id == team_id)
    )
    cassette = result.scalar_one_or_none()
    if cassette is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cassette not found")
    return cassette


@router.post("/{cassette_id}/compare", response_model=CompareResponse)
async def compare_cassette(
    cassette_id: uuid.UUID,
    body: CompareRequest,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Compare a cassette against a golden set."""
    # Fetch cassette
    cass_result = await db.execute(
        select(StoredCassette)
        .join(Project, StoredCassette.project_id == Project.id)
        .where(StoredCassette.id == cassette_id, Project.team_id == team_id)
    )
    cassette = cass_result.scalar_one_or_none()
    if cassette is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cassette not found")

    # Fetch golden set
    gs_result = await db.execute(
        select(StoredGoldenSet)
        .join(Project, StoredGoldenSet.project_id == Project.id)
        .where(StoredGoldenSet.id == body.golden_set_id, Project.team_id == team_id)
    )
    golden_set_row = gs_result.scalar_one_or_none()
    if golden_set_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Golden set not found")

    # Use core models to run comparison
    core_gs = CoreGoldenSet.from_dict(golden_set_row.raw_data)
    candidate = CoreCassette.from_dict(cassette.raw_data)
    comparison = core_gs.compare(candidate)

    return CompareResponse(
        passed=comparison.passed,
        golden_name=comparison.golden_name,
        golden_version=comparison.golden_version,
        fields=[
            CompareFieldResult(
                name=f.name,
                passed=f.passed,
                golden_value=f.golden_value,
                candidate_value=f.candidate_value,
                message=f.message,
            )
            for f in comparison.fields
        ],
    )
