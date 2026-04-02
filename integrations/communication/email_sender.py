"""
EMAIL SENDER — sends emails via SMTP.
BOUNDARY: Delivers pre-formatted emails only. Never decides content or urgency.
Supports: SMTP (Gmail, Outlook, custom), or dry-run mode.
"""
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from pathlib import Path

EAT = timezone(timedelta(hours=3))


class EmailSender:
    """Send emails via configured SMTP provider."""

    def __init__(self):
        self.provider = os.getenv("EMAIL_PROVIDER", "dry_run")  # dry_run | smtp
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.smtp_user = os.getenv("EMAIL_SMTP_USER", "")
        self.smtp_password = os.getenv("EMAIL_SMTP_PASSWORD", "")
        self.from_email = os.getenv("EMAIL_FROM", "noreply@kra-helmet.co.ke")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "KRA Helmet")
        self._log_dir = Path(__file__).parent.parent.parent / "logs"
        self._log_dir.mkdir(exist_ok=True)

    def send(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        pin: str = "",
    ) -> dict:
        """Send an email. Returns delivery result."""
        if self.provider == "dry_run" or not self.smtp_user:
            return self._dry_run(to_email, subject, body_text, pin)

        return self._send_smtp(to_email, subject, body_text, body_html, pin)

    def _send_smtp(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None,
        pin: str,
    ) -> dict:
        """Send via SMTP."""
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        # Add text part
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Add HTML part if provided
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            delivery_result = {
                "status": "sent",
                "provider": "smtp",
                "to_email": to_email,
                "pin": pin,
                "subject": subject,
                "sent_at": datetime.now(EAT).isoformat(),
            }
        except Exception as e:
            delivery_result = {
                "status": "failed",
                "provider": "smtp",
                "to_email": to_email,
                "pin": pin,
                "error": str(e),
                "sent_at": datetime.now(EAT).isoformat(),
            }

        self._log_delivery(delivery_result, subject, body_text)
        return delivery_result

    def _dry_run(self, to_email: str, subject: str, body_text: str, pin: str) -> dict:
        """Log the email instead of sending it."""
        result = {
            "status": "dry_run",
            "provider": "none",
            "to_email": to_email,
            "pin": pin,
            "subject": subject,
            "body_length": len(body_text),
            "sent_at": datetime.now(EAT).isoformat(),
        }
        self._log_delivery(result, subject, body_text)
        return result

    def _log_delivery(self, result: dict, subject: str, body_text: str):
        """Log delivery to file."""
        log_entry = {
            "channel": "email",
            "to_email": result.get("to_email"),
            "pin": result.get("pin"),
            "subject": subject,
            "body_preview": body_text[:200],
            "result": result,
        }
        log_path = self._log_dir / "sent_messages.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    @property
    def is_configured(self) -> bool:
        """Check if email is configured."""
        return self.provider != "dry_run" and bool(self.smtp_user)
