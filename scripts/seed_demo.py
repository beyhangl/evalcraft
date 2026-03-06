#!/usr/bin/env python3
"""Seed the Evalcraft demo with sample data via the HTTP API."""

import sys
import time
import uuid

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx")
    sys.exit(1)

BASE = "http://localhost:8000/api/v1"

# ── Helpers ──────────────────────────────────────


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _span(kind: str, name: str, **kwargs) -> dict:
    span = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "name": name,
        "timestamp": time.time(),
        "duration_ms": kwargs.pop("duration_ms", 50.0),
        "parent_id": kwargs.pop("parent_id", None),
        "input": kwargs.pop("input", None),
        "output": kwargs.pop("output", None),
        "error": None,
        "model": kwargs.pop("model", None),
        "token_usage": kwargs.pop("token_usage", None),
        "cost_usd": kwargs.pop("cost_usd", None),
        "tool_name": kwargs.pop("tool_name", None),
        "tool_args": kwargs.pop("tool_args", None),
        "tool_result": kwargs.pop("tool_result", None),
        "metadata": kwargs.pop("metadata", {}),
    }
    return span


def _cassette(name: str, agent_name: str, input_text: str, output_text: str, spans: list) -> dict:
    return {
        "evalcraft_version": "0.1.0",
        "cassette": {
            "id": str(uuid.uuid4()),
            "name": name,
            "version": "1.0",
            "created_at": time.time(),
            "agent_name": agent_name,
            "framework": "openai",
            "input_text": input_text,
            "output_text": output_text,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_duration_ms": 0.0,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "fingerprint": "",
            "metadata": {},
        },
        "spans": spans,
    }


# ── Sample cassettes ────────────────────────────


def cassette_weather_lookup() -> dict:
    """Weather Agent: user asks for weather, agent calls tool, returns answer."""
    root_id = str(uuid.uuid4())
    return _cassette(
        name="weather-lookup-sf",
        agent_name="WeatherAgent",
        input_text="What's the weather in San Francisco?",
        output_text="It's currently 62°F and partly cloudy in San Francisco.",
        spans=[
            _span("user_input", "user-query",
                  input="What's the weather in San Francisco?",
                  parent_id=None),
            _span("agent_step", "plan",
                  input="Determine user intent",
                  output="User wants current weather for San Francisco",
                  parent_id=root_id,
                  duration_ms=12.0),
            _span("llm_request", "gpt-4o-plan",
                  input="What's the weather in San Francisco?",
                  model="gpt-4o",
                  token_usage={"prompt_tokens": 85, "completion_tokens": 32, "total_tokens": 117},
                  cost_usd=0.0012,
                  duration_ms=430.0),
            _span("llm_response", "gpt-4o-plan-response",
                  output='{"tool": "get_weather", "args": {"city": "San Francisco"}}',
                  model="gpt-4o",
                  duration_ms=5.0),
            _span("tool_call", "get_weather",
                  tool_name="get_weather",
                  tool_args={"city": "San Francisco"},
                  duration_ms=210.0),
            _span("tool_result", "get_weather-result",
                  tool_name="get_weather",
                  tool_result={"temp_f": 62, "condition": "Partly Cloudy", "humidity": 72},
                  duration_ms=2.0),
            _span("llm_request", "gpt-4o-answer",
                  input="Weather data: 62°F, Partly Cloudy, 72% humidity",
                  model="gpt-4o",
                  token_usage={"prompt_tokens": 140, "completion_tokens": 28, "total_tokens": 168},
                  cost_usd=0.0015,
                  duration_ms=380.0),
            _span("llm_response", "gpt-4o-answer-response",
                  output="It's currently 62°F and partly cloudy in San Francisco.",
                  model="gpt-4o",
                  duration_ms=5.0),
            _span("agent_output", "final-answer",
                  output="It's currently 62°F and partly cloudy in San Francisco.",
                  duration_ms=1.0),
        ],
    )


