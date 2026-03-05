"""Tests for evalcraft.replay.network_guard.

Covers:
- ReplayNetworkViolation error attributes and message
- NetworkGuard blocks connections by default
- NetworkGuard allowlist permits specific hosts
- Nesting / stacking guards
- Guard is not active outside context manager
- socket.create_connection restored after exit
- Guard works as async context manager
- NetworkGuard.is_active() helper
- NetworkGuard.allowlist property
- ReplayEngine block_network integration (default on)
- ReplayEngine block_network=False skips guard
- ReplayEngine network_allowlist forwarded to guard
- replay() convenience function block_network kwarg
- CLI --block-network / --no-block-network flags
- CLI --allow-host option
"""

from __future__ import annotations

import importlib
import socket
import threading
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Import sub-modules directly to avoid the name-shadowing caused by
# ``evalcraft.__init__`` exporting a ``replay`` function that masks the
# ``evalcraft.replay`` subpackage when patch() resolves dotted paths.
import sys as _sys
import importlib as _importlib

_ng_module = _importlib.import_module("evalcraft.replay.network_guard")
_engine_module = _importlib.import_module("evalcraft.replay.engine")

from evalcraft.replay.network_guard import (
    NetworkGuard,
    ReplayNetworkViolation,
    _active_guards,
    _real_create_connection,
)
from evalcraft.replay.engine import ReplayEngine, replay
from evalcraft.cli.main import cli


# ─── helpers ──────────────────────────────────────────────────────────────────

def _try_connect(host: str = "example.com", port: int = 80):
    """Attempt socket.create_connection — used in tests to trigger the guard."""
    socket.create_connection((host, port), timeout=0.01)


# ─── ReplayNetworkViolation ────────────────────────────────────────────────────

class TestReplayNetworkViolation:
    def test_is_runtime_error(self):
        exc = ReplayNetworkViolation("api.example.com", 443)
        assert isinstance(exc, RuntimeError)

    def test_stores_host(self):
        exc = ReplayNetworkViolation("api.example.com", 443)
        assert exc.host == "api.example.com"

    def test_stores_port(self):
        exc = ReplayNetworkViolation("api.example.com", 443)
        assert exc.port == 443

    def test_message_contains_host(self):
        exc = ReplayNetworkViolation("api.example.com", 443)
        assert "api.example.com" in str(exc)

    def test_message_contains_port(self):
        exc = ReplayNetworkViolation("api.example.com", 8080)
        assert "8080" in str(exc)

    def test_message_mentions_allowlist(self):
        exc = ReplayNetworkViolation("api.example.com", 443)
        assert "allowlist" in str(exc).lower()

    def test_string_port_stored(self):
        exc = ReplayNetworkViolation("localhost", "ftp")
        assert exc.port == "ftp"


# ─── NetworkGuard — basic blocking ────────────────────────────────────────────

class TestNetworkGuardBlocking:
    def test_blocks_connection_inside_context(self):
        with NetworkGuard():
            with pytest.raises(ReplayNetworkViolation):
                _try_connect("example.com", 80)

    def test_does_not_block_outside_context(self):
        """After the guard exits, socket.create_connection must be restored."""
        with NetworkGuard():
            pass  # enter and exit immediately

        # After exiting, create_connection should be the real function again.
        assert socket.create_connection is _real_create_connection

    def test_raises_on_https_port(self):
        with NetworkGuard():
            with pytest.raises(ReplayNetworkViolation):
                _try_connect("secure.example.com", 443)

    def test_violation_carries_correct_host(self):
        with NetworkGuard():
            try:
                _try_connect("api.openai.com", 443)
            except ReplayNetworkViolation as exc:
                assert exc.host == "api.openai.com"
            else:
                pytest.fail("Expected ReplayNetworkViolation")

    def test_violation_carries_correct_port(self):
        with NetworkGuard():
            try:
                _try_connect("some.host", 9999)
            except ReplayNetworkViolation as exc:
                assert exc.port == 9999
            else:
                pytest.fail("Expected ReplayNetworkViolation")


# ─── NetworkGuard — allowlist ──────────────────────────────────────────────────

