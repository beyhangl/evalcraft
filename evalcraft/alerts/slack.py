"""SlackAlert — send regression notifications to Slack via incoming webhook."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from evalcraft.regression.detector import RegressionReport, Severity

_SEV_COLOR = {
    Severity.CRITICAL: "#E53935",
    Severity.WARNING: "#FB8C00",
    Severity.INFO: "#1E88E5",
}

_SEV_EMOJI = {
    Severity.CRITICAL: ":red_circle:",
    Severity.WARNING: ":large_yellow_circle:",
    Severity.INFO: ":large_blue_circle:",
}


@dataclass
class SlackAlert:
    """Send regression notifications to Slack via incoming webhook.

    Example::

        alert = SlackAlert(webhook_url="https://hooks.slack.com/services/...")
        alert.send_regression(report)
        alert.send_summary([report1, report2])
    """

    webhook_url: str
    channel: str = ""
    username: str = "Evalcraft"
    icon_emoji: str = ":robot_face:"
    mention_here_on_critical: bool = True

    def send_regression(self, report: RegressionReport) -> None:
        """Send a single regression report to Slack."""
        if not report.has_regressions:
            return
        payload = self._build_regression_payload(report)
        self._post(payload)

    def send_summary(self, reports: list[RegressionReport]) -> None:
        """Send a batch summary of multiple regression reports to Slack."""
        reports_with_regressions = [r for r in reports if r.has_regressions]
        if not reports_with_regressions:
            return
        payload = self._build_summary_payload(reports_with_regressions)
        self._post(payload)

    # ──────────────────────────────────────────
    # Payload builders
    # ──────────────────────────────────────────

    def _build_regression_payload(self, report: RegressionReport) -> dict[str, Any]:
        max_sev = report.max_severity
        color = _SEV_COLOR.get(max_sev, "#888888") if max_sev else "#888888"

        header = f":warning: Regression detected: *{report.golden_name}*"
        if self.mention_here_on_critical and report.has_critical:
            header = f"<!here> {header}"

        blocks: list[dict] = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": header},
            },
            {"type": "divider"},
        ]

        for sev in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
            items = report.by_severity(sev)
            if not items:
                continue

            sev_emoji = _SEV_EMOJI[sev]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{sev_emoji} *{sev.value}* ({len(items)} issue(s))",
                },
            })

            for r in items:
                text = f"*[{r.category}]* {r.message}"
                if r.golden_value is not None and r.current_value is not None:
                    text += (
                        f"\n• Golden: `{r.golden_value}`"
                        f"  →  Current: `{r.current_value}`"
                    )
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},
                })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"{len(report.regressions)} regression(s)"
                        f" | max severity: *{max_sev.value if max_sev else 'NONE'}*"
                    ),
                }
            ],
        })

        payload: dict[str, Any] = {
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                }
            ],
        }
        if self.channel:
            payload["channel"] = self.channel
        return payload

    def _build_summary_payload(self, reports: list[RegressionReport]) -> dict[str, Any]:
        any_critical = any(r.has_critical for r in reports)
        total_regressions = sum(len(r.regressions) for r in reports)

        header = (
            f":warning: Regression summary: "
            f"*{len(reports)} cassette(s)* with {total_regressions} total regression(s)"
        )
        if self.mention_here_on_critical and any_critical:
            header = f"<!here> {header}"

        blocks: list[dict] = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": header},
            },
            {"type": "divider"},
        ]

        for report in reports:
            max_sev = report.max_severity
            emoji = _SEV_EMOJI.get(max_sev, ":grey_question:") if max_sev else ":grey_question:"
            count = len(report.regressions)
            sev_label = max_sev.value if max_sev else "NONE"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *{report.golden_name}*"
                        f" — {count} regression(s), max: *{sev_label}*"
                    ),
                },
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Total: {total_regressions} regression(s)"
                        f" across {len(reports)} cassette(s)"
                    ),
                }
            ],
        })

        payload: dict[str, Any] = {
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "blocks": blocks,
        }
        if self.channel:
            payload["channel"] = self.channel
        return payload

    # ──────────────────────────────────────────
    # HTTP
    # ──────────────────────────────────────────

    def _post(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
