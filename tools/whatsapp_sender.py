"""
WHATSAPP SENDER — sends WhatsApp messages via provider API.
Supports Africa's Talking, Twilio, or direct WhatsApp Business API.
Currently in DRY RUN mode — logs messages instead of sending.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .phone_utils import normalize_phone

EAT = timezone(timedelta(hours=3))
ROOT = Path(__file__).parent.parent


class WhatsAppSender:
    """Send WhatsApp messages. Dry-run by default until provider is configured."""

    def __init__(self):
        self.provider = os.getenv("HELMET_WA_PROVIDER", "dry_run")  # dry_run | africastalking | twilio
        self.api_key = os.getenv("HELMET_WA_API_KEY", "")
        self.sender_id = os.getenv("HELMET_WA_SENDER", "KRA Helmet")
        self._log_dir = ROOT / "logs"
        self._log_dir.mkdir(exist_ok=True)

    def send(self, phone: str, message: str, pin: str = "") -> dict:
        """Send a WhatsApp message. Returns delivery result."""
        phone = self._normalize_phone(phone)

        if self.provider == "dry_run" or not self.api_key:
            return self._dry_run(phone, message, pin)

        # Future: plug in real provider here
        # if self.provider == "africastalking":
        #     return self._send_africastalking(phone, message)
        # if self.provider == "twilio":
        #     return self._send_twilio(phone, message)

        return self._dry_run(phone, message, pin)

    def _dry_run(self, phone: str, message: str, pin: str) -> dict:
        """Log the message instead of sending it."""
        result = {
            "status": "dry_run",
            "provider": "none",
            "phone": phone,
            "pin": pin,
            "message_length": len(message),
            "sent_at": datetime.now(EAT).isoformat(),
            "message_preview": message[:100],
        }

        # Log to file
        log_entry = {
            "channel": "whatsapp",
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