class TestNetworkGuardAllowlist:
    def test_allowlist_host_is_not_blocked(self):
        """Hosts in the allowlist should pass through to the real function.

        We mock _real_create_connection so we don't need a live server.
        """
        mock_sock = MagicMock()
        with patch.object(_ng_module, "_real_create_connection", return_value=mock_sock):
            with NetworkGuard(allowlist=["localhost"]):
                result = socket.create_connection(("localhost", 8080))
                assert result is mock_sock

    def test_non_allowlisted_host_still_blocked(self):
        with patch.object(_ng_module, "_real_create_connection"):
            with NetworkGuard(allowlist=["localhost"]):
                with pytest.raises(ReplayNetworkViolation):
                    _try_connect("external.example.com", 80)

    def test_empty_allowlist_blocks_all(self):
        with NetworkGuard(allowlist=[]):
            with pytest.raises(ReplayNetworkViolation):
                _try_connect("localhost", 8080)

    def test_multiple_hosts_in_allowlist(self):
        mock_sock = MagicMock()
        with patch.object(_ng_module, "_real_create_connection", return_value=mock_sock):
            with NetworkGuard(allowlist=["localhost", "127.0.0.1", "::1"]):
                # Each allowed host passes through
                for host in ["localhost", "127.0.0.1", "::1"]:
                    result = socket.create_connection((host, 9000))
                    assert result is mock_sock

    def test_allowlist_is_exact_match(self):
        """'localhos' (typo) should NOT match 'localhost'."""
        with NetworkGuard(allowlist=["localhos"]):
            with pytest.raises(ReplayNetworkViolation):
                _try_connect("localhost", 8080)

    def test_allowlist_property_returns_frozenset(self):
        guard = NetworkGuard(allowlist=["a.com", "b.com"])
        assert isinstance(guard.allowlist, frozenset)
        assert "a.com" in guard.allowlist
        assert "b.com" in guard.allowlist

    def test_none_allowlist_treated_as_empty(self):
        guard = NetworkGuard(allowlist=None)
        assert len(guard.allowlist) == 0


# ─── NetworkGuard — is_active ──────────────────────────────────────────────────

class TestNetworkGuardIsActive:
    def test_not_active_before_enter(self):
        guard = NetworkGuard()
        assert not guard.is_active()

    def test_active_inside_context(self):
        guard = NetworkGuard()
        with guard:
            assert guard.is_active()

    def test_not_active_after_exit(self):
        guard = NetworkGuard()
        with guard:
            pass
        assert not guard.is_active()

    def test_double_exit_is_safe(self):
        """Calling __exit__ twice should not raise."""
        guard = NetworkGuard()
        guard.__enter__()
        guard.__exit__(None, None, None)
        guard.__exit__(None, None, None)  # should not raise


# ─── NetworkGuard — nesting ────────────────────────────────────────────────────

class TestNetworkGuardNesting:
    def test_nested_guard_still_blocks(self):
        with NetworkGuard():
            with NetworkGuard():
                with pytest.raises(ReplayNetworkViolation):
                    _try_connect("example.com", 80)

    def test_socket_restored_after_nested_exit(self):
        with NetworkGuard():
            with NetworkGuard():
                pass
            # Inner exited, outer still active — should still block
            with pytest.raises(ReplayNetworkViolation):
                _try_connect("example.com", 80)

        # Both exited — real function back
        assert socket.create_connection is _real_create_connection

    def test_outer_allowlist_honoured_when_inner_exits(self):
        mock_sock = MagicMock()
        with patch.object(_ng_module, "_real_create_connection", return_value=mock_sock):
            with NetworkGuard(allowlist=["localhost"]):
                with NetworkGuard(allowlist=["127.0.0.1"]):
                    pass  # inner exits, outer is now controlling
                # After inner exits the outer guard is in control;
                # localhost is in the outer allowlist → should pass
                result = socket.create_connection(("localhost", 8080))
                assert result is mock_sock


# ─── NetworkGuard — async context manager ─────────────────────────────────────

class TestNetworkGuardAsync:
    @pytest.mark.asyncio
    async def test_async_context_blocks(self):
        async with NetworkGuard():
            with pytest.raises(ReplayNetworkViolation):
                _try_connect("example.com", 80)

    @pytest.mark.asyncio
    async def test_async_context_restores_on_exit(self):
        async with NetworkGuard():
            pass
        assert socket.create_connection is _real_create_connection

    @pytest.mark.asyncio
    async def test_async_allowlist(self):
        mock_sock = MagicMock()
        with patch.object(_ng_module, "_real_create_connection", return_value=mock_sock):
            async with NetworkGuard(allowlist=["localhost"]):
                result = socket.create_connection(("localhost", 5432))
                assert result is mock_sock


# ─── ReplayEngine integration ─────────────────────────────────────────────────

