"""EvalcraftCloud — HTTP client for pushing cassettes and golden sets to the dashboard.

Features:
- Retry with exponential backoff (configurable max retries + jitter)
- Offline queue: when the API is unreachable, payloads are saved to
  ~/.evalcraft/queue/ and re-attempted on the next flush_queue() call
- API-key auth via Bearer token
- Config persisted to ~/.evalcraft/config.json

Usage:
    cloud = EvalcraftCloud(api_key="ec_...")
    cloud.upload(cassette)
    cloud.upload_golden(golden_set)
    cassettes = cloud.list_cassettes(project="my-project")
    regressions = cloud.get_regressions(project="my-project")

    # Flush any queued offline uploads
    cloud.flush_queue()
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.evalcraft.dev/v1"
_CONFIG_DIR = Path.home() / ".evalcraft"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_QUEUE_DIR = _CONFIG_DIR / "queue"


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class CloudUploadError(Exception):
    """Raised when an upload fails after all retries."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# ──────────────────────────────────────────────
# Offline queue item
# ──────────────────────────────────────────────

@dataclass
class OfflineQueueItem:
    """A failed upload saved to disk for later retry."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    method: str = "POST"
    path: str = ""
    payload: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    attempts: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "method": self.method,
            "path": self.path,
            "payload": self.payload,
            "created_at": self.created_at,
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OfflineQueueItem:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            method=data.get("method", "POST"),
            path=data.get("path", ""),
            payload=data.get("payload", {}),
            created_at=data.get("created_at", time.time()),
            attempts=data.get("attempts", 0),
        )


# ──────────────────────────────────────────────
# Cloud client
# ──────────────────────────────────────────────

class EvalcraftCloud:
    """HTTP client for the Evalcraft SaaS dashboard.

    Args:
        api_key: Bearer token (``ec_...``).  If None, reads from
            ``~/.evalcraft/config.json`` or the ``EVALCRAFT_API_KEY``
            environment variable.
        base_url: Override the default API endpoint.
        timeout: Request timeout in seconds (default 30).
        max_retries: Maximum number of retry attempts for transient errors
            (default 3).  Uses exponential backoff with jitter.
        queue_dir: Directory for the offline queue (default
            ``~/.evalcraft/queue``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 30,
        max_retries: int = 3,
        queue_dir: Path | None = None,
    ):
        self.api_key = api_key or self._load_api_key()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.queue_dir = queue_dir or _QUEUE_DIR

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def upload(self, cassette: Any) -> dict:
        """Upload a Cassette to the dashboard.

        Args:
            cassette: A ``Cassette`` instance.

        Returns:
            The server response as a dict (``{"id": ..., "url": ...}``).

        Raises:
            CloudUploadError: If upload fails after all retries.  The cassette
                is queued to disk for later retry instead.
        """
        payload = cassette.to_dict()
        try:
            return self._request("POST", "/cassettes", payload)
        except CloudUploadError:
            self._enqueue("POST", "/cassettes", payload)
            raise

    def upload_golden(self, golden_set: Any) -> dict:
        """Upload a GoldenSet to the dashboard.

        Args:
            golden_set: A ``GoldenSet`` instance.

        Returns:
            The server response as a dict.

        Raises:
            CloudUploadError: If upload fails after all retries.  The golden
                set is queued to disk for later retry instead.
        """
        payload = golden_set.to_dict()
        try:
            return self._request("POST", "/golden-sets", payload)
        except CloudUploadError:
            self._enqueue("POST", "/golden-sets", payload)
            raise

    def list_cassettes(self, project: str) -> list[dict]:
        """List cassettes stored in the dashboard for a project.

        Args:
            project: Project identifier.

        Returns:
            A list of cassette summary dicts.
        """
        qs = urllib.parse.urlencode({"project": project})
        return self._request("GET", f"/cassettes?{qs}")  # type: ignore[return-value]

    def get_regressions(self, project: str) -> list[dict]:
        """Get regression history for a project from the dashboard.

        Args:
            project: Project identifier.

        Returns:
            A list of regression report dicts.
        """
        qs = urllib.parse.urlencode({"project": project})
        return self._request("GET", f"/regressions?{qs}")  # type: ignore[return-value]

    def flush_queue(self) -> tuple[int, int]:
        """Attempt to upload all items in the offline queue.

        Returns:
            ``(succeeded, failed)`` counts.
        """
        queue_files = sorted(self.queue_dir.glob("*.json")) if self.queue_dir.exists() else []
        succeeded = 0
        failed = 0

        for fpath in queue_files:
            try:
                item = OfflineQueueItem.from_dict(json.loads(fpath.read_text()))
            except Exception as exc:
                logger.warning("Could not read queue item %s: %s", fpath, exc)
                failed += 1
                continue

            item.attempts += 1
            try:
                self._request(item.method, item.path, item.payload)
                fpath.unlink(missing_ok=True)
                succeeded += 1
                logger.info("Flushed queued item %s", item.id)
            except CloudUploadError as exc:
                logger.warning("Queue flush failed for %s: %s", item.id, exc)
                # Update attempt count on disk
                fpath.write_text(json.dumps(item.to_dict(), indent=2))
                failed += 1

        return succeeded, failed

    def queue_size(self) -> int:
        """Return the number of items waiting in the offline queue."""
        if not self.queue_dir.exists():
            return 0
        return len(list(self.queue_dir.glob("*.json")))

    # ──────────────────────────────────────────
    # Config helpers (used by CLI)
    # ──────────────────────────────────────────

    @staticmethod
    def save_config(api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        """Persist API key and base URL to ``~/.evalcraft/config.json``."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config: dict = {}
        if _CONFIG_FILE.exists():
            try:
                config = json.loads(_CONFIG_FILE.read_text())
            except Exception:
                pass
        config["api_key"] = api_key
        config["base_url"] = base_url
        _CONFIG_FILE.write_text(json.dumps(config, indent=2))
        _CONFIG_FILE.chmod(0o600)

    @staticmethod
    def load_config() -> dict:
        """Load config from ``~/.evalcraft/config.json``."""
        if not _CONFIG_FILE.exists():
            return {}
        try:
            return json.loads(_CONFIG_FILE.read_text())
        except Exception:
            return {}

    def check_connection(self) -> dict:
        """Ping the API and return status info.

        Returns:
            Dict with ``{"ok": True/False, "message": "...", ...}``.
        """
        try:
            result = self._request("GET", "/ping")
            return {"ok": True, "message": "Connected", "detail": result}
        except CloudUploadError as exc:
            return {"ok": False, "message": str(exc), "detail": None}
        except Exception as exc:
            return {"ok": False, "message": f"Unexpected error: {exc}", "detail": None}

    # ──────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────

    def _load_api_key(self) -> str:
        """Load API key from config file or environment variable."""
        import os
        env_key = os.environ.get("EVALCRAFT_API_KEY", "")
        if env_key:
            return env_key
        config = self.load_config()
        return config.get("api_key", "")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> dict | list:
        """Make an authenticated HTTP request with exponential-backoff retry.

        Args:
            method: HTTP method (``GET``, ``POST``, etc.).
            path: Path relative to base_url (may include query string).
            payload: JSON-serialisable body for POST/PUT.

        Returns:
            Parsed JSON response.

        Raises:
            CloudUploadError: After max_retries exhausted or on 4xx errors.
        """
        url = f"{self.base_url}{path}"
        body: bytes | None = None
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "evalcraft-sdk/0.1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if payload is not None:
            body = json.dumps(payload, default=str).encode("utf-8")
            headers["Content-Type"] = "application/json"

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                # Exponential backoff with jitter: 2^attempt * (0.5..1.5)
                sleep_s = (2 ** attempt) * (0.5 + random.random())
                logger.debug("Retry %d/%d for %s %s — sleeping %.2fs",
                             attempt, self.max_retries, method, path, sleep_s)
                time.sleep(sleep_s)

            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                status = exc.code
                # 4xx errors are not retryable
                if 400 <= status < 500:
                    body_text = ""
                    try:
                        body_text = exc.read().decode("utf-8")
                    except Exception:
                        pass
                    raise CloudUploadError(
                        f"HTTP {status}: {exc.reason}. {body_text}",
                        status_code=status,
                    ) from exc
                # 5xx / other — retry
                last_exc = CloudUploadError(
                    f"HTTP {status}: {exc.reason}", status_code=status
                )
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                # Network/timeout errors — retry
                last_exc = CloudUploadError(f"Network error: {exc}")

        raise last_exc or CloudUploadError("Request failed after retries")

    def _enqueue(self, method: str, path: str, payload: dict) -> None:
        """Save a failed request to the offline queue."""
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        item = OfflineQueueItem(method=method, path=path, payload=payload)
        fpath = self.queue_dir / f"{item.id}.json"
        fpath.write_text(json.dumps(item.to_dict(), indent=2))
        logger.info("Queued upload %s to %s (offline queue size: %d)",
                    item.id, fpath, self.queue_size())
