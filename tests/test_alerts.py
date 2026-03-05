"""Tests for evalcraft.alerts — Slack, email, and webhook integrations."""

from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, call, patch

import pytest

from evalcraft.alerts.email import EmailAlert, SMTPConfig, _build_html
from evalcraft.alerts.slack import SlackAlert
from evalcraft.alerts.webhook import GenericWebhook
from evalcraft.regression.detector import Regression, RegressionReport, Severity


# ──────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────

@pytest.fixture
def critical_report() -> RegressionReport:
    report = RegressionReport(golden_name="weather_agent")
    report.regressions = [
        Regression(
            category="cost_increase",
            severity=Severity.CRITICAL,
            message="Cost increased 3.50x",
            golden_value=0.001,
            current_value=0.0035,
            metadata={"ratio": 3.5},
        ),
        Regression(
            category="token_bloat",
            severity=Severity.WARNING,
            message="Token usage increased 1.40x",
            golden_value=1000,
            current_value=1400,
        ),
    ]
    return report


@pytest.fixture
def info_report() -> RegressionReport:
    report = RegressionReport(golden_name="summarizer_agent")
    report.regressions = [
        Regression(
            category="output_drift",
            severity=Severity.INFO,
            message="Output text differs from golden baseline",
            golden_value="hello world",
            current_value="hello earth",
        ),
    ]
    return report


@pytest.fixture
def empty_report() -> RegressionReport:
    return RegressionReport(golden_name="clean_agent")


def _mock_urlopen(status: int = 200) -> MagicMock:
    """Return a mock that urlopen returns as a context manager."""
    response = MagicMock()
    response.status = status
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=response)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


# ──────────────────────────────────────────
# SlackAlert
# ──────────────────────────────────────────

