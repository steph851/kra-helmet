"""
SMS SENDER — sends SMS via Africa's Talking or Twilio.
Currently in DRY RUN mode — logs messages instead of sending.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .phone_utils import normalize_phone

EAT = timezone(timedelta(hours=3))
ROOT = Path(__file__).parent.parent


class SMSSender:
    """Send SMS messages. Dry-run by default until provider is configured."""

    def __init__(self):
        self.provider = os.getenv("HELMET_SMS_PROVIDER", "dry_run")  # dry_run | africastalking | twilio
        self.api_key = os.getenv("HELMET_SMS_API_KEY", "")
        self.sender_id = os.getenv("HELMET_SMS_SENDER", "KRA_HELMET")
        self._log_dir = ROOT / "logs"
        self._log_dir.mkdir(exist_ok=True)

    def send(self, phone: str, message: str, pin: str = "") -> dict:
        """Send an SMS. Hard-truncates to 160 chars. Returns delivery result."""
        phone = self._normalize_phone(phone)

        # Hard SMS limit
        if len(message) > 160:
            message = message[:157] + "..."

        if self.provider == "dry_run" or not self.api_key:
            return self._dry_run(phone, message, pin)

        return self._dry_run(phone, message, pin)

    def _dry_run(self, phone: str, message: str, pin: str) -> dict:
        result = {
            "status": "dry_run",
            "provider": "none",
            "phone": phone,
            "pin": pin,
            "message_length": len(message),
            "sent_at": datetime.now(EAT).isoformat(),
            "message_preview": message[:100],
        }

        log_entry = {
            "channel": "sms",
            "phone": phone,
            "pin": pin,
            "message": message,
            "result": result,
        }
        log_path = self._log_dir / "sent_messages.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return result

    def _normalize_phone(self, phone: str) -> str:
        """Normalize Kenya phone to +254 format."""
        return normalize_phone(phone)

    @property
    def is_configured(self) -> bool:
        return self.provider != "dry_run" and bool(self.api_key)
