"""Tests for project endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "My Project", "description": "A test project"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["slug"] == "my-project"


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.get("/api/v1/projects", headers=auth_headers)
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) >= 1


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.get(f"/api/v1/projects/{test_project}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == test_project


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.patch(
        f"/api/v1/projects/{test_project}",
        json={"name": "Updated Project"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Project"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "To Delete"},
        headers=auth_headers,
    )
    pid = resp.json()["id"]

    resp = await client.delete(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_project_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404
