"""Tests for webhook endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_github_webhook_no_api_key(client: AsyncClient):
    resp = await client.post("/api/v1/webhooks/github", json={"project_slug": "test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_github_webhook_missing_slug(client: AsyncClient, auth_headers: dict):
    # Create an API key
    key_resp = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "webhook-key"},
        headers=auth_headers,
    )
    api_key = key_resp.json()["full_key"]

    resp = await client.post(
        "/api/v1/webhooks/github",
        json={"project_slug": ""},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 400
