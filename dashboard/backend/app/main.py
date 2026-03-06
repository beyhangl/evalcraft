"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from app.api import auth, cassettes, golden_sets, projects, regressions, webhooks
from app.api.auth import get_team_id
from app.config import get_settings
from app.database import get_db
from app.logging_config import request_id_var, setup_logging
from app.services.analytics_service import compute_trends

setup_logging()
logger = logging.getLogger("evalcraft")
settings = get_settings()

MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=["200/minute"],
)


class LimitUploadSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large. Maximum size is 10MB."},
            )
        return await call_next(request)


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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(LimitUploadSizeMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    logger.error("Unhandled error request_id=%s: %s", request_id, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request_id},
    )


# Request timing middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    rid = str(uuid.uuid4())[:8]
    request_id_var.set(rid)
    start = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration,
    )
    response.headers["X-Request-ID"] = rid
    return response


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
    checks = {}

    # DB check
    try:
        from app.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis check
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )


@app.get(f"{prefix}/analytics/trends")
async def get_trends(
    project_id: uuid.UUID = Query(...),
    days: int = Query(30, ge=1, le=365),
    team_id: uuid.UUID = Depends(get_team_id),
    db=Depends(get_db),
):
    """Token, cost, and latency trends over time."""
    return await compute_trends(project_id, team_id, db, days=days)
