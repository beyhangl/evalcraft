"""Tests for regression endpoints."""

import pytest
from httpx import AsyncClient
from conftest import SAMPLE_CASSETTE


@pytest.mark.asyncio
async def test_list_regressions(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.get(
        f"/api/v1/regressions?project_id={test_project}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_list_regressions_with_severity_filter(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.get(
        f"/api/v1/regressions?project_id={test_project}&severity=CRITICAL",
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_regressions_with_resolved_filter(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.get(
        f"/api/v1/regressions?project_id={test_project}&resolved=false",
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_resolve_regression_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        "/api/v1/regressions/00000000-0000-0000-0000-000000000000/resolve",
        headers=auth_headers,
    )
    assert resp.status_code == 404