def cassette_weather_forecast() -> dict:
    """Weather Agent: user asks for a 3-day forecast."""
    return _cassette(
        name="weather-forecast-nyc",
        agent_name="WeatherAgent",
        input_text="Give me a 3-day forecast for New York City",
        output_text="NYC 3-day forecast: Mon 58°F rain, Tue 63°F cloudy, Wed 67°F sunny.",
        spans=[
            _span("user_input", "user-query",
                  input="Give me a 3-day forecast for New York City"),
            _span("agent_step", "plan",
                  input="Parse forecast request",
                  output="User wants 3-day forecast for NYC",
                  duration_ms=10.0),
            _span("llm_request", "gpt-4o-plan",
                  input="Give me a 3-day forecast for New York City",
                  model="gpt-4o",
                  token_usage={"prompt_tokens": 92, "completion_tokens": 45, "total_tokens": 137},
                  cost_usd=0.0014,
                  duration_ms=520.0),
            _span("llm_response", "gpt-4o-plan-response",
                  output='{"tool": "get_forecast", "args": {"city": "New York City", "days": 3}}',
                  model="gpt-4o",
                  duration_ms=5.0),
            _span("tool_call", "get_forecast",
                  tool_name="get_forecast",
                  tool_args={"city": "New York City", "days": 3},
                  duration_ms=350.0),
            _span("tool_result", "get_forecast-result",
                  tool_name="get_forecast",
                  tool_result=[
                      {"day": "Mon", "temp_f": 58, "condition": "Rain"},
                      {"day": "Tue", "temp_f": 63, "condition": "Cloudy"},
                      {"day": "Wed", "temp_f": 67, "condition": "Sunny"},
                  ],
                  duration_ms=2.0),
            _span("llm_request", "gpt-4o-answer",
                  input="Forecast data for NYC",
                  model="gpt-4o",
                  token_usage={"prompt_tokens": 165, "completion_tokens": 40, "total_tokens": 205},
                  cost_usd=0.0019,
                  duration_ms=410.0),
            _span("llm_response", "gpt-4o-answer-response",
                  output="NYC 3-day forecast: Mon 58°F rain, Tue 63°F cloudy, Wed 67°F sunny.",
                  model="gpt-4o",
                  duration_ms=5.0),
            _span("agent_output", "final-answer",
                  output="NYC 3-day forecast: Mon 58°F rain, Tue 63°F cloudy, Wed 67°F sunny.",
                  duration_ms=1.0),
        ],
    )


