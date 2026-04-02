"""
ALERT ENGINE — the mouth. Sends messages through configured channels.
BOUNDARY: Delivers messages only. Never decides content or urgency — receives pre-formatted messages
from the notification_engine and sends them through the appropriate tool.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..base import BaseAgent

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.whatsapp_sender import WhatsAppSender
from tools.sms_sender import SMSSender
from workflow.audit_trail import AuditTrail

EAT = timezone(timedelta(hours=3))


class AlertEngine(BaseAgent):
    name = "alert_engine"
    boundary = "Delivers pre-formatted messages only. Never decides content or urgency."

    def __init__(self):
        super().__init__()
        self.whatsapp = WhatsAppSender()
        self.sms = SMSSender()
        self.audit = AuditTrail()

    def deliver_alert(self, alert: dict) -> dict:
        """Deliver a single alert through the specified channel. Returns delivery result."""
        channel = alert.get("channel", "sms")
        pin = alert.get("sme_pin", "")
        message = alert.get("message", "")
        phone = alert.get("phone", "")

        if not message:
            return {"status": "skipped", "reason": "empty_message"}
        if not phone:
            return {"status": "skipped", "reason": "no_phone"}

        if channel == "whatsapp":
            result = self.whatsapp.send(phone, message, pin)
        elif channel == "email":
            result = self._send_email(alert)
        else:
            result = self.sms.send(phone, message, pin)

        # Audit the delivery
        self.audit.record("ALERT_DELIVERED", self.name, {
            "pin": pin,
            "channel": channel,
            "status": result.get("status", "unknown"),
            "message_length": len(message),
        }, sme_pin=pin)

        return result

    def deliver_batch(self, alerts: list[dict]) -> list[dict]:
        """Deliver multiple alerts. Returns list of delivery results."""
        results = []
        for alert in alerts:
            result = self.safe_run(
                lambda a=alert: self.deliver_alert(a),
                context=f"deliver_{alert.get('sme_pin', '?')}",
                fallback={"status": "failed", "error": "delivery_error"},
            )
            results.append(result)
        return results

    def process_queue(self) -> list[dict]:
        """Process all pending alerts from staging/alerts/. Returns delivery results."""
        alerts_dir = self.staging / "alerts"
        if not alerts_dir.exists():
            return []

        results = []
        now = datetime.now(EAT)

        for alert_file in sorted(alerts_dir.glob("*.json")):
            try:
                alert = json.loads(alert_file.read_text(encoding="utf-8"))

                # Check if scheduled time has arrived
                scheduled = alert.get("scheduled_at", "")
                if scheduled:
                    try:
                        sched_dt = datetime.fromisoformat(scheduled)
                        if sched_dt.tzinfo is None:
                            sched_dt = sched_dt.replace(tzinfo=EAT)
                        if sched_dt > now:
                            continue  # not yet time
                    except (ValueError, TypeError):
                        pass

                # Look up phone from SME profile
                if not alert.get("phone"):
                    profile = self.load_sme(alert.get("sme_pin", ""))
                    if profile:
                        alert["phone"] = profile.get("phone", "")

                result = self.deliver_alert(alert)
                result["alert_file"] = alert_file.name

                # Mark as delivered by moving to processed
                delivered_dir = self.staging / "alerts" / "delivered"
                delivered_dir.mkdir(exist_ok=True)
                alert["_delivered_at"] = now.isoformat()
                alert["_delivery_result"] = result.get("status", "unknown")
                (delivered_dir / alert_file.name).write_text(
                    json.dumps(alert, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                alert_file.unlink()

                results.append(result)

            except (json.JSONDecodeError, OSError) as e:
                self.log(f"Failed to process {alert_file.name}: {e}", "ERROR")

        if results:
            self.log(f"Delivered {len(results)} alert(s)")
        return results

    def _send_email(self, alert: dict) -> dict:
        """Email delivery — logs to file (no SMTP configured yet)."""
        result = {
            "status": "dry_run",
            "channel": "email",
            "pin": alert.get("sme_pin", ""),
            "sent_at": datetime.now(EAT).isoformat(),
            "note": "Email delivery not yet configured — message logged",
        }

        log_entry = {"channel": "email", "alert": alert, "result": result}
        log_path = self.logs_dir / "sent_messages.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return result

    def status(self) -> dict:
        """Alert engine status."""
        alerts_dir = self.staging / "alerts"
        pending = 0
        delivered = 0

        if alerts_dir.exists():
            pending = len(list(alerts_dir.glob("*.json")))
            delivered_dir = alerts_dir / "delivered"
            if delivered_dir.exists():
                delivered = len(list(delivered_dir.glob("*.json")))

        return {
            "pending_alerts": pending,
            "delivered_alerts": delivered,
            "whatsapp_configured": self.whatsapp.is_configured,
            "sms_configured": self.sms.is_configured,
        }
