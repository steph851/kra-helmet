"""
ESCALATION ENGINE — missed deadlines get routed to human gate.
BOUNDARY: Creates escalation items in staging/review. Never takes action itself.
Escalation tiers:
  1. SME notification (already handled by alert_engine)
  2. Human review item → staging/review/
  3. Critical flag on dashboard
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..base import BaseAgent

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from workflow.audit_trail import AuditTrail

EAT = timezone(timedelta(hours=3))

# Escalation thresholds
ESCALATION_RULES = {
    "overdue_days_tier1": 1,     # 1+ days overdue → alert SME (alert_engine handles)
    "overdue_days_tier2": 7,     # 7+ days → human review
    "overdue_days_tier3": 30,    # 30+ days → critical escalation
    "penalty_threshold_kes": 50000,  # >50K penalty → immediate escalation
    "missed_alerts_threshold": 3,     # 3 missed alerts → escalate
}


class EscalationEngine(BaseAgent):
    name = "escalation_engine"
    boundary = "Creates escalation items for review. Never takes action directly."

    def __init__(self):
        super().__init__()
        self.audit = AuditTrail()

    def evaluate(self, pin: str, compliance: dict, obligations: list[dict],
                 penalties: dict, urgency: dict) -> list[dict]:
        """Evaluate an SME's compliance state and create escalations as needed."""
        escalations = []

        # Tier 2: Overdue obligations needing human review
        for ob in obligations:
            days = ob.get("days_until_deadline")
            if days is not None and days < 0:
                overdue_days = abs(days)
                tax_name = ob.get("tax_name", "Unknown")

                if overdue_days >= ESCALATION_RULES["overdue_days_tier3"]:
                    escalations.append(self._create_escalation(
                        pin=pin,
                        tier="critical",
                        reason=f"{tax_name} overdue by {overdue_days} days — CRITICAL",
                        tax_type=ob.get("tax_key", ""),
                        overdue_days=overdue_days,
                        obligation=ob,
                    ))
                elif overdue_days >= ESCALATION_RULES["overdue_days_tier2"]:
                    escalations.append(self._create_escalation(
                        pin=pin,
                        tier="review",
                        reason=f"{tax_name} overdue by {overdue_days} days — needs review",
                        tax_type=ob.get("tax_key", ""),
                        overdue_days=overdue_days,
                        obligation=ob,
                    ))

        # Penalty threshold escalation
        total_penalty = penalties.get("total_penalty_exposure_kes", 0)
        if total_penalty >= ESCALATION_RULES["penalty_threshold_kes"]:
            severity = penalties.get("severity", "unknown")
            escalations.append(self._create_escalation(
                pin=pin,
                tier="critical" if total_penalty >= 200000 else "review",
                reason=f"Penalty exposure KES {total_penalty:,.0f} ({severity})",
                penalty_kes=total_penalty,
            ))

        # Route to human gate
        for esc in escalations:
            self._route_to_review(esc)

        if escalations:
            self.audit.record("ESCALATION", self.name, {
                "pin": pin,
                "escalation_count": len(escalations),
                "tiers": [e["tier"] for e in escalations],
            }, sme_pin=pin)
            self.log(f"Created {len(escalations)} escalation(s) for {pin}")

        return escalations

    def evaluate_all(self) -> list[dict]:
        """Evaluate all SMEs and create escalations. Returns all escalation items."""
        all_escalations = []
        smes = self.list_smes()

        for sme in smes:
            if not sme.get("active", True):
                continue

            pin = sme["pin"]
            report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
            if not report_path.exists():
                continue

            try:
                report = self.load_json(report_path)
                escalations = self.evaluate(
                    pin=pin,
                    compliance=report.get("compliance", {}),
                    obligations=report.get("obligations", []),
                    penalties=report.get("penalties", {}),
                    urgency=report.get("urgency", {}),
                )
                all_escalations.extend(escalations)
            except Exception as e:
                self.log(f"Escalation eval failed for {pin}: {e}", "ERROR")

        return all_escalations

    def _create_escalation(self, pin: str, tier: str, reason: str, **kwargs) -> dict:
        return {
            "type": "escalation",
            "pin": pin,
            "tier": tier,
            "reason": reason,
            "created_at": datetime.now(EAT).isoformat(),
            "status": "pending_review",
            **kwargs,
        }

    def _route_to_review(self, escalation: dict):
        """Write escalation to staging/review for human gate."""
        review_item = {
            "type": f"escalation_{escalation['tier']}",
            "pin": escalation["pin"],
            "reason": escalation["reason"],
            "tier": escalation["tier"],
            "created_at": escalation["created_at"],
            "status": "pending_review",
            "action_needed": self._action_for_tier(escalation["tier"]),
        }

        # Include extra context
        for key in ("tax_type", "overdue_days", "penalty_kes", "obligation"):
            if key in escalation:
                review_item[key] = escalation[key]

        ts = datetime.now(EAT).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"escalation_{escalation['pin']}_{ts}.json"
        self.write_staging("review", filename, review_item)

    def _action_for_tier(self, tier: str) -> str:
        if tier == "critical":
            return "URGENT: Contact SME immediately. Consider professional tax advisor referral."
        return "Review SME compliance status and advise on next steps."

    def get_pending_escalations(self) -> list[dict]:
        """Get all pending escalation items from staging/review."""
        review_dir = self.staging / "review"
        if not review_dir.exists():
            return []

        escalations = []
        for f in sorted(review_dir.glob("escalation_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data["_filename"] = f.name
                escalations.append(data)
            except (json.JSONDecodeError, OSError):
                continue

        return escalations
