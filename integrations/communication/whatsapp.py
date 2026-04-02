"""
WHATSAPP SENDER — sends WhatsApp messages via provider API.
BOUNDARY: Delivers pre-formatted messages only. Never decides content or urgency.
Supports: WhatsApp Business API, Twilio, or dry-run mode.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

EAT = timezone(timedelta(hours=3))


class WhatsAppSender:
    """Send WhatsApp messages via configured provider."""

    def __init__(self):
        self.provider = os.getenv("WHATSAPP_PROVIDER", "dry_run")  # dry_run | whatsapp_business | twilio
        self.api_key = os.getenv("WHATSAPP_API_KEY", "")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self._log_dir = Path(__file__).parent.parent.parent / "logs"
        self._log_dir.mkdir(exist_ok=True)

    def send(self, phone: str, message: str, pin: str = "") -> dict:
        """Send a WhatsApp message. Returns delivery result."""
        phone = self._normalize_phone(phone)

        if self.provider == "dry_run" or not self.api_key:
            return self._dry_run(phone, message, pin)

        if self.provider == "whatsapp_business":
            return self._send_whatsapp_business(phone, message, pin)
        elif self.provider == "twilio":
            return self._send_twilio(phone, message, pin)

        return self._dry_run(phone, message, pin)

    def _send_whatsapp_business(self, phone: str, message: str, pin: str) -> dict:
        """Send via WhatsApp Business API."""
        import requests

        url = f"https://graph.facebook.com/v17.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message},
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            delivery_result = {
                "status": "sent",
                "provider": "whatsapp_business",
                "phone": phone,
                "pin": pin,
                "message_id": result.get("messages", [{}])[0].get("id"),
                "sent_at": datetime.now(EAT).isoformat(),
            }
        except Exception as e:
            delivery_result = {
                "status": "failed",
                "provider": "whatsapp_business",
                "phone": phone,
                "pin": pin,
                "error": str(e),
                "sent_at": datetime.now(EAT).isoformat(),
            }

        self._log_delivery(delivery_result, message)
        return delivery_result

    def _send_twilio(self, phone: str, message: str, pin: str) -> dict:
        """Send via Twilio WhatsApp API."""
        import requests
        from base64 import b64encode

        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        from_number = os.getenv("TWILIO_WHATSAPP_FROM", "")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        auth = b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "From": f"whatsapp:{from_number}",
            "To": f"whatsapp:{phone}",
            "Body": message,
        }

        try:
            response = requests.post(url, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()

            delivery_result = {
                "status": "sent",
                "provider": "twilio",
                "phone": phone,
                "pin": pin,
                "message_id": result.get("sid"),
                "sent_at": datetime.now(EAT).isoformat(),
            }
        except Exception as e:
            delivery_result = {
                "status": "failed",
                "provider": "twilio",
                "phone": phone,
                "pin": pin,
                "error": str(e),
                "sent_at": datetime.now(EAT).isoformat(),
            }

        self._log_delivery(delivery_result, message)
        return delivery_result

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
        self._log_delivery(result, message)
        return result

    def _normalize_phone(self, phone: str) -> str:
        """Normalize Kenya phone to +254 format."""
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith("0"):
            phone = "+254" + phone[1:]
        elif phone.startswith("254") and not phone.startswith("+"):
            phone = "+" + phone
        return phone

    def _log_delivery(self, result: dict, message: str):
        """Log delivery to file."""
        log_entry = {
            "channel": "whatsapp",
            "phone": result.get("phone"),
            "pin": result.get("pin"),
            "message": message,
            "result": result,
        }
        log_path = self._log_dir / "sent_messages.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    @property
    def is_configured(self) -> bool:
        """Check if WhatsApp is configured."""
        return self.provider != "dry_run" and bool(self.api_key)
