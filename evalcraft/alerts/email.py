"""EmailAlert — send regression notifications via SMTP."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from evalcraft.regression.detector import Regression, RegressionReport, Severity

_SEV_BADGE_STYLE = {
    Severity.CRITICAL: "background:#ffebee;color:#E53935;",
    Severity.WARNING: "background:#fff3e0;color:#FB8C00;",
    Severity.INFO: "background:#e3f2fd;color:#1E88E5;",
}

_SEV_ROW_BG = {
    Severity.CRITICAL: "#fff5f5",
    Severity.WARNING: "#fffdf0",
    Severity.INFO: "#f5f9ff",
}


@dataclass
class SMTPConfig:
    """SMTP connection settings."""

    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True


@dataclass
class EmailAlert:
    """Send regression notifications via SMTP.

    Example::

        cfg = SMTPConfig(host="smtp.example.com", username="user", password="pass")
        alert = EmailAlert(smtp=cfg, sender="evalcraft@example.com")
        alert.send_regression(report, recipients=["team@example.com"])
    """

    smtp: SMTPConfig
    sender: str = "evalcraft@localhost"

    def send_regression(self, report: RegressionReport, recipients: list[str]) -> None:
        """Send a regression report email to the given recipients."""
        if not report.has_regressions:
            return
        max_sev = report.max_severity.value if report.max_severity else "INFO"
        subject = (
            f"[Evalcraft] Regression detected: {report.golden_name}"
            f" ({max_sev})"
        )
        html = _build_html(report)
        self._send(subject, html, recipients)

    # ──────────────────────────────────────────
    # SMTP delivery
    # ──────────────────────────────────────────

    def _send(self, subject: str, html: str, recipients: list[str]) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(self.smtp.host, self.smtp.port) as server:
            if self.smtp.use_tls:
                server.starttls()
            if self.smtp.username:
                server.login(self.smtp.username, self.smtp.password)
            server.sendmail(self.sender, recipients, msg.as_string())


# ──────────────────────────────────────────
# HTML template
# ──────────────────────────────────────────

def _build_html(report: RegressionReport) -> str:
    """Build an HTML email body for the given regression report."""
    max_sev = report.max_severity
    max_sev_label = max_sev.value if max_sev else "NONE"
    badge_style = _SEV_BADGE_STYLE.get(max_sev, "background:#eee;color:#333;") if max_sev else "background:#eee;color:#333;"

    rows_html = _build_table_rows(report.regressions)
    count = len(report.regressions)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #333;
      max-width: 760px;
      margin: 0 auto;
      padding: 24px;
      background: #f9f9f9;
    }}
    .card {{
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
      padding: 24px 28px;
    }}
    h2 {{ margin: 0 0 4px; font-size: 20px; color: #1a1a1a; }}
    .subtitle {{ color: #666; margin: 0 0 20px; font-size: 14px; }}
    .badge {{
      display: inline-block;
      padding: 2px 10px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 700;
      {badge_style}
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin-top: 16px;
      font-size: 14px;
    }}
    th {{
      background: #f5f5f5;
      text-align: left;
      padding: 9px 12px;
      border-bottom: 2px solid #e0e0e0;
      font-weight: 600;
      color: #555;
    }}
    td {{
      padding: 8px 12px;
      border-bottom: 1px solid #eee;
      vertical-align: top;
    }}
    .sev-critical {{ color: #E53935; font-weight: 700; }}
    .sev-warning  {{ color: #FB8C00; font-weight: 700; }}
    .sev-info     {{ color: #1E88E5; font-weight: 700; }}
    .mono {{ font-family: monospace; font-size: 12px; }}
    .footer {{ margin-top: 20px; color: #aaa; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>Regression Report</h2>
    <p class="subtitle">
      Cassette: <strong>{escape(report.golden_name)}</strong> &mdash;
      {count} regression(s) found &mdash;
      Max severity: <span class="badge">{escape(max_sev_label)}</span>
    </p>
    <table>
      <thead>
        <tr>
          <th>Severity</th>
          <th>Category</th>
          <th>Message</th>
          <th>Golden&nbsp;Value</th>
          <th>Current&nbsp;Value</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    <p class="footer">Sent by <strong>Evalcraft</strong></p>
  </div>
</body>
</html>"""


def _build_table_rows(regressions: list[Regression]) -> str:
    rows: list[str] = []
    for r in regressions:
        sev_class = f"sev-{r.severity.value.lower()}"
        row_bg = _SEV_ROW_BG.get(r.severity, "#fff")
        golden = escape(str(r.golden_value)) if r.golden_value is not None else "&mdash;"
        current = escape(str(r.current_value)) if r.current_value is not None else "&mdash;"
        rows.append(
            f'<tr style="background:{row_bg}">'
            f'<td class="{sev_class}">{escape(r.severity.value)}</td>'
            f'<td class="mono">{escape(r.category)}</td>'
            f'<td>{escape(r.message)}</td>'
            f'<td class="mono">{golden}</td>'
            f'<td class="mono">{current}</td>'
            f'</tr>'
        )
    return "\n        ".join(rows)
