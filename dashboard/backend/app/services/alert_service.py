"""Alert dispatch — Slack / email / webhook notifications for regressions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from app.models.regression import Alert, AlertChannel, RegressionEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def send_alerts(
    events: list[RegressionEvent],
    db: "AsyncSession",
    *,
    slack_webhook_url: str | None = None,
) -> list[Alert]:
    """Create and dispatch alerts for regression events.

    Currently supports Slack webhooks. Email and generic webhook
    channels are stubbed for future implementation.
    """
    alerts: list[Alert] = []

    for event in events:
        if event.severity in ("WARNING", "CRITICAL") and slack_webhook_url:
            alert = Alert(
                regression_event_id=event.id,
                channel=AlertChannel.SLACK.value,
            )
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        slack_webhook_url,
                        json={
                            "text": (
                                f"*[{event.severity}]* Regression detected\n"
                                f"Category: {event.category}\n"
                                f"{event.message}"
                            ),
                        },
                    )
                    resp.raise_for_status()
                alert.sent = True
            except Exception as exc:
                logger.warning("Failed to send Slack alert: %s", exc)
                alert.error = str(exc)

            db.add(alert)
            alerts.append(alert)

    if alerts:
        await db.flush()

    return alerts
