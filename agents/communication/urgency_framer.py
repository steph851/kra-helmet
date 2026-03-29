"""
URGENCY FRAMER — wraps messages in urgency context.
BOUNDARY: frames urgency only. Never changes deadlines.
"""
from ..base import BaseAgent


class UrgencyFramer(BaseAgent):
    name = "urgency_framer"
    boundary = "Frames urgency only. Never changes deadlines."

    def frame(self, obligations: list[dict]) -> dict:
        """Determine overall urgency and return framing metadata."""
        alert_rules = self.load_config("alert_rules.json")
        levels = alert_rules.get("urgency_levels", {})

        overdue = [o for o in obligations if o.get("days_until_deadline", 999) < 0]
        critical = [o for o in obligations if o.get("days_until_deadline", 999) == 0]
        urgent = [o for o in obligations if 0 < o.get("days_until_deadline", 999) <= 3]
        due_soon = [o for o in obligations if 3 < o.get("days_until_deadline", 999) <= 7]

        if overdue:
            level = "black"
            emoji = "🚨"
            prefix = "OVERDUE"
            action = "alert_immediately"
        elif critical:
            level = "red"
            emoji = "🔴"
            prefix = "FILE TODAY"
            action = "alert_immediately"
        elif urgent:
            level = "orange"
            emoji = "🟠"
            prefix = "URGENT"
            action = "alert_daily"
        elif due_soon:
            level = "yellow"
            emoji = "🟡"
            prefix = "DUE SOON"
            action = "alert_once"
        else:
            level = "green"
            emoji = "🟢"
            prefix = "ON TRACK"
            action = "no_alert"

        return {
            "urgency_level": level,
            "emoji": emoji,
            "prefix": prefix,
            "action": action,
            "overdue_count": len(overdue),
            "critical_count": len(critical),
            "urgent_count": len(urgent),
            "should_alert": action != "no_alert",
        }
