"""FastAPI application entrypoint."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, cassettes, golden_sets, projects, regressions, webhooks
from app.api.auth import get_team_id
from app.config import get_settings
from app.database import get_db
from app.services.analytics_service import compute_trends

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    from app.database import engine

    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
prefix = settings.api_v1_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(projects.router, prefix=prefix)
app.include_router(cassettes.router, prefix=prefix)
app.include_router(golden_sets.router, prefix=prefix)
app.include_router(regressions.router, prefix=prefix)
app.include_router(webhooks.router, prefix=prefix)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get(f"{prefix}/analytics/trends")
async def get_trends(
    project_id: uuid.UUID = Query(...),
    days: int = Query(30, ge=1, le=365),
    team_id: uuid.UUID = Depends(get_team_id),
    db=Depends(get_db),
):
    """Token, cost, and latency trends over time."""
    return await compute_trends(project_id, team_id, db, days=days)
