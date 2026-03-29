"""
COMPLIANCE CHECKER — compares what SME should file vs what's on record.
BOUNDARY: checks compliance only. Never sends alerts.
"""
from datetime import datetime
from ..base import BaseAgent


class ComplianceChecker(BaseAgent):
    name = "compliance_checker"
    boundary = "Checks compliance only. Never sends alerts."

    def check(self, profile: dict, obligations: list[dict]) -> dict:
        """Generate compliance status for an SME."""
        self.log(f"Checking compliance for {profile['pin']}")

        total = len(obligations)
        overdue = [o for o in obligations if o.get("status") == "overdue"]
        critical = [o for o in obligations if o.get("status") == "critical"]
        due_soon = [o for o in obligations if o.get("status") == "due_soon"]
        upcoming = [o for o in obligations if o.get("status") == "upcoming"]
        filed = [o for o in obligations if o.get("status") == "filed"]

        overdue_count = len(overdue)
        met = len(filed) + len(upcoming)

        if overdue_count > 0:
            overall = "non_compliant"
        elif len(critical) > 0 or len(due_soon) > 0:
            overall = "at_risk"
        else:
            overall = "compliant"

        # Build next action
        if overdue:
            next_action = f"URGENT: File {overdue[0]['tax_name']} immediately — penalties are accruing."
        elif critical:
            next_action = f"File {critical[0]['tax_name']} TODAY — deadline is tomorrow."
        elif due_soon:
            next_action = f"File {due_soon[0]['tax_name']} within {due_soon[0].get('days_until_deadline', '?')} days."
        else:
            next_action = "All obligations on track. Next filing is upcoming."

        result = {
            "overall": overall,
            "obligations_met": met,
            "obligations_total": total,
            "overdue_count": overdue_count,
            "overdue_list": [{"tax": o["tax_name"], "deadline": o.get("next_deadline")} for o in overdue],
            "critical_list": [{"tax": o["tax_name"], "deadline": o.get("next_deadline")} for o in critical],
            "next_action": next_action,
            "checked_at": datetime.now().isoformat(),
            "disclaimer": (
                "This is an automated compliance check based on available data. "
                "It is NOT legal or tax advice. Always consult a registered tax "
                "advisor or KRA directly for official compliance status."
            ),
        }

        self.log(f"Compliance: {overall} — {overdue_count} overdue, {total} total obligations")
        return result
