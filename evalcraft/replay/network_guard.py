"""NetworkGuard — blocks outgoing HTTP requests during cassette replay.

When a cassette is being replayed, real network requests should never
escape to the outside world.  NetworkGuard enforces this by monkey-
patching ``socket.create_connection`` (the low-level hook used by
``http.client``, ``urllib``, ``requests``, ``httpx``, and most other
HTTP libraries) and raising ``ReplayNetworkViolation`` the moment any
blocked connection attempt is made.

Usage::

    from evalcraft.replay.network_guard import NetworkGuard

    with NetworkGuard():
        # Any outgoing HTTP call here will raise ReplayNetworkViolation
        requests.get("https://api.example.com/data")   # raises!

    # Allow specific domains (e.g. localhost for integration tests):
    with NetworkGuard(allowlist=["localhost", "127.0.0.1"]):
        requests.get("http://localhost:8080/health")   # OK
        requests.get("https://api.example.com/data")   # raises!
"""

from __future__ import annotations

import socket
import threading
from typing import Collection, Sequence


# ─── exception ────────────────────────────────────────────────────────────────

class ReplayNetworkViolation(RuntimeError):
    """Raised when an outgoing network request is attempted during replay.

    Attributes:
        host: The hostname that was blocked.
        port: The port that was blocked.
    """

    def __init__(self, host: str, port: int | str) -> None:
        self.host = host
        self.port = port
        super().__init__(
            f"Network request blocked during replay: attempted connection to "
            f"{host!r} on port {port}.  "
            f"Replay should be fully deterministic — if you need this host, "
            f"add it to the NetworkGuard allowlist."
        )


# ─── guard ────────────────────────────────────────────────────────────────────

_guard_lock = threading.Lock()
_active_guards: list["NetworkGuard"] = []

# Save the real implementation once, at import time, so nested guards and
# re-entrance can always restore back to the true original.
_real_create_connection = socket.create_connection


class NetworkGuard:
    """Context manager that blocks outgoing network connections during replay.

    When active, ``socket.create_connection`` is replaced with a blocking
    stub.  Any host that is **not** in ``allowlist`` will immediately raise
    :class:`ReplayNetworkViolation`.

    Args:
        allowlist: Collection of hostnames or IP addresses that are
            permitted to connect even while the guard is active.
            Defaults to an empty list (block everything).

    Example::

        # Block all outgoing calls
        with NetworkGuard():
            ...

        # Allow localhost only
        with NetworkGuard(allowlist=["localhost", "127.0.0.1", "::1"]):
            ...
    """

    def __init__(self, allowlist: Collection[str] | None = None) -> None:
        self._allowlist: frozenset[str] = frozenset(allowlist or [])

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "NetworkGuard":
        self._install()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._uninstall()
        return None  # never suppress exceptions

    # ------------------------------------------------------------------
    # Async context manager protocol (for use with asyncio / anyio code)
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "NetworkGuard":
        self._install()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._uninstall()
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _install(self) -> None:
        """Activate the guard by monkey-patching socket.create_connection."""
        with _guard_lock:
            _active_guards.append(self)
            # Only patch once — the outermost guard owns the patch.
            if len(_active_guards) == 1:
                socket.create_connection = self._blocking_create_connection

    def _uninstall(self) -> None:
        """Deactivate this guard and restore socket.create_connection if needed."""
        with _guard_lock:
            try:
                _active_guards.remove(self)
            except ValueError:
                # Guard was already removed (double-exit guard).
                return

            if not _active_guards:
                # Last guard removed — restore the real function.
                socket.create_connection = _real_create_connection
            else:
                # Outer guard is still active; keep the blocking stub in place
                # but update it to reflect the outermost guard's allowlist.
                socket.create_connection = _active_guards[0]._blocking_create_connection

    def _is_allowed(self, host: str) -> bool:
        """Return True if *host* is in this guard's allowlist."""
        return host in self._allowlist

    def _blocking_create_connection(
        self,
        address: tuple[str, int],
        timeout: float = socket._GLOBAL_DEFAULT_TIMEOUT,  # type: ignore[attr-defined]
        source_address: tuple[str, int] | None = None,
        *,
        all_errors: bool = False,
    ) -> socket.socket:
        """Replacement for socket.create_connection that blocks non-allowed hosts."""
        host, port = address

        # Walk the guard stack (innermost guard first).  If *any* active
        # guard allows this host we let the call through.
        with _guard_lock:
            active_snapshot = list(_active_guards)

        for guard in reversed(active_snapshot):
            if guard._is_allowed(host):
                return _real_create_connection(
                    address, timeout, source_address, all_errors=all_errors
                )

        raise ReplayNetworkViolation(host, port)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def allowlist(self) -> frozenset[str]:
        """The set of allowed hosts for this guard."""
        return self._allowlist

    def is_active(self) -> bool:
        """Return True if this guard is currently installed."""
        with _guard_lock:
            return self in _active_guards
