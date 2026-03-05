"""CI/CD webhook receiver (e.g., GitHub Actions)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_team_from_api_key
from app.database import get_db
from app.models.project import Project
from app.models.user import Team
from app.schemas.api import WebhookResponse
from app.services.cassette_service import process_upload
from app.services.regression_service import check_regressions

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", response_model=WebhookResponse)
async def github_webhook(
    payload: dict[str, Any],
    team: Team = Depends(get_team_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Receive cassette uploads from GitHub Actions.

    Expected payload:
    {
        "project_slug": "my-agent",
        "git_sha": "abc123",
        "branch": "main",
        "ci_run_url": "https://github.com/...",
        "cassettes": [ { ... cassette JSON ... } ]
    }
    """
    project_slug = payload.get("project_slug", "")
    if not project_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_slug required")

    result = await db.execute(
        select(Project).where(Project.slug == project_slug, Project.team_id == team.id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    cassettes_data = payload.get("cassettes", [])
    if not cassettes_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No cassettes in payload")

    git_sha = payload.get("git_sha", "")
    branch = payload.get("branch", "")
    ci_run_url = payload.get("ci_run_url", "")

    stored_ids: list[uuid.UUID] = []
    total_regressions = 0

    for cassette_json in cassettes_data:
        stored = await process_upload(
            raw_data=cassette_json,
            project_id=project.id,
            git_sha=git_sha,
            branch=branch,
            ci_run_url=ci_run_url,
            db=db,
        )
        stored_ids.append(stored.id)

        events = await check_regressions(cassette_json, project.id, stored.id, db)
        total_regressions += len(events)

    return WebhookResponse(
        status="ok",
        cassette_ids=stored_ids,
        regressions_found=total_regressions,
    )