class TestReplayEngineNetworkGuard:
    def test_engine_blocks_network_by_default(self, simple_cassette):
        """ReplayEngine.run() should activate NetworkGuard by default."""
        engine = ReplayEngine(simple_cassette)
        assert engine._block_network is True

    def test_engine_run_does_not_make_real_calls(self, simple_cassette):
        """run() on a pure-replay cassette completes without network activity."""
        engine = ReplayEngine(simple_cassette)
        # Should NOT raise — no real network calls happen in _run_spans
        run = engine.run()
        assert run.success is True

    def test_engine_block_network_false_skips_guard(self, simple_cassette):
        engine = ReplayEngine(simple_cassette, block_network=False)
        assert engine._block_network is False
        # Guard stack should be empty before and after
        before = len(_active_guards)
        engine.run()
        assert len(_active_guards) == before

    def test_engine_network_allowlist_forwarded(self, simple_cassette):
        """network_allowlist passed to ReplayEngine is stored correctly."""
        engine = ReplayEngine(
            simple_cassette,
            block_network=True,
            network_allowlist=["localhost", "127.0.0.1"],
        )
        assert set(engine._network_allowlist) == {"localhost", "127.0.0.1"}

    def test_guard_not_active_after_run(self, simple_cassette):
        """NetworkGuard must be cleaned up after engine.run() completes."""
        engine = ReplayEngine(simple_cassette)
        engine.run()
        assert socket.create_connection is _real_create_connection

    def test_guard_cleaned_up_on_run_exception(self, simple_cassette):
        """Even if _run_spans raises, the guard should be cleaned up."""
        engine = ReplayEngine(simple_cassette)
        with patch.object(engine, "_run_spans", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                engine.run()
        assert socket.create_connection is _real_create_connection


# ─── replay() convenience function ────────────────────────────────────────────

class TestReplayConvenienceFnNetworkGuard:
    def test_replay_fn_blocks_by_default(self, cassette_file):
        path, _ = cassette_file
        # Just ensure no exception during normal replay (no real network calls)
        run = replay(path)
        assert run.success is True

    def test_replay_fn_block_network_false(self, cassette_file):
        path, _ = cassette_file
        run = replay(path, block_network=False)
        assert run.success is True
        # Guard should not be active
        assert socket.create_connection is _real_create_connection

    def test_replay_fn_network_allowlist(self, cassette_file):
        path, _ = cassette_file
        run = replay(path, network_allowlist=["localhost"])
        assert run.success is True


# ─── CLI integration ───────────────────────────────────────────────────────────

class TestCLINetworkGuardFlags:
    def _make_cassette_file(self, tmp_path, simple_cassette):
        path = tmp_path / "test.cassette.json"
        simple_cassette.save(path)
        return str(path)

    def test_cli_replay_default_shows_network_blocked(self, tmp_path, simple_cassette):
        path = self._make_cassette_file(tmp_path, simple_cassette)
        runner = CliRunner()
        result = runner.invoke(cli, ["replay", path])
        assert result.exit_code == 0
        assert "network blocked" in result.output

    def test_cli_replay_no_block_network_hides_note(self, tmp_path, simple_cassette):
        path = self._make_cassette_file(tmp_path, simple_cassette)
        runner = CliRunner()
        result = runner.invoke(cli, ["replay", path, "--no-block-network"])
        assert result.exit_code == 0
        assert "network blocked" not in result.output

    def test_cli_replay_allow_host_shows_in_output(self, tmp_path, simple_cassette):
        path = self._make_cassette_file(tmp_path, simple_cassette)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["replay", path, "--allow-host", "localhost"]
        )
        assert result.exit_code == 0
        assert "localhost" in result.output

    def test_cli_replay_multiple_allow_hosts(self, tmp_path, simple_cassette):
        path = self._make_cassette_file(tmp_path, simple_cassette)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["replay", path, "--allow-host", "localhost", "--allow-host", "127.0.0.1"],
        )
        assert result.exit_code == 0
        assert "localhost" in result.output
        assert "127.0.0.1" in result.output

    def test_cli_replay_network_violation_exits_nonzero(self, tmp_path, simple_cassette):
        """If a real network call escapes during replay, exit code must be 1."""
        path = self._make_cassette_file(tmp_path, simple_cassette)
        runner = CliRunner()

        # Patch _run_spans to simulate a network violation
        with patch.object(
            _engine_module.ReplayEngine,
            "_run_spans",
            side_effect=ReplayNetworkViolation("api.example.com", 443),
        ):
            result = runner.invoke(cli, ["replay", path])

        assert result.exit_code == 1
        assert "network violation" in result.output.lower()