class TestSlackAlert:
    def test_send_regression_posts_to_webhook(self, critical_report):
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        mock_cm = _mock_urlopen(200)

        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_regression(critical_report)

        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://hooks.slack.com/test"
        assert req.get_header("Content-type") == "application/json"
        payload = json.loads(req.data)
        assert payload["username"] == "Evalcraft"

    def test_send_regression_skips_empty_report(self, empty_report):
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        with patch("urllib.request.urlopen") as mock_open:
            alert.send_regression(empty_report)
        mock_open.assert_not_called()

    def test_critical_report_includes_here_mention(self, critical_report):
        alert = SlackAlert(
            webhook_url="https://hooks.slack.com/test",
            mention_here_on_critical=True,
        )
        mock_cm = _mock_urlopen(200)
        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        payload = json.loads(req.data)
        # Header text should contain <!here>
        attachment_blocks = payload["attachments"][0]["blocks"]
        header_block = attachment_blocks[0]
        assert "<!here>" in header_block["text"]["text"]

    def test_no_here_mention_when_disabled(self, critical_report):
        alert = SlackAlert(
            webhook_url="https://hooks.slack.com/test",
            mention_here_on_critical=False,
        )
        mock_cm = _mock_urlopen(200)
        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        payload = json.loads(req.data)
        header_block = payload["attachments"][0]["blocks"][0]
        assert "<!here>" not in header_block["text"]["text"]

    def test_critical_color_in_attachment(self, critical_report):
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        mock_cm = _mock_urlopen(200)
        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["attachments"][0]["color"] == "#E53935"

    def test_info_color_in_attachment(self, info_report):
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        mock_cm = _mock_urlopen(200)
        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_regression(info_report)

        req = mock_open.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["attachments"][0]["color"] == "#1E88E5"

    def test_channel_included_when_set(self, critical_report):
        alert = SlackAlert(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
        )
        mock_cm = _mock_urlopen(200)
        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["channel"] == "#alerts"

    def test_send_summary_skips_when_all_clean(self):
        reports = [RegressionReport(golden_name="a"), RegressionReport(golden_name="b")]
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        with patch("urllib.request.urlopen") as mock_open:
            alert.send_summary(reports)
        mock_open.assert_not_called()

    def test_send_summary_posts_combined_payload(self, critical_report, info_report):
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        mock_cm = _mock_urlopen(200)
        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_summary([critical_report, info_report])

        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        payload = json.loads(req.data)
        # Summary uses top-level blocks, not attachments
        assert "blocks" in payload
        # Check <!here> present because critical_report has critical severity
        header = payload["blocks"][0]["text"]["text"]
        assert "<!here>" in header

    def test_payload_contains_golden_name(self, critical_report):
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        mock_cm = _mock_urlopen(200)
        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            alert.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        raw = req.data.decode()
        assert "weather_agent" in raw

    def test_http_error_propagates(self, critical_report):
        alert = SlackAlert(webhook_url="https://hooks.slack.com/test")
        err = urllib.error.HTTPError(
            url="https://hooks.slack.com/test",
            code=500,
            msg="Internal Server Error",
            hdrs=None,  # type: ignore
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(urllib.error.HTTPError):
                alert.send_regression(critical_report)


# ──────────────────────────────────────────
# EmailAlert
# ──────────────────────────────────────────

class TestEmailAlert:
    def _make_alert(self, **smtp_kwargs) -> EmailAlert:
        cfg = SMTPConfig(host="smtp.example.com", **smtp_kwargs)
        return EmailAlert(smtp=cfg, sender="eval@example.com")

    def test_send_regression_calls_smtp(self, critical_report):
        alert = self._make_alert()
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            alert.send_regression(critical_report, ["team@example.com"])

        mock_server.starttls.assert_called_once()
        mock_server.sendmail.assert_called_once()
        _from, _to, _msg = mock_server.sendmail.call_args[0]
        assert _from == "eval@example.com"
        assert _to == ["team@example.com"]

    def test_skips_empty_report(self, empty_report):
        alert = self._make_alert()
        with patch("smtplib.SMTP") as mock_smtp:
            alert.send_regression(empty_report, ["team@example.com"])
        mock_smtp.assert_not_called()

    def test_subject_contains_golden_name_and_severity(self, critical_report):
        alert = self._make_alert()
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            alert.send_regression(critical_report, ["team@example.com"])

        _from, _to, raw_msg = mock_server.sendmail.call_args[0]
        assert "weather_agent" in raw_msg
        assert "CRITICAL" in raw_msg

    def test_login_called_when_credentials_provided(self, critical_report):
        alert = self._make_alert(username="user", password="secret")
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            alert.send_regression(critical_report, ["team@example.com"])

        mock_server.login.assert_called_once_with("user", "secret")

    def test_no_login_when_no_credentials(self, critical_report):
        alert = self._make_alert()
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            alert.send_regression(critical_report, ["team@example.com"])

        mock_server.login.assert_not_called()

    def test_tls_disabled(self, critical_report):
        cfg = SMTPConfig(host="smtp.example.com", use_tls=False)
        alert = EmailAlert(smtp=cfg, sender="eval@example.com")
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            alert.send_regression(critical_report, ["team@example.com"])

        mock_server.starttls.assert_not_called()

    def test_multiple_recipients(self, critical_report):
        alert = self._make_alert()
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server):
            alert.send_regression(critical_report, ["a@x.com", "b@x.com"])

        _from, _to, _msg = mock_server.sendmail.call_args[0]
        assert _to == ["a@x.com", "b@x.com"]


class TestBuildHtml:
    def test_contains_golden_name(self, critical_report):
        html = _build_html(critical_report)
        assert "weather_agent" in html

    def test_contains_severity_labels(self, critical_report):
        html = _build_html(critical_report)
        assert "CRITICAL" in html
        assert "WARNING" in html

    def test_contains_regression_messages(self, critical_report):
        html = _build_html(critical_report)
        assert "Cost increased" in html
        assert "Token usage increased" in html

    def test_contains_golden_and_current_values(self, critical_report):
        html = _build_html(critical_report)
        assert "0.001" in html
        assert "0.0035" in html

    def test_html_structure(self, critical_report):
        html = _build_html(critical_report)
        assert "<table" in html
        assert "<tbody>" in html
        assert "</html>" in html

    def test_escapes_special_chars(self):
        report = RegressionReport(golden_name="<script>alert('xss')</script>")
        report.regressions = [
            Regression(
                category="test",
                severity=Severity.INFO,
                message="msg with <b>bold</b>",
                golden_value="<value>",
                current_value="&current",
            )
        ]
        html = _build_html(report)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "&lt;b&gt;" in html
        assert "&lt;value&gt;" in html
        assert "&amp;current" in html


