#!/usr/bin/env python3
"""Evalcraft API smoke test.

Tests the full API flow end-to-end:
  signup → login → me → create project → upload cassettes → cassette detail
  → create golden set → get trends → create / list / revoke API keys

Usage:
    SMOKE_TEST_URL=http://localhost:8000 python scripts/smoke_test.py

Environment variables:
    SMOKE_TEST_URL  — backend base URL  (default: http://localhost:8000)
    FRONTEND_URL    — optional frontend URL to health-check

Exit codes:  0 = all passed,  1 = one or more failed.
"""

from __future__ import annotations

import os
import sys
import time
import uuid

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx")
    sys.exit(1)

# ── Config ──────────────────────────────────────────

BASE_URL = os.environ.get("SMOKE_TEST_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
API = f"{BASE_URL}/api/v1"
HEALTH_URL = f"{BASE_URL}/health"
STARTUP_WAIT = 30  # seconds to wait for backend

# ── Colours ─────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ── Result tracking ────────────────────────────────

passed: list[str] = []
failed: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    """Record and print a single check result."""
    if condition:
        passed.append(label)
        print(f"  {GREEN}\u2713{RESET} {label}")
    else:
        failed.append(label)
        msg = f"  {RED}\u2717{RESET} {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)


# ── Helpers ─────────────────────────────────────────


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _span(kind: str, name: str, **kw) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "name": name,
        "timestamp": time.time(),
        "duration_ms": kw.get("duration_ms", 50.0),
        "parent_id": kw.get("parent_id"),
        "input": kw.get("input"),
        "output": kw.get("output"),
        "error": None,
        "model": kw.get("model"),
        "token_usage": kw.get("token_usage"),
        "cost_usd": kw.get("cost_usd"),
        "tool_name": kw.get("tool_name"),
        "tool_args": kw.get("tool_args"),
        "tool_result": kw.get("tool_result"),
        "metadata": kw.get("metadata", {}),
    }


def _cassette(name: str) -> dict:
    """Build a valid cassette JSON payload with lowercase SpanKind values."""
    return {
        "evalcraft_version": "0.1.0",
        "cassette": {
            "id": str(uuid.uuid4()),
            "name": name,
            "version": "1.0",
            "created_at": time.time(),
            "agent_name": "SmokeAgent",
            "framework": "openai",
            "input_text": "hello",
            "output_text": "world",
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_duration_ms": 0.0,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "fingerprint": "",
            "metadata": {},
        },
        "spans": [
            _span("user_input", "query", input="hello"),
            _span(
                "llm_request", "gpt-4o", model="gpt-4o",
                token_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                cost_usd=0.001, duration_ms=200.0,
            ),
            _span("llm_response", "gpt-4o-resp", output="world", model="gpt-4o"),
            _span("tool_call", "calculator", tool_name="calculator",
                  tool_args={"expr": "1+1"}, tool_result="2", duration_ms=30.0),
            _span("agent_output", "answer", output="world"),
        ],
    }


# ── Test Flows ──────────────────────────────────────


def test_health():
    print(f"\n{BOLD}Health{RESET}")
    r = httpx.get(HEALTH_URL, timeout=5)
    check("GET /health returns 200", r.status_code == 200, f"got {r.status_code}")


