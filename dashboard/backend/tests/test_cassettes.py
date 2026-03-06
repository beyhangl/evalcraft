"""Tests for cassette endpoints."""

import pytest
from httpx import AsyncClient
from conftest import SAMPLE_CASSETTE


@pytest.mark.asyncio
async def test_upload_cassette(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.post(
        f"/api/v1/cassettes/upload?project_id={test_project}",
        json=SAMPLE_CASSETTE,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-cassette"
    assert data["agent_name"] == "test-agent"


@pytest.mark.asyncio
async def test_list_cassettes(client: AsyncClient, auth_headers: dict, test_project: str):
    # Upload one first
    await client.post(
        f"/api/v1/cassettes/upload?project_id={test_project}",
        json=SAMPLE_CASSETTE,
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/v1/cassettes?project_id={test_project}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_cassettes_pagination(client: AsyncClient, auth_headers: dict, test_project: str):
    # Upload two
    for _ in range(2):
        await client.post(
            f"/api/v1/cassettes/upload?project_id={test_project}",
            json=SAMPLE_CASSETTE,
            headers=auth_headers,
        )

    resp = await client.get(
        f"/api/v1/cassettes?project_id={test_project}&page=1&page_size=1",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_get_cassette(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.post(
        f"/api/v1/cassettes/upload?project_id={test_project}",
        json=SAMPLE_CASSETTE,
        headers=auth_headers,
    )
    cid = resp.json()["id"]

    resp = await client.get(f"/api/v1/cassettes/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == cid


@pytest.mark.asyncio
async def test_get_cassette_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/cassettes/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_with_metadata(client: AsyncClient, auth_headers: dict, test_project: str):
    resp = await client.post(
        f"/api/v1/cassettes/upload?project_id={test_project}&git_sha=abc123&branch=main",
        json=SAMPLE_CASSETTE,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["git_sha"] == "abc123"
    assert data["branch"] == "main"


@pytest.mark.asyncio
async def test_diff_cassettes(client: AsyncClient, auth_headers: dict, test_project: str):
    # Upload two cassettes
    r1 = await client.post(
        f"/api/v1/cassettes/upload?project_id={test_project}",
        json=SAMPLE_CASSETTE,
        headers=auth_headers,
    )
    cassette_2 = dict(SAMPLE_CASSETTE)
    cassette_2["name"] = "test-cassette-2"
    r2 = await client.post(
        f"/api/v1/cassettes/upload?project_id={test_project}",
        json=cassette_2,
        headers=auth_headers,
    )

    id_a = r1.json()["id"]
    id_b = r2.json()["id"]

    resp = await client.get(
        f"/api/v1/cassettes/{id_a}/diff/{id_b}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cassette_a_id"] == id_a
    assert data["cassette_b_id"] == id_b
    assert len(data["fields"]) > 0
