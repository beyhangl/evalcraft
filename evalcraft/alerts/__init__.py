"""evalcraft.alerts — send regression notifications to Slack, email, and webhooks."""

from evalcraft.alerts.email import EmailAlert, SMTPConfig
from evalcraft.alerts.slack import SlackAlert
from evalcraft.alerts.webhook import GenericWebhook

__all__ = ["SlackAlert", "EmailAlert", "SMTPConfig", "GenericWebhook"]
