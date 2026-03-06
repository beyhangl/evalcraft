"""Tests for auth endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup(client: AsyncClient):
    resp = await client.post("/api/v1/auth/signup", json={
        "email": "new@example.com",
        "password": "password123",
        "full_name": "New User",
        "team_name": "New Team",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    body = {
        "email": "dupe@example.com",
        "password": "password123",
        "full_name": "User",
        "team_name": "Team A",
    }
    resp1 = await client.post("/api/v1/auth/signup", json=body)
    assert resp1.status_code == 201

    body["team_name"] = "Team B"
    resp2 = await client.post("/api/v1/auth/signup", json=body)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json={
        "email": "login@example.com",
        "password": "password123",
        "full_name": "Login User",
        "team_name": "Login Team",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@example.com",
        "password": "password123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_bad_password(client: AsyncClient):
    await client.post("/api/v1/auth/signup", json={
        "email": "bad@example.com",
        "password": "password123",
        "full_name": "User",
        "team_name": "Team",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "bad@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "email" in data
    assert "team_id" in data


@pytest.mark.asyncio
async def test_me_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/auth/refresh", headers=auth_headers)
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_api_key_lifecycle(client: AsyncClient, auth_headers: dict):
    # Create
    resp = await client.post("/api/v1/auth/api-keys", json={"name": "test-key"}, headers=auth_headers)
    assert resp.status_code == 201
    key_data = resp.json()
    assert "full_key" in key_data
    key_id = key_data["id"]

    # List
    resp = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # Revoke
    resp = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_forgot_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": "anyone@example.com"})
    assert resp.status_code == 200
    assert "message" in resp.json()
