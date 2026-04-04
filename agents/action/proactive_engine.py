"""
PROACTIVE ENGINE — anticipates needs and makes autonomous recommendations.
BOUNDARY: Makes low-risk decisions autonomously. Routes critical decisions to human gate.
This agent transforms KRA Deadline Tracker from reactive to proactive by:
  - Anticipating SME needs based on patterns
  - Making autonomous recommendations for low-risk actions
  - Providing contextual reasoning for suggestions
  - Learning from outcomes to improve future recommendations
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..base import BaseAgent
from ..learning.pattern_miner import PatternMiner
from ..learning.memory import DecisionMemory

EAT = timezone(timedelta(hours=3))


class ProactiveEngine(BaseAgent):
    """Proactive recommendation engine that anticipates SME needs."""

    name = "proactive_engine"
    boundary = "Makes low-risk recommendations autonomously. Routes critical decisions to human gate."

    # Low-risk actions that can be decided autonomously
    AUTONOMOUS_ACTIONS = {
        "send_reminder",
        "suggest_filing_early",
        "recommend_etims_registration",
        "suggest_document_preparation",
        "recommend_payment_method",
    }

    # Critical actions that require human gate
    CRITICAL_ACTIONS = {
        "model_update",
        "escalation",
        "penalty_calculation",
        "compliance_override",
        "data_modification",
    }

    def __init__(self):
        super().__init__()
        self.miner = PatternMiner()
        self.memory = DecisionMemory()

    def analyze_and_recommend(self, pin: str) -> dict:
        """Analyze an SME and provide proactive recommendations.

        This is the main entry point for proactive behavior.
        It anticipates needs rather than just reacting to triggers.
        """
        profile = self.load_sme(pin)
        if not profile:
            return {"pin": pin, "error": "SME not found", "recommendations": []}

        # Load latest compliance report
        report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
        if not report_path.exists():
            return {
                "pin": pin,
                "name": profile.get("name", ""),
                "recommendations": [],
                "message": "No compliance data yet. Run a check first.",
            }

        report = self.load_json(report_path)
        recommendations = []

        # 1. Anticipate deadline pressure
        recommendations.extend(self._anticipate_deadline_pressure(profile, report))

        # 2. Predict risk trajectory
        recommendations.extend(self._predict_risk_trajectory(pin, profile, report))

        # 3. Suggest proactive measures
        recommendations.extend(self._suggest_proactive_measures(profile, report))

        # 4. Identify optimization opportunities
        recommendations.extend(self._identify_optimizations(profile, report))

        # Sort by priority and remove duplicates
        recommendations = self._deduplicate_and_sort(recommendations)

        return {
            "pin": pin,
            "name": profile.get("name", ""),
            "compliance_status": report.get("compliance", {}).get("overall", "unknown"),
            "risk_score": report.get("risk", {}).get("risk_score", 0),
            "recommendations": recommendations,
            "autonomous_count": sum(1 for r in recommendations if r.get("autonomous", False)),
            "requires_human_count": sum(1 for r in recommendations if not r.get("autonomous", False)),
            "generated_at": datetime.now(EAT).isoformat(),
        }

    def _anticipate_deadline_pressure(self, profile: dict, report: dict) -> list[dict]:
        """Anticipate upcoming deadline pressure and suggest early filing."""
        recs = []
        obligations = report.get("obligations", [])

        for ob in obligations:
            days = ob.get("days_until_deadline")
            if days is None:
                continue

            # Suggest early filing if deadline is approaching
            if 7 <= days <= 14:
                recs.append({
                    "type": "proactive_reminder",
                    "action": "suggest_filing_early",
                    "title": f"Consider filing {ob.get('tax_name', 'tax')} early",
                    "detail": f"Deadline is {days} days away. Filing early avoids last-minute stress and potential iTax issues.",
                    "urgency": "yellow",
                    "autonomous": True,
                    "reasoning": "Based on deadline proximity and historical filing patterns",
                })
            elif 3 <= days <= 6:
                recs.append({
                    "type": "urgent_reminder",
                    "action": "send_reminder",
                    "title": f"File {ob.get('tax_name', 'tax')} within {days} days",
                    "detail": "Don't wait until the last day — iTax can be slow near deadlines.",
                    "urgency": "orange",
                    "autonomous": True,
                    "reasoning": "Deadline approaching, proactive reminder to avoid last-minute issues",
                })

        return recs

    def _predict_risk_trajectory(self, pin: str, profile: dict, report: dict) -> list[dict]:
        """Predict where risk is heading and suggest interventions."""
        recs = []
        risk = report.get("risk", {})
        risk_score = risk.get("risk_score", 0)

        # Check historical risk changes
        risk_changes = self.memory.get_by_type("risk_change")
        pin_changes = [c for c in risk_changes if c.get("pin") == pin]

        if pin_changes:
            latest = pin_changes[-1]
            delta = latest.get("context", {}).get("delta", 0)

            if delta > 10:
                recs.append({
                    "type": "risk_intervention",
                    "action": "suggest_document_preparation",
                    "title": "Risk score increasing — prepare documents now",
                    "detail": f"Risk score increased by {delta} points. Gather your records before the next filing deadline.",
                    "urgency": "orange",
                    "autonomous": True,
                    "reasoning": "Risk trajectory analysis shows upward trend",
                })

        # High risk score intervention
        if risk_score >= 60:
            recs.append({
                "type": "risk_mitigation",
                "action": "recommend_etims_registration",
                "title": "High risk score — consider eTIMS registration",
                "detail": "eTIMS compliance significantly reduces audit risk. Register at your nearest KRA office.",
                "urgency": "yellow",
                "autonomous": True,
                "reasoning": "High risk score correlates with eTIMS non-compliance",
            })

        return recs

    def _suggest_proactive_measures(self, profile: dict, report: dict) -> list[dict]:
        """Suggest proactive measures based on profile analysis."""
        recs = []

        # Check for missing eTIMS
        if not profile.get("has_etims") and profile.get("is_vat_registered"):
            recs.append({
                "type": "proactive_compliance",
                "action": "recommend_etims_registration",
                "title": "Register for eTIMS before KRA enforcement",
                "detail": "VAT-registered businesses must use eTIMS. Register now to avoid penalties.",
                "urgency": "yellow",
                "autonomous": True,
                "reasoning": "VAT registration without eTIMS is a compliance risk",
            })

        # Check for high turnover without proper tax regime
        turnover = profile.get("annual_turnover_kes", 0)
        if turnover > 8_000_000 and not profile.get("is_vat_registered"):
            recs.append({
                "type": "regime_optimization",
                "action": "suggest_filing_early",
                "title": "Consider VAT registration",
                "detail": f"Turnover KES {turnover:,.0f} exceeds TOT threshold. VAT registration may be beneficial.",
                "urgency": "green",
                "autonomous": True,
                "reasoning": "High turnover may benefit from VAT input credit claims",
            })

        return recs

    def _identify_optimizations(self, profile: dict, report: dict) -> list[dict]:
        """Identify optimization opportunities."""
        recs = []

        # Check for employees without PAYE optimization
        if profile.get("has_employees") and profile.get("employee_count", 0) > 5:
            recs.append({
                "type": "optimization",
                "action": "recommend_payment_method",
                "title": "Optimize PAYE filing process",
                "detail": "With multiple employees, consider using payroll software to automate PAYE calculations.",
                "urgency": "green",
                "autonomous": True,
                "reasoning": "Multiple employees increase PAYE complexity and error risk",
            })

        return recs

    def _deduplicate_and_sort(self, recommendations: list[dict]) -> list[dict]:
        """Remove duplicates and sort by urgency."""
        seen = set()
        unique = []

        for rec in recommendations:
            key = (rec.get("action"), rec.get("title"))
            if key not in seen:
                seen.add(key)
                unique.append(rec)

        # Sort by urgency
        urgency_order = {"red": 0, "orange": 1, "yellow": 2, "green": 3}
        unique.sort(key=lambda r: urgency_order.get(r.get("urgency", "green"), 3))

        return unique

    def execute_autonomous_action(self, action: str, pin: str, context: dict) -> dict:
        """Execute an autonomous action (low-risk only)."""
        if action not in self.AUTONOMOUS_ACTIONS:
            return {
                "status": "rejected",
                "reason": f"Action '{action}' requires human approval",
                "action": action,
                "pin": pin,
            }

        # Log the autonomous decision
        self.log_decision(
            f"autonomous_{action}",
            f"Executed {action} for {pin} without human gate",
            pin=pin,
            autonomous=True,
            context=context,
        )

        return {
            "status": "executed",
            "action": action,
            "pin": pin,
            "autonomous": True,
            "timestamp": datetime.now(EAT).isoformat(),
        }

    def print_recommendations(self, pin: str):
        """Print proactive recommendations for an SME."""
        result = self.analyze_and_recommend(pin)

        print(f"\n{'='*65}")
        print(f"  PROACTIVE RECOMMENDATIONS — {result.get('name', pin)}")
        print(f"  Status: {result.get('compliance_status', '?')} | Risk: {result.get('risk_score', '?')}/100")
        print(f"{'='*65}")

        if not result["recommendations"]:
            print("\n  No proactive recommendations at this time.\n")
            return

        for i, rec in enumerate(result["recommendations"], 1):
            auto = "🤖" if rec.get("autonomous") else "👤"
            print(f"\n  {i}. [{auto}] {rec['title']}")
            print(f"     {rec['detail']}")
            print(f"     Reasoning: {rec.get('reasoning', 'N/A')}")

        print(f"\n  Autonomous: {result['autonomous_count']} | Requires Human: {result['requires_human_count']}")
        print()
