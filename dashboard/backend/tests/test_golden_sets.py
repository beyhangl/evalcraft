"""Tests for golden set endpoints."""

import pytest
from httpx import AsyncClient
from conftest import SAMPLE_CASSETTE


@pytest.mark.asyncio
async def test_create_golden_set(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.post(
        f"/api/v1/golden-sets?project_id={test_project}",
        json={"name": "Test Golden", "description": "A test golden set"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Golden"
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_create_golden_set_with_cassettes(client: AsyncClient, auth_headers: dict, test_project: str):
    # Upload a cassette first
    r = await client.post(
        f"/api/v1/cassettes/upload?project_id={test_project}",
        json=SAMPLE_CASSETTE,
        headers=auth_headers,
    )
    cid = r.json()["id"]

    resp = await client.post(
        f"/api/v1/golden-sets?project_id={test_project}",
        json={"name": "Seeded Golden", "cassette_ids": [cid]},
        headers=auth_headers,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_list_golden_sets(client: AsyncClient, auth_headers: dict, test_project: str):
    await client.post(
        f"/api/v1/golden-sets?project_id={test_project}",
        json={"name": "Listed Golden"},
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/v1/golden-sets?project_id={test_project}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_golden_set(client: AsyncClient, auth_headers: dict, test_project: str):
    r = await client.post(
        f"/api/v1/golden-sets?project_id={test_project}",
        json={"name": "Get Golden"},
        headers=auth_headers,
    )
    gs_id = r.json()["id"]

    resp = await client.get(f"/api/v1/golden-sets/{gs_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert "raw_data" in resp.json()


@pytest.mark.asyncio
async def test_update_golden_set(client: AsyncClient, auth_headers: dict, test_project: str):
    r = await client.post(
        f"/api/v1/golden-sets?project_id={test_project}",
        json={"name": "Update Golden"},
        headers=auth_headers,
    )
    gs_id = r.json()["id"]

    resp = await client.patch(
        f"/api/v1/golden-sets/{gs_id}",
        json={"name": "Updated Golden"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Golden"
    assert resp.json()["version"] == 2


@pytest.mark.asyncio
async def test_delete_golden_set(client: AsyncClient, auth_headers: dict, test_project: str):
    r = await client.post(
        f"/api/v1/golden-sets?project_id={test_project}",
        json={"name": "Delete Golden"},
        headers=auth_headers,
    )
    gs_id = r.json()["id"]

    resp = await client.delete(f"/api/v1/golden-sets/{gs_id}", headers=auth_headers)
    assert resp.status_code == 204