# ──────────────────────────────────────────
# GenericWebhook
# ──────────────────────────────────────────

class TestGenericWebhook:
    def test_send_regression_posts_json(self, critical_report):
        hook = GenericWebhook(url="https://example.com/hook")
        mock_cm = _mock_urlopen(200)

        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            hook.send_regression(critical_report)

        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://example.com/hook"
        payload = json.loads(req.data)
        assert payload["golden_name"] == "weather_agent"
        assert payload["has_critical"] is True

    def test_auth_token_sets_authorization_header(self, critical_report):
        hook = GenericWebhook(url="https://example.com/hook", auth_token="mysecret")
        mock_cm = _mock_urlopen(200)

        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            hook.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer mysecret"

    def test_custom_headers_included(self, critical_report):
        hook = GenericWebhook(
            url="https://example.com/hook",
            headers={"X-Custom": "value"},
        )
        mock_cm = _mock_urlopen(200)

        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            hook.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        assert req.get_header("X-custom") == "value"

    def test_send_summary_includes_all_reports(self, critical_report, info_report):
        hook = GenericWebhook(url="https://example.com/hook")
        mock_cm = _mock_urlopen(200)

        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            hook.send_summary([critical_report, info_report])

        req = mock_open.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["total_reports"] == 2
        assert payload["total_regressions"] == 3  # 2 + 1
        assert payload["has_critical"] is True
        assert len(payload["reports"]) == 2

    def test_retries_on_server_error(self, critical_report):
        hook = GenericWebhook(url="https://example.com/hook", max_retries=3, retry_delay=0)
        server_err = urllib.error.HTTPError(
            url="https://example.com/hook",
            code=503,
            msg="Service Unavailable",
            hdrs=None,  # type: ignore
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=server_err) as mock_open:
            with pytest.raises(urllib.error.HTTPError):
                hook.send_regression(critical_report)

        assert mock_open.call_count == 3

    def test_no_retry_on_client_error(self, critical_report):
        hook = GenericWebhook(url="https://example.com/hook", max_retries=3, retry_delay=0)
        client_err = urllib.error.HTTPError(
            url="https://example.com/hook",
            code=400,
            msg="Bad Request",
            hdrs=None,  # type: ignore
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=client_err) as mock_open:
            with pytest.raises(urllib.error.HTTPError):
                hook.send_regression(critical_report)

        # Should NOT retry on 4xx
        assert mock_open.call_count == 1

    def test_retries_on_url_error(self, critical_report):
        hook = GenericWebhook(url="https://example.com/hook", max_retries=2, retry_delay=0)
        url_err = urllib.error.URLError("connection refused")

        with patch("urllib.request.urlopen", side_effect=url_err) as mock_open:
            with pytest.raises(urllib.error.URLError):
                hook.send_regression(critical_report)

        assert mock_open.call_count == 2

    def test_succeeds_on_second_attempt(self, critical_report):
        hook = GenericWebhook(url="https://example.com/hook", max_retries=3, retry_delay=0)
        server_err = urllib.error.HTTPError(
            url="https://example.com/hook",
            code=503,
            msg="Service Unavailable",
            hdrs=None,  # type: ignore
            fp=None,
        )
        mock_cm = _mock_urlopen(200)

        with patch("urllib.request.urlopen", side_effect=[server_err, mock_cm]) as mock_open:
            hook.send_regression(critical_report)  # Should not raise

        assert mock_open.call_count == 2

    def test_content_type_header_set(self, critical_report):
        hook = GenericWebhook(url="https://example.com/hook")
        mock_cm = _mock_urlopen(200)

        with patch("urllib.request.urlopen", return_value=mock_cm) as mock_open:
            hook.send_regression(critical_report)

        req = mock_open.call_args[0][0]
        assert req.get_header("Content-type") == "application/json"
