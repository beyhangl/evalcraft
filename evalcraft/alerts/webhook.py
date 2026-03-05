"""GenericWebhook — POST regression reports as JSON to any HTTP endpoint."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from evalcraft.regression.detector import RegressionReport


@dataclass
class GenericWebhook:
    """POST regression report JSON to any HTTP endpoint with retry/backoff.

    Example::

        hook = GenericWebhook(
            url="https://example.com/hooks/evalcraft",
            auth_token="secret",
        )
        hook.send_regression(report)
    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    auth_token: str = ""
    max_retries: int = 3
    retry_delay: float = 1.0

    def send_regression(self, report: RegressionReport) -> None:
        """POST a single regression report as JSON."""
        self._post(report.to_dict())

    def send_summary(self, reports: list[RegressionReport]) -> None:
        """POST a summary of multiple regression reports as JSON."""
        any_critical = any(r.has_critical for r in reports)
        payload: dict[str, Any] = {
            "total_reports": len(reports),
            "total_regressions": sum(len(r.regressions) for r in reports),
            "has_critical": any_critical,
            "reports": [r.to_dict() for r in reports],
        }
        self._post(payload)

    # ──────────────────────────────────────────
    # HTTP with retry/backoff
    # ──────────────────────────────────────────

    def _post(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.headers}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            req = urllib.request.Request(
                self.url,
                data=data,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10):
                    return  # 2xx — success
            except urllib.error.HTTPError as exc:
                last_exc = exc
                # Don't retry client errors (4xx)
                if exc.code < 500:
                    raise
            except urllib.error.URLError as exc:
                last_exc = exc

            if attempt < self.max_retries:
                time.sleep(self.retry_delay * (2 ** (attempt - 1)))

        raise last_exc  # type: ignore[misc]
