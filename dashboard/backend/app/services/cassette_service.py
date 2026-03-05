"""Cassette upload processing and storage."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from evalcraft.core.models import Cassette as CoreCassette
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from evalcraft.core.models import Cassette as CoreCassette

from app.models.cassette import StoredCassette


async def process_upload(
    raw_data: dict,
    project_id: uuid.UUID,
    git_sha: str = "",
    branch: str = "",
    ci_run_url: str = "",
    db: AsyncSession | None = None,
) -> StoredCassette:
    """Parse raw cassette JSON into a StoredCassette record.

    Uses the core Cassette model to validate and compute metrics,
    then stores a flattened row for efficient querying.
    """
    core = CoreCassette.from_dict(raw_data)
    core.compute_metrics()
    core.compute_fingerprint()

    stored = StoredCassette(
        project_id=project_id,
        name=core.name,
        agent_name=core.agent_name,
        framework=core.framework,
        fingerprint=core.fingerprint,
        total_tokens=core.total_tokens,
        total_cost_usd=core.total_cost_usd,
        total_duration_ms=core.total_duration_ms,
        llm_call_count=core.llm_call_count,
        tool_call_count=core.tool_call_count,
        input_text=core.input_text,
        output_text=core.output_text,
        raw_data=raw_data,
        git_sha=git_sha,
        branch=branch,
        ci_run_url=ci_run_url,
    )

    if db is not None:
        db.add(stored)
        await db.flush()
        await db.refresh(stored)

    return stored


async def get_cassette_by_id(
    cassette_id: uuid.UUID,
    team_id: uuid.UUID,
    db: AsyncSession,
) -> StoredCassette | None:
    """Fetch a single cassette scoped to the team's projects."""
    from app.models.project import Project

    result = await db.execute(
        select(StoredCassette)
        .join(Project, StoredCassette.project_id == Project.id)
        .where(StoredCassette.id == cassette_id, Project.team_id == team_id)
    )
    return result.scalar_one_or_none()
