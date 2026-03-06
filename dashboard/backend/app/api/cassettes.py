"""Cassette upload, list, get, compare, and diff endpoints."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_team_id
from app.cache import cache_invalidate
from app.database import get_db
from app.models.cassette import StoredCassette
from app.models.golden_set import StoredGoldenSet
from app.models.project import Project
from app.schemas.api import (
    CassetteDetail,
    CassetteDiffField,
    CassetteDiffResponse,
    CassetteListItem,
    CassettePaginatedResponse,
    CassetteUploadMeta,
    CompareRequest,
    CompareResponse,
    CompareFieldResult,
)
from app.services.cassette_service import process_upload
from app.services.regression_service import check_regressions

from evalcraft.core.models import Cassette as CoreCassette
from evalcraft.golden.manager import GoldenSet as CoreGoldenSet

router = APIRouter(prefix="/cassettes", tags=["cassettes"])


async def _get_cassette(
    cassette_id: uuid.UUID, team_id: uuid.UUID, db: AsyncSession
) -> StoredCassette:
    result = await db.execute(
        select(StoredCassette)
        .join(Project, StoredCassette.project_id == Project.id)
        .where(StoredCassette.id == cassette_id, Project.team_id == team_id)
    )
    cassette = result.scalar_one_or_none()
    if cassette is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cassette not found")
    return cassette


@router.post("/upload", response_model=CassetteListItem, status_code=status.HTTP_201_CREATED)
async def upload_cassette(
    cassette_json: dict,
    request: Request,
    background_tasks: BackgroundTasks,
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

    # Invalidate analytics cache
    await cache_invalidate(f"trends:{project_id}:*")

    return stored


@router.get("", response_model=CassettePaginatedResponse)
async def list_cassettes(
    project_id: uuid.UUID = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    agent_name: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """List cassettes with pagination and optional filters."""
    # Verify project belongs to team
    proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.team_id == team_id)
    )
    if proj.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    base_stmt = select(StoredCassette).where(StoredCassette.project_id == project_id)

    if date_from:
        base_stmt = base_stmt.where(cast(StoredCassette.created_at, Date) >= date_from)
    if date_to:
        base_stmt = base_stmt.where(cast(StoredCassette.created_at, Date) <= date_to)
    if agent_name:
        base_stmt = base_stmt.where(StoredCassette.agent_name == agent_name)

    # Count
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    items_stmt = base_stmt.order_by(StoredCassette.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(items_stmt)

    return CassettePaginatedResponse(
        items=result.scalars().all(),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{cassette_id}", response_model=CassetteDetail)
async def get_cassette(
    cassette_id: uuid.UUID,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Get full cassette detail including spans."""
    return await _get_cassette(cassette_id, team_id, db)


@router.get("/{id_a}/diff/{id_b}", response_model=CassetteDiffResponse)
async def diff_cassettes(
    id_a: uuid.UUID,
    id_b: uuid.UUID,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Compare two cassettes field-by-field."""
    a = await _get_cassette(id_a, team_id, db)
    b = await _get_cassette(id_b, team_id, db)

    diff_fields = []
    for field in ["total_tokens", "total_cost_usd", "total_duration_ms", "llm_call_count", "tool_call_count", "agent_name", "framework"]:
        va = getattr(a, field)
        vb = getattr(b, field)
        diff_fields.append(CassetteDiffField(field=field, value_a=va, value_b=vb, changed=va != vb))

    for field in ["input_text", "output_text"]:
        va = getattr(a, field)
        vb = getattr(b, field)
        diff_fields.append(CassetteDiffField(
            field=field,
            value_a=va[:200] if va else None,
            value_b=vb[:200] if vb else None,
            changed=va != vb,
        ))

    return CassetteDiffResponse(cassette_a_id=id_a, cassette_b_id=id_b, fields=diff_fields)


@router.post("/{cassette_id}/compare", response_model=CompareResponse)
async def compare_cassette(
    cassette_id: uuid.UUID,
    body: CompareRequest,
    team_id: uuid.UUID = Depends(get_team_id),
    db: AsyncSession = Depends(get_db),
):
    """Compare a cassette against a golden set."""
    cassette = await _get_cassette(cassette_id, team_id, db)

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