def cassette_weather_regression() -> dict:
    """A cassette with higher token usage to trigger regression detection."""
    return _cassette(
        name="weather-lookup-sf-v2",
        agent_name="WeatherAgent",
        input_text="What's the weather in San Francisco?",
        output_text="The current weather in San Francisco, California is 62°F with partly cloudy skies and 72% humidity. Expect mild conditions throughout the day.",
        spans=[
            _span("user_input", "user-query",
                  input="What's the weather in San Francisco?"),
            _span("agent_step", "plan",
                  input="Determine user intent",
                  output="User wants current weather for San Francisco",
                  duration_ms=15.0),
            _span("llm_request", "gpt-4o-plan",
                  input="What's the weather in San Francisco?",
                  model="gpt-4o",
                  token_usage={"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
                  cost_usd=0.0035,
                  duration_ms=650.0),
            _span("llm_response", "gpt-4o-plan-response",
                  output='{"tool": "get_weather", "args": {"city": "San Francisco"}}',
                  model="gpt-4o",
                  duration_ms=5.0),
            _span("tool_call", "get_weather",
                  tool_name="get_weather",
                  tool_args={"city": "San Francisco"},
                  duration_ms=310.0),
            _span("tool_result", "get_weather-result",
                  tool_name="get_weather",
                  tool_result={"temp_f": 62, "condition": "Partly Cloudy", "humidity": 72},
                  duration_ms=2.0),
            _span("llm_request", "gpt-4o-elaborate",
                  input="Weather data — elaborate on conditions",
                  model="gpt-4o",
                  token_usage={"prompt_tokens": 180, "completion_tokens": 95, "total_tokens": 275},
                  cost_usd=0.0032,
                  duration_ms=580.0),
            _span("llm_response", "gpt-4o-elaborate-response",
                  output="Detailed weather analysis for San Francisco...",
                  model="gpt-4o",
                  duration_ms=5.0),
            _span("llm_request", "gpt-4o-final",
                  input="Summarize for user",
                  model="gpt-4o",
                  token_usage={"prompt_tokens": 250, "completion_tokens": 60, "total_tokens": 310},
                  cost_usd=0.0038,
                  duration_ms=450.0),
            _span("llm_response", "gpt-4o-final-response",
                  output="The current weather in San Francisco, California is 62°F...",
                  model="gpt-4o",
                  duration_ms=5.0),
            _span("agent_output", "final-answer",
                  output="The current weather in San Francisco, California is 62°F with partly cloudy skies and 72% humidity. Expect mild conditions throughout the day.",
                  duration_ms=1.0),
        ],
    )


# ── Main seed flow ───────────────────────────────


def main():
    client = httpx.Client(base_url=BASE, timeout=30)

    # 1. Wait for backend
    print("Waiting for backend...", end="", flush=True)
    for _ in range(30):
        try:
            r = httpx.get("http://localhost:8000/health", timeout=5)
            if r.status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(1)
        print(".", end="", flush=True)
    else:
        print("\nBackend not reachable after 30s. Is it running?")
        sys.exit(1)
    print(" ready!")

    # 2. Sign up demo user
    print("Creating demo user...", end=" ")
    r = client.post("/auth/signup", json={
        "email": "demo@evalcraft.dev",
        "password": "demodemo123",
        "full_name": "Demo User",
        "team_name": "Demo Team",
    })
    if r.status_code == 409:
        print("already exists, logging in.")
        r = client.post("/auth/login", json={
            "email": "demo@evalcraft.dev",
            "password": "demodemo123",
        })
        r.raise_for_status()
    elif r.status_code == 201:
        print("done.")
    else:
        print(f"failed: {r.status_code} {r.text}")
        sys.exit(1)

    token = r.json()["access_token"]
    auth = _headers(token)

    # 3. Create project
    print("Creating project 'Weather Agent'...", end=" ")
    r = client.post("/projects", json={
        "name": "Weather Agent",
        "description": "Demo weather agent that fetches forecasts and current conditions.",
    }, headers=auth)
    if r.status_code == 201:
        project_id = r.json()["id"]
        print(f"done (id={project_id[:8]}...).")
    else:
        # Project may already exist; list and find it
        r2 = client.get("/projects", headers=auth)
        r2.raise_for_status()
        projects = r2.json()
        existing = [p for p in projects if p["name"] == "Weather Agent"]
        if existing:
            project_id = existing[0]["id"]
            print(f"already exists (id={project_id[:8]}...).")
        else:
            print(f"failed: {r.status_code} {r.text}")
            sys.exit(1)

    # 4. Upload cassettes
    cassettes_data = [
        ("weather-lookup-sf", cassette_weather_lookup()),
        ("weather-forecast-nyc", cassette_weather_forecast()),
    ]
    cassette_ids = []

    for name, cdata in cassettes_data:
        print(f"Uploading cassette '{name}'...", end=" ")
        r = client.post(
            "/cassettes/upload",
            params={"project_id": project_id, "git_sha": "abc1234", "branch": "main"},
            json=cdata,
            headers=auth,
        )
        if r.status_code == 201:
            cid = r.json()["id"]
            cassette_ids.append(cid)
            print(f"done (id={cid[:8]}...).")
        else:
            print(f"failed: {r.status_code} {r.text}")

    # 5. Create golden set from first cassette
    if cassette_ids:
        print("Creating golden set 'Baseline v1'...", end=" ")
        r = client.post(
            "/golden-sets",
            params={"project_id": project_id},
            json={
                "name": "Baseline v1",
                "description": "Golden set from the initial weather lookup cassette.",
                "cassette_ids": [cassette_ids[0]],
                "thresholds": {
                    "tool_sequence_must_match": True,
                    "output_must_match": False,
                    "max_token_increase_ratio": 1.5,
                    "max_cost_increase_ratio": 2.0,
                    "max_latency_increase_ratio": 3.0,
                },
            },
            headers=auth,
        )
        if r.status_code == 201:
            gs_id = r.json()["id"]
            print(f"done (id={gs_id[:8]}...).")
        else:
            print(f"failed: {r.status_code} {r.text}")

    # 6. Upload regression cassette (auto-detects regressions against golden set)
    print("Uploading regression cassette 'weather-lookup-sf-v2'...", end=" ")
    r = client.post(
        "/cassettes/upload",
        params={"project_id": project_id, "git_sha": "def5678", "branch": "feature/verbose"},
        json=cassette_weather_regression(),
        headers=auth,
    )
    if r.status_code == 201:
        cid = r.json()["id"]
        print(f"done (id={cid[:8]}...).")
    else:
        print(f"failed: {r.status_code} {r.text}")

    # 7. Upload another regression cassette
    print("Uploading second regression cassette...", end=" ")
    regression2 = cassette_weather_regression()
    regression2["cassette"]["name"] = "weather-lookup-sf-v3"
    regression2["cassette"]["id"] = str(uuid.uuid4())
    r = client.post(
        "/cassettes/upload",
        params={"project_id": project_id, "git_sha": "ghi9012", "branch": "feature/verbose"},
        json=regression2,
        headers=auth,
    )
    if r.status_code == 201:
        cid = r.json()["id"]
        print(f"done (id={cid[:8]}...).")
    else:
        print(f"failed: {r.status_code} {r.text}")

    print()
    print("Seed complete!")
    print(f"  Login:    demo@evalcraft.dev / demodemo123")
    print(f"  Frontend: http://localhost:3000")
    print(f"  Backend:  http://localhost:8000")
    print(f"  API docs: http://localhost:8000/docs")


if __name__ == "__main__":
    main()