def test_auth(client: httpx.Client) -> str | None:
    """Signup, login, /me. Returns bearer token or None."""
    print(f"\n{BOLD}Auth{RESET}")

    unique = uuid.uuid4().hex[:8]
    email = f"smoke-{unique}@evalcraft.dev"
    password = "smoketest123"

    # Signup
    r = client.post("/auth/signup", json={
        "email": email,
        "password": password,
        "full_name": "Smoke Tester",
        "team_name": f"smoke-team-{unique}",
    })
    check("POST /auth/signup returns 201", r.status_code == 201, f"got {r.status_code}")
    if r.status_code != 201:
        return None
    token = r.json().get("access_token")
    check("signup returns access_token", token is not None)

    # Login
    r = client.post("/auth/login", json={"email": email, "password": password})
    check("POST /auth/login returns 200", r.status_code == 200, f"got {r.status_code}")
    check("login returns access_token", r.json().get("access_token") is not None)

    # /me
    r = client.get("/auth/me", headers=auth_headers(token))
    check("GET /auth/me returns 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        check("/me.email matches", r.json().get("email") == email)

    return token


def test_projects(client: httpx.Client, token: str) -> str | None:
    """Create and list projects. Returns project_id."""
    print(f"\n{BOLD}Projects{RESET}")
    h = auth_headers(token)

    r = client.post("/projects", json={
        "name": "Smoke Project",
        "description": "Created by smoke test",
    }, headers=h)
    check("POST /projects returns 201", r.status_code == 201, f"got {r.status_code}")
    if r.status_code != 201:
        return None
    project_id = r.json()["id"]

    r = client.get("/projects", headers=h)
    check("GET /projects returns 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        names = [p["name"] for p in r.json()]
        check("project appears in list", "Smoke Project" in names)

    return project_id


def test_cassettes(client: httpx.Client, token: str, project_id: str) -> str | None:
    """Upload cassettes, list, get detail. Returns cassette_id."""
    print(f"\n{BOLD}Cassettes{RESET}")
    h = auth_headers(token)

    # Upload
    r = client.post(
        "/cassettes/upload",
        params={"project_id": project_id, "git_sha": "smoke123", "branch": "main"},
        json=_cassette("smoke-cassette-1"),
        headers=h,
    )
    check("POST /cassettes/upload returns 201", r.status_code == 201, f"got {r.status_code}")
    if r.status_code != 201:
        return None
    cassette_id = r.json()["id"]

    # Second upload
    r = client.post(
        "/cassettes/upload",
        params={"project_id": project_id, "git_sha": "smoke456", "branch": "main"},
        json=_cassette("smoke-cassette-2"),
        headers=h,
    )
    check("second cassette upload returns 201", r.status_code == 201, f"got {r.status_code}")

    # List
    r = client.get("/cassettes", params={"project_id": project_id}, headers=h)
    check("GET /cassettes returns 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        check("cassette list has >= 2 items", len(r.json()) >= 2, f"got {len(r.json())}")

    # Detail
    r = client.get(f"/cassettes/{cassette_id}", headers=h)
    check("GET /cassettes/:id returns 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        check("cassette detail has raw_data", "raw_data" in r.json())

    return cassette_id


def test_golden_sets(client: httpx.Client, token: str, project_id: str, cassette_id: str) -> str | None:
    """Create, list, get golden set. Returns golden_set_id."""
    print(f"\n{BOLD}Golden Sets{RESET}")
    h = auth_headers(token)

    r = client.post(
        "/golden-sets",
        params={"project_id": project_id},
        json={
            "name": "Smoke Baseline",
            "description": "Auto-created by smoke test",
            "cassette_ids": [cassette_id],
            "thresholds": {
                "tool_sequence_must_match": True,
                "output_must_match": False,
                "max_token_increase_ratio": 1.5,
                "max_cost_increase_ratio": 2.0,
                "max_latency_increase_ratio": 3.0,
            },
        },
        headers=h,
    )
    check("POST /golden-sets returns 201", r.status_code == 201, f"got {r.status_code}")
    if r.status_code != 201:
        return None
    gs_id = r.json()["id"]

    r = client.get("/golden-sets", params={"project_id": project_id}, headers=h)
    check("GET /golden-sets returns 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        check("golden set list has >= 1 item", len(r.json()) >= 1)

    r = client.get(f"/golden-sets/{gs_id}", headers=h)
    check("GET /golden-sets/:id returns 200", r.status_code == 200, f"got {r.status_code}")

    return gs_id


def test_trends(client: httpx.Client, token: str, project_id: str):
    """Fetch analytics trends."""
    print(f"\n{BOLD}Analytics{RESET}")
    h = auth_headers(token)

    r = client.get("/analytics/trends", params={"project_id": project_id, "days": 7}, headers=h)
    check("GET /analytics/trends returns 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        check("trends response has points", "points" in r.json())


def test_api_keys(client: httpx.Client, token: str):
    """Create, list, and revoke API keys."""
    print(f"\n{BOLD}API Keys{RESET}")
    h = auth_headers(token)

    # Create
    r = client.post("/auth/api-keys", json={"name": "smoke-key"}, headers=h)
    check("POST /auth/api-keys returns 201", r.status_code == 201, f"got {r.status_code}")
    key_id = None
    if r.status_code == 201:
        body = r.json()
        check("api key has full_key", "full_key" in body)
        check("api key has key_prefix", "key_prefix" in body)
        key_id = body["id"]

    # List
    r = client.get("/auth/api-keys", headers=h)
    check("GET /auth/api-keys returns 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        check("api key list has >= 1 item", len(r.json()) >= 1)

    # Revoke
    if key_id:
        r = client.delete(f"/auth/api-keys/{key_id}", headers=h)
        check("DELETE /auth/api-keys/:id returns 204", r.status_code == 204, f"got {r.status_code}")
    else:
        check("DELETE /auth/api-keys/:id returns 204", False, "skipped — no key_id")


def test_frontend():
    """Optional: check frontend is reachable."""
    if not FRONTEND_URL:
        return
    print(f"\n{BOLD}Frontend{RESET}")
    try:
        r = httpx.get(FRONTEND_URL.rstrip("/") + "/", timeout=10)
        check("Frontend reachable", r.status_code == 200, f"got {r.status_code}")
    except Exception as e:
        check("Frontend reachable", False, str(e))


# ── Main ────────────────────────────────────────────


def main() -> int:
    # Wait for backend
    print(f"Waiting for backend at {HEALTH_URL} ...", end="", flush=True)
    for _ in range(STARTUP_WAIT):
        try:
            r = httpx.get(HEALTH_URL, timeout=3)
            if r.status_code == 200:
                break
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(1)
        print(".", end="", flush=True)
    else:
        print(f"\n{RED}\u2717 Backend not reachable after {STARTUP_WAIT}s{RESET}")
        return 1
    print(" ready!")

    client = httpx.Client(base_url=API, timeout=15)

    print(f"\n{BOLD}{'=' * 48}")
    print("  Evalcraft Integration Smoke Test")
    print(f"  API: {API}")
    print(f"{'=' * 48}{RESET}")

    # Run test flows in dependency order
    test_health()

    token = test_auth(client)
    if not token:
        print(f"\n{RED}Auth failed — cannot continue.{RESET}")
        return 1

    project_id = test_projects(client, token)
    if not project_id:
        print(f"\n{RED}Project creation failed — cannot continue.{RESET}")
        return 1

    cassette_id = test_cassettes(client, token, project_id)
    if cassette_id:
        test_golden_sets(client, token, project_id, cassette_id)

    test_trends(client, token, project_id)
    test_api_keys(client, token)
    test_frontend()

    # Summary
    total = len(passed) + len(failed)
    print(f"\n{BOLD}{'=' * 48}")
    if failed:
        print(f"  {RED}Results: {len(passed)}/{total} passed, {len(failed)} failed{RESET}")
        for f in failed:
            print(f"    {RED}\u2717{RESET} {f}")
    else:
        print(f"  {GREEN}Results: {len(passed)}/{total} passed{RESET}")
    print(f"{BOLD}{'=' * 48}{RESET}\n")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
