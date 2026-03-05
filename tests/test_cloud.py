"""Tests for evalcraft.cloud — cloud upload client."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import urllib.error

import pytest

from evalcraft.cloud.client import EvalcraftCloud, CloudUploadError, OfflineQueueItem
from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage
from evalcraft.golden.manager import GoldenSet


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def cassette():
    c = Cassette(name="test_run", agent_name="weather_agent", framework="test")
    c.add_span(Span(
        kind=SpanKind.TOOL_CALL,
        name="tool:get_weather",
        tool_name="get_weather",
        tool_args={"city": "NYC"},
        tool_result={"temp": 72},
        duration_ms=100.0,
    ))
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4",
        model="gpt-4",
        output="It is 72F in NYC.",
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        cost_usd=0.001,
        duration_ms=200.0,
    ))
    c.compute_metrics()
    c.compute_fingerprint()
    return c


@pytest.fixture
def golden_set(cassette):
    gs = GoldenSet(name="weather_golden", description="test golden")
    gs.add_cassette(cassette)
    return gs


@pytest.fixture
def client(tmp_path):
    return EvalcraftCloud(
        api_key="ec_test_key",
        base_url="https://api.evalcraft.dev/v1",
        timeout=5,
        max_retries=2,
        queue_dir=tmp_path / "queue",
    )


def _make_mock_response(data: dict | list, status: int = 200):
    """Return a mock urllib response context manager."""
    raw = json.dumps(data).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ──────────────────────────────────────────────
# EvalcraftCloud construction
# ──────────────────────────────────────────────

def test_api_key_from_constructor(tmp_path):
    c = EvalcraftCloud(api_key="ec_direct", queue_dir=tmp_path / "queue")
    assert c.api_key == "ec_direct"


def test_api_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALCRAFT_API_KEY", "ec_from_env")
    # No api_key in constructor — should pick up from env
    c = EvalcraftCloud(queue_dir=tmp_path / "queue")
    assert c.api_key == "ec_from_env"


def test_api_key_from_config(tmp_path, monkeypatch):
    monkeypatch.delenv("EVALCRAFT_API_KEY", raising=False)
    config_dir = tmp_path / ".evalcraft"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"api_key": "ec_from_config"}))

    with patch("evalcraft.cloud.client._CONFIG_FILE", config_file):
        c = EvalcraftCloud(queue_dir=tmp_path / "queue")
        assert c.api_key == "ec_from_config"


# ──────────────────────────────────────────────
# upload()
# ──────────────────────────────────────────────

def test_upload_cassette_success(client, cassette):
    server_resp = {"id": "cas_abc123", "url": "https://app.evalcraft.dev/cassettes/cas_abc123"}
    mock_resp = _make_mock_response(server_resp)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = client.upload(cassette)

    assert result["id"] == "cas_abc123"
    assert result["url"].endswith("cas_abc123")

    # Verify correct URL and method
    req = mock_open.call_args[0][0]
    assert req.full_url == "https://api.evalcraft.dev/v1/cassettes"
    assert req.method == "POST"
    assert req.headers.get("Authorization") == "Bearer ec_test_key"
    assert req.headers.get("Content-type") == "application/json"

    # Payload should be valid cassette JSON
    payload = json.loads(req.data.decode("utf-8"))
    assert "cassette" in payload
    assert payload["cassette"]["name"] == "test_run"


def test_upload_cassette_queued_on_failure(client, cassette, tmp_path):
    err = urllib.error.URLError("connection refused")
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(CloudUploadError):
            client.upload(cassette)

    # Item should be in queue
    assert client.queue_size() == 1
    queue_files = list(client.queue_dir.glob("*.json"))
    item = OfflineQueueItem.from_dict(json.loads(queue_files[0].read_text()))
    assert item.path == "/cassettes"
    assert item.method == "POST"


# ──────────────────────────────────────────────
# upload_golden()
# ──────────────────────────────────────────────

def test_upload_golden_success(client, golden_set):
    server_resp = {"id": "gs_xyz", "url": "https://app.evalcraft.dev/golden/gs_xyz"}
    mock_resp = _make_mock_response(server_resp)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = client.upload_golden(golden_set)

    assert result["id"] == "gs_xyz"
    req = mock_open.call_args[0][0]
    assert req.full_url == "https://api.evalcraft.dev/v1/golden-sets"
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["name"] == "weather_golden"


def test_upload_golden_queued_on_failure(client, golden_set):
    err = urllib.error.URLError("timeout")
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(CloudUploadError):
            client.upload_golden(golden_set)

    assert client.queue_size() == 1
    queue_files = list(client.queue_dir.glob("*.json"))
    item = OfflineQueueItem.from_dict(json.loads(queue_files[0].read_text()))
    assert item.path == "/golden-sets"


# ──────────────────────────────────────────────
# list_cassettes() / get_regressions()
# ──────────────────────────────────────────────

def test_list_cassettes(client):
    server_resp = [{"id": "cas_1", "name": "run1"}, {"id": "cas_2", "name": "run2"}]
    mock_resp = _make_mock_response(server_resp)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = client.list_cassettes("my-project")

    assert len(result) == 2
    req = mock_open.call_args[0][0]
    assert "project=my-project" in req.full_url
    assert req.method == "GET"


def test_get_regressions(client):
    server_resp = [{"id": "reg_1", "severity": "CRITICAL"}]
    mock_resp = _make_mock_response(server_resp)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = client.get_regressions("my-project")

    assert result[0]["severity"] == "CRITICAL"
    req = mock_open.call_args[0][0]
    assert "/regressions" in req.full_url
    assert "project=my-project" in req.full_url


# ──────────────────────────────────────────────
# Retry with exponential backoff
# ──────────────────────────────────────────────

def test_retry_on_5xx_then_success(client, cassette):
    """Should retry on 5xx and succeed on the next attempt."""
    server_err = urllib.error.HTTPError(
        url="https://api.evalcraft.dev/v1/cassettes",
        code=503,
        msg="Service Unavailable",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=None,
    )
    server_ok = _make_mock_response({"id": "cas_retry_ok"})

    with patch("urllib.request.urlopen", side_effect=[server_err, server_ok]):
        with patch("time.sleep"):  # skip actual sleeping
            result = client.upload(cassette)

    assert result["id"] == "cas_retry_ok"


def test_no_retry_on_4xx(client, cassette):
    """4xx errors should not be retried."""
    err = urllib.error.HTTPError(
        url="https://api.evalcraft.dev/v1/cassettes",
        code=401,
        msg="Unauthorized",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=MagicMock(read=lambda: b"Unauthorized"),
    )
    with patch("urllib.request.urlopen", side_effect=err) as mock_open:
        with pytest.raises(CloudUploadError) as exc_info:
            client.upload(cassette)

    assert exc_info.value.status_code == 401
    # urlopen should only be called once (no retry)
    assert mock_open.call_count == 1


def test_exhausted_retries_enqueues(client, cassette):
    """After max_retries, item should be queued and CloudUploadError raised."""
    err = urllib.error.URLError("no route to host")
    with patch("urllib.request.urlopen", side_effect=err):
        with patch("time.sleep"):
            with pytest.raises(CloudUploadError):
                client.upload(cassette)

    # max_retries=2 → 3 total attempts, then queue
    assert client.queue_size() == 1


# ──────────────────────────────────────────────
# Offline queue
# ──────────────────────────────────────────────

def test_flush_queue_success(client, cassette):
    """flush_queue() should upload queued items and remove them."""
    # First upload fails → queued
    net_err = urllib.error.URLError("offline")
    with patch("urllib.request.urlopen", side_effect=net_err):
        with patch("time.sleep"):
            with pytest.raises(CloudUploadError):
                client.upload(cassette)

    assert client.queue_size() == 1

    # Network back — flush succeeds
    server_ok = _make_mock_response({"id": "cas_flushed"})
    with patch("urllib.request.urlopen", return_value=server_ok):
        succeeded, failed = client.flush_queue()

    assert succeeded == 1
    assert failed == 0
    assert client.queue_size() == 0


def test_flush_queue_partial_failure(client, cassette, golden_set):
    """flush_queue() returns correct counts when some items still fail."""
    net_err = urllib.error.URLError("offline")
    with patch("urllib.request.urlopen", side_effect=net_err):
        with patch("time.sleep"):
            with pytest.raises(CloudUploadError):
                client.upload(cassette)
            with pytest.raises(CloudUploadError):
                client.upload_golden(golden_set)

    assert client.queue_size() == 2

    server_ok = _make_mock_response({"id": "ok"})
    # First flush call succeeds; second item retries max_retries=2 times (3 total calls failing)
    with patch("urllib.request.urlopen", side_effect=[server_ok, net_err, net_err, net_err]):
        with patch("time.sleep"):
            succeeded, failed = client.flush_queue()

    assert succeeded == 1
    assert failed == 1
    assert client.queue_size() == 1


def test_queue_size_zero_when_empty(client):
    assert client.queue_size() == 0


def test_offline_queue_item_round_trip():
    item = OfflineQueueItem(
        method="POST",
        path="/cassettes",
        payload={"evalcraft_version": "0.1.0"},
    )
    restored = OfflineQueueItem.from_dict(item.to_dict())
    assert restored.method == item.method
    assert restored.path == item.path
    assert restored.payload == item.payload
    assert restored.id == item.id


# ──────────────────────────────────────────────
# Config save / load
# ──────────────────────────────────────────────

def test_save_and_load_config(tmp_path):
    config_file = tmp_path / "config.json"
    config_dir = tmp_path

    with patch("evalcraft.cloud.client._CONFIG_DIR", config_dir), \
         patch("evalcraft.cloud.client._CONFIG_FILE", config_file):
        EvalcraftCloud.save_config("ec_saved_key", "https://custom.api.dev/v1")
        loaded = EvalcraftCloud.load_config()

    assert loaded["api_key"] == "ec_saved_key"
    assert loaded["base_url"] == "https://custom.api.dev/v1"


def test_load_config_missing_returns_empty(tmp_path):
    with patch("evalcraft.cloud.client._CONFIG_FILE", tmp_path / "missing.json"):
        assert EvalcraftCloud.load_config() == {}


# ──────────────────────────────────────────────
# check_connection()
# ──────────────────────────────────────────────

def test_check_connection_ok(client):
    mock_resp = _make_mock_response({"status": "ok", "version": "0.1.0"})
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = client.check_connection()
    assert result["ok"] is True
    assert "Connected" in result["message"]


def test_check_connection_unreachable(client):
    err = urllib.error.URLError("name resolution failed")
    with patch("urllib.request.urlopen", side_effect=err):
        with patch("time.sleep"):
            result = client.check_connection()
    assert result["ok"] is False
    assert result["message"] != ""


# ──────────────────────────────────────────────
# CaptureContext cloud=True auto-upload
# ──────────────────────────────────────────────

def test_capture_context_auto_upload(tmp_path):
    """CaptureContext(cloud=True) should auto-upload on exit."""
    mock_client = MagicMock()
    mock_client.upload.return_value = {"id": "cas_auto"}

    # Inject mock client via cloud= param
    from evalcraft.capture.recorder import CaptureContext
    with CaptureContext(name="auto_test", cloud=mock_client) as ctx:
        ctx.record_output("hello world")

    mock_client.upload.assert_called_once()
    uploaded_cassette = mock_client.upload.call_args[0][0]
    assert uploaded_cassette.name == "auto_test"


def test_capture_context_auto_upload_failure_does_not_raise(tmp_path):
    """Auto-upload failure should not propagate — just log."""
    mock_client = MagicMock()
    mock_client.upload.side_effect = Exception("network gone")

    from evalcraft.capture.recorder import CaptureContext
    # Should not raise even if upload fails
    with CaptureContext(name="fail_test", cloud=mock_client) as ctx:
        ctx.record_output("output")

    mock_client.upload.assert_called_once()


def test_capture_context_cloud_false_no_upload():
    """CaptureContext(cloud=False) should never call upload."""
    mock_client = MagicMock()

    from evalcraft.capture.recorder import CaptureContext
    with CaptureContext(name="no_cloud", cloud=False) as ctx:
        ctx.record_output("x")

    mock_client.upload.assert_not_called()
