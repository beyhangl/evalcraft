"""Pydantic request/response schemas for the API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    team_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    team_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── API Keys ──────────────────────────────────

class APIKeyCreateRequest(BaseModel):
    name: str = "default"


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    key_prefix: str
    name: str
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class APIKeyCreatedResponse(APIKeyResponse):
    """Returned only on creation — includes the full key (shown once)."""
    full_key: str


# ── Projects ──────────────────────────────────

class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    team_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Cassettes ─────────────────────────────────

class CassetteUploadMeta(BaseModel):
    """Optional metadata sent alongside cassette JSON upload."""
    git_sha: str = ""
    branch: str = ""
    ci_run_url: str = ""


class CassetteListItem(BaseModel):
    id: uuid.UUID
    name: str
    agent_name: str
    framework: str
    fingerprint: str
    total_tokens: int
    total_cost_usd: float
    total_duration_ms: float
    llm_call_count: int
    tool_call_count: int
    git_sha: str
    branch: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CassetteDetail(CassetteListItem):
    input_text: str
    output_text: str
    raw_data: dict
    ci_run_url: str


class CompareRequest(BaseModel):
    golden_set_id: uuid.UUID


class CompareFieldResult(BaseModel):
    name: str
    passed: bool
    golden_value: object = None
    candidate_value: object = None
    message: str = ""


class CompareResponse(BaseModel):
    passed: bool
    golden_name: str
    golden_version: int
    fields: list[CompareFieldResult]


# ── Golden Sets ───────────────────────────────

class ThresholdsSchema(BaseModel):
    tool_sequence_must_match: bool = True
    output_must_match: bool = False
    max_token_increase_ratio: float | None = 1.5
    max_cost_increase_ratio: float | None = 2.0
    max_latency_increase_ratio: float | None = 3.0
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None


class GoldenSetCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    cassette_ids: list[uuid.UUID] = Field(default_factory=list)
    thresholds: ThresholdsSchema = Field(default_factory=ThresholdsSchema)


class GoldenSetUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    thresholds: ThresholdsSchema | None = None


class GoldenSetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    version: int
    thresholds: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoldenSetDetailResponse(GoldenSetResponse):
    raw_data: dict


# ── Regressions ───────────────────────────────

class RegressionEventResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    cassette_id: uuid.UUID
    golden_set_id: uuid.UUID | None
    severity: str
    category: str
    message: str
    details: dict
    resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Analytics ─────────────────────────────────

class TrendPoint(BaseModel):
    date: str
    total_tokens: int
    total_cost_usd: float
    total_duration_ms: float
    cassette_count: int


class TrendsResponse(BaseModel):
    project_id: uuid.UUID
    points: list[TrendPoint]


# ── Webhooks ──────────────────────────────────

class WebhookResponse(BaseModel):
    status: str
    cassette_ids: list[uuid.UUID] = Field(default_factory=list)
    regressions_found: int = 0


# ── Generic ───────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
