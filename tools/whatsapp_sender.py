"""
WHATSAPP SENDER — sends WhatsApp messages via local bot or provider API.
Priority: local bot (whatsapp-web.js) > provider API > dry run.
"""
import json
import os
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .phone_utils import normalize_phone

EAT = timezone(timedelta(hours=3))
ROOT = Path(__file__).parent.parent
log = logging.getLogger("whatsapp_sender")


class WhatsAppSender:
    """Send WhatsApp messages. Uses local bot if running, falls back to dry-run."""

    def __init__(self):
        self.bot_url = os.getenv("HELMET_BOT_URL", "http://localhost:3001")
        self.provider = os.getenv("HELMET_WA_PROVIDER", "dry_run")  # bot | meta | dry_run
        self.whatsapp_token = os.getenv("WHATSAPP_TOKEN")  # Meta Cloud API token
        self.whatsapp_phone_id = os.getenv("WHATSAPP_PHONE_ID")  # Meta Cloud API phone ID
        self._log_dir = ROOT / "logs"
        self._log_dir.mkdir(exist_ok=True)

    def send(self, phone: str, message: str, pin: str = "") -> dict:
        """Send a WhatsApp message. Tries bot/meta, falls back to dry-run."""
        phone = self._normalize_phone(phone)

        # Try local bot
        if self.provider == "bot":
            result = self._send_via_bot(phone, message, pin)
            if result.get("success"):
                return result
            log.warning(f"Bot failed for {pin}: {result.get('error')} — trying meta")

        # Try Meta WhatsApp Cloud API (free tier)
        if self.provider in ("bot", "meta") and self.whatsapp_token:
            result = self._send_via_meta(phone, message, pin)
            if result.get("success"):
                return result
            log.warning(f"Meta send failed: {result.get('error')} — falling back to dry-run")

        return self._dry_run(phone, message, pin)

    def send_bulk(self, messages: list[dict]) -> dict:
        """Send multiple messages. Each item: {phone, message, pin}."""
        if self.provider == "dry_run":
            results = []
            for m in messages:
                r = self._dry_run(
                    self._normalize_phone(m["phone"]), m["message"], m.get("pin", "")
                )
                results.append(r)
            return {"total": len(messages), "sent": 0, "results": results}

        # Try bulk endpoint on bot
        try:
            import urllib.request
            payload = json.dumps({
                "messages": [
                    {"phone": m["phone"], "message": m["message"]}
                    for m in messages
                ]
            }).encode()
            req = urllib.request.Request(
                f"{self.bot_url}/send-bulk",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                self._log_bulk(messages, result)
                return result
        except Exception as e:
            log.warning(f"Bot bulk send failed: {e}")
            results = []
            for m in messages:
                r = self._dry_run(
                    self._normalize_phone(m["phone"]), m["message"], m.get("pin", "")
                )
                results.append(r)
            return {"total": len(messages), "sent": 0, "results": results}

    def _send_via_bot(self, phone: str, message: str, pin: str) -> dict:
        """Send via the local whatsapp-web.js bot HTTP API."""
        try:
            import urllib.request
            payload = json.dumps({"phone": phone, "message": message}).encode()
            req = urllib.request.Request(
                f"{self.bot_url}/send",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())

            result["provider"] = "whatsapp_bot"
            result["pin"] = pin
            self._log_message(phone, message, pin, result)
            log.info(f"WhatsApp sent to {phone} for {pin}")
            return result

        except Exception as e:
            return {"success": False, "error": str(e), "provider": "whatsapp_bot"}

    def bot_status(self) -> dict:
        """Check if the bot is running and connected."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.bot_url}/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception:
            return {"connected": False, "error": "Bot not reachable"}

    def _send_via_meta(self, phone: str, message: str, pin: str) -> dict:
        """Send via Meta WhatsApp Cloud API (free tier)."""
        if not self.whatsapp_token or not self.whatsapp_phone_id:
            return {"success": False, "error": "Missing WHATSAPP_TOKEN or WHATSAPP_PHONE_ID"}

        url = f"https://graph.facebook.com/v21.0/{self.whatsapp_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.whatsapp_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message},
        }

        try:
            import urllib.request
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())

            result["provider"] = "meta"
            result["pin"] = pin
            self._log_message(phone, message, pin, result)
            log.info(f"WhatsApp sent via Meta to {phone} for {pin}")
            return {"success": True, "provider": "meta", "message_id": result.get("messages", [{}])[0].get("id")}
        except Exception as e:
            return {"success": False, "error": str(e), "provider": "meta"}

    def _dry_run(self, phone: str, message: str, pin: str) -> dict:
        """Log the message instead of sending it."""
        result = {
            "success": False,
            "status": "dry_run",
            "provider": "none",
            "phone": phone,
            "pin": pin,
            "message_length": len(message),
            "sent_at": datetime.now(EAT).isoformat(),
            "message_preview": message[:100],
        }
        self._log_message(phone, message, pin, result)
        return result

    def _log_message(self, phone: str, message: str, pin: str, result: dict):
        log_entry = {
            "channel": "whatsapp",
            "phone": phone,
            "pin": pin,
            "message": message,
            "result": result,
            "timestamp": datetime.now(EAT).isoformat(),
        }
        log_path = self._log_dir / "sent_messages.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _log_bulk(self, messages: list, result: dict):
        log_entry = {
            "channel": "whatsapp",
            "type": "bulk",
            "count": len(messages),
            "result_summary": {
                "sent": result.get("sent", 0),
                "failed": result.get("failed", 0),
            },
            "timestamp": datetime.now(EAT).isoformat(),
        }
        log_path = self._log_dir / "sent_messages.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _normalize_phone(self, phone: str) -> str:
        return normalize_phone(phone)

    @property
    def is_configured(self) -> bool:
        status = self.bot_status()
        return status.get("connected", False)
