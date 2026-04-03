"""
RECOMMENDATION ENGINE — generates "do this now" action lists for SMEs.
BOUNDARY: Creates prioritized recommendations. Never executes actions.
Combines compliance, deadlines, penalties, and eTIMS status into a single
actionable list sorted by urgency.
"""
import json
from datetime import datetime, timedelta, timezone

from ..base import BaseAgent

import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.mpesa_caller import MpesaCaller
from tools.kra_shuru import KRAShuru

EAT = timezone(timedelta(hours=3))


class RecommendationEngine(BaseAgent):
    name = "recommendation_engine"
    boundary = "Creates recommendations only. Never executes actions."

    def __init__(self):
        super().__init__()
        self.mpesa = MpesaCaller()
        self.shuru = KRAShuru()

    def generate(self, pin: str) -> dict:
        """Generate a prioritized action list for an SME. Returns recommendations dict."""
        profile = self.load_sme(pin)
        if not profile:
            return {"pin": pin, "error": "SME not found", "recommendations": []}

        # Load latest compliance report
        report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
        if not report_path.exists():
            return {
                "pin": pin,
                "name": profile.get("name", ""),
                "recommendations": [{
                    "priority": 1,
                    "action": "run_compliance_check",
                    "title": "Run your first compliance check",
                    "detail": "No compliance data yet. Run: python run.py check " + pin,
                    "urgency": "yellow",
                }],
                "generated_at": datetime.now(EAT).isoformat(),
            }

        report = self.load_json(report_path)
        obligations = report.get("obligations", [])
        compliance = report.get("compliance", {})
        penalties = report.get("penalties", {})
        risk = report.get("risk", {})

        recommendations = []

        # 1. Overdue filings — highest priority
        recommendations.extend(self._overdue_recommendations(pin, profile, obligations))

        # 2. Due today / critical
        recommendations.extend(self._critical_recommendations(pin, profile, obligations))

        # 3. Due soon (within 7 days)
        recommendations.extend(self._upcoming_recommendations(pin, profile, obligations))

        # 4. eTIMS compliance
        recommendations.extend(self._etims_recommendations(pin, profile))

        # 5. KRA Shuru WhatsApp filing option
        recommendations.extend(self._shuru_recommendations(pin, profile, obligations))

        # 6. Payment instructions for overdue items
        recommendations.extend(self._payment_recommendations(pin, profile, obligations, penalties))

        # 7. Risk reduction
        recommendations.extend(self._risk_recommendations(pin, profile, risk))

        # Sort by priority (1 = most urgent)
        recommendations.sort(key=lambda r: r["priority"])

        # Number them
        for i, rec in enumerate(recommendations, 1):
            rec["order"] = i

        return {
            "pin": pin,
            "name": profile.get("name", ""),
            "compliance_status": compliance.get("overall", "unknown"),
            "risk_score": risk.get("risk_score", 0),
            "total_recommendations": len(recommendations),
            "recommendations": recommendations,
            "generated_at": datetime.now(EAT).isoformat(),
        }

    def _overdue_recommendations(self, pin: str, profile: dict, obligations: list) -> list:
        recs = []
        for ob in obligations:
            days = ob.get("days_until_deadline")
            if days is not None and days < 0:
                tax_name = ob.get("tax_name", "Tax")
                tax_key = ob.get("tax_key", "")
                deadline = ob.get("next_deadline", "?")
                overdue_days = abs(days)

                shuru_link = self.shuru.generate_filing_link(pin, tax_name)
                recs.append({
                    "priority": 1,
                    "action": "file_overdue",
                    "title": f"FILE NOW: {tax_name} is {overdue_days} day(s) overdue",
                    "detail": f"Deadline was {deadline}. Penalties are accruing daily. "
                              f"File on iTax or via KRA WhatsApp (Shuru) to stop penalty accumulation.",
                    "urgency": "red",
                    "tax_type": tax_key,
                    "overdue_days": overdue_days,
                    "itax_url": "https://itax.kra.go.ke",
                    "shuru_deeplink": shuru_link["deeplink"],
                })
        return recs

    def _critical_recommendations(self, pin: str, profile: dict, obligations: list) -> list:
        recs = []
        for ob in obligations:
            days = ob.get("days_until_deadline")
            if days is not None and days == 0:
                tax_name = ob.get("tax_name", "Tax")
                shuru_link = self.shuru.generate_filing_link(pin, tax_name)
                recs.append({
                    "priority": 2,
                    "action": "file_today",
                    "title": f"FILE TODAY: {tax_name} deadline is TODAY",
                    "detail": f"Last chance to file without penalties. "
                              f"Use iTax or KRA WhatsApp (Shuru) — just 3 steps.",
                    "urgency": "red",
                    "tax_type": ob.get("tax_key", ""),
                    "itax_url": "https://itax.kra.go.ke",
                    "shuru_deeplink": shuru_link["deeplink"],
                })
        return recs

    def _upcoming_recommendations(self, pin: str, profile: dict, obligations: list) -> list:
        recs = []
        for ob in obligations:
            days = ob.get("days_until_deadline")
            if days is not None and 0 < days <= 7:
                tax_name = ob.get("tax_name", "Tax")
                deadline = ob.get("next_deadline", "?")
                recs.append({
                    "priority": 3,
                    "action": "prepare_filing",
                    "title": f"PREPARE: {tax_name} due in {days} day(s)",
                    "detail": f"Deadline: {deadline}. Gather documents and file before the deadline.",
                    "urgency": "orange" if days <= 3 else "yellow",
                    "tax_type": ob.get("tax_key", ""),
                })
        return recs

    def _etims_recommendations(self, pin: str, profile: dict) -> list:
        recs = []
        is_vat = profile.get("is_vat_registered", False)
        has_etims = profile.get("has_etims", False)
        turnover = profile.get("annual_turnover_kes", 0)

        if is_vat and not has_etims:
            recs.append({
                "priority": 2,
                "action": "register_etims",
                "title": "REGISTER for eTIMS — mandatory for VAT taxpayers",
                "detail": "As a VAT-registered taxpayer, you must use eTIMS for all invoices. "
                          "Visit your nearest KRA office or apply online. "
                          "Penalty: KES 50 per missing invoice.",
                "urgency": "red",
            })
        elif turnover > 5_000_000 and not has_etims:
            recs.append({
                "priority": 4,
                "action": "consider_etims",
                "title": "Consider eTIMS registration",
                "detail": f"Your turnover (KES {turnover:,.0f}) may require eTIMS compliance. "
                          f"Check with KRA whether your business needs to register.",
                "urgency": "yellow",
            })

        return recs

    def _shuru_recommendations(self, pin: str, profile: dict, obligations: list) -> list:
        """Recommend KRA Shuru WhatsApp for upcoming filings."""
        recs = []
        due_soon = [o for o in obligations
                    if o.get("days_until_deadline") is not None and 0 < o["days_until_deadline"] <= 14]

        if due_soon:
            info = self.shuru.generate_instructions(pin, lang=profile.get("preferred_language", "en"))
            tax_names = ", ".join(o.get("tax_name", "Tax") for o in due_soon[:3])
            recs.append({
                "priority": 4,
                "action": "file_via_shuru",
                "title": f"FILE VIA WHATSAPP: Use KRA Shuru for {tax_names}",
                "detail": f"KRA's new WhatsApp bot lets you file returns and pay taxes in 3 steps. "
                          f"Send 'Hi' to +254 711 099 999 on WhatsApp.",
                "urgency": "green",
                "shuru_deeplink": info["filing_deeplink"],
                "shuru_number": info["number"],
                "shuru_steps": info["steps"],
            })
        return recs

    def _payment_recommendations(self, pin: str, profile: dict,
                                  obligations: list, penalties: dict) -> list:
        recs = []
        total_penalty = penalties.get("total_penalty_exposure_kes", 0)

        if total_penalty <= 0:
            return recs

        # Generate M-Pesa payment instructions for overdue items
        for ob in obligations:
            days = ob.get("days_until_deadline")
            if days is not None and days < 0:
                tax_key = ob.get("tax_key", "")
                tax_name = ob.get("tax_name", "Tax")

                payment_info = self.mpesa.generate_payment_instructions(
                    tax_type=tax_key,
                    amount=0,  # amount TBD by SME
                    pin=pin,
                )

                shuru_pay = self.shuru.generate_payment_link(pin, tax_name)
                recs.append({
                    "priority": 2,
                    "action": "pay_tax",
                    "title": f"PAY: {tax_name} via M-Pesa or KRA WhatsApp",
                    "detail": f"M-Pesa Paybill: {payment_info['paybill']}, "
                              f"Account: {payment_info['account_number']}. "
                              f"Or pay via KRA WhatsApp (Shuru): +254 711 099 999",
                    "urgency": "red",
                    "tax_type": tax_key,
                    "payment_steps": payment_info["steps"],
                    "shuru_deeplink": shuru_pay["deeplink"],
                })
                break  # One payment instruction is enough in the list

        return recs

    def _risk_recommendations(self, pin: str, profile: dict, risk: dict) -> list:
        recs = []
        score = risk.get("risk_score", 0)

        if score >= 60:
            factors = risk.get("factors", [])
            factor_text = ", ".join(f.get("factor", "") for f in factors[:3]) if factors else "multiple risk factors"

            recs.append({
                "priority": 5,
                "action": "reduce_risk",
                "title": f"HIGH RISK: Audit probability {risk.get('audit_probability_pct', '?')}%",
                "detail": f"Risk score {score}/100 due to: {factor_text}. "
                          f"Filing all obligations on time will reduce your risk score.",
                "urgency": "yellow",
            })

        return recs

    def print_recommendations(self, pin: str):
        """Print recommendations to console."""
        result = self.generate(pin)

        print(f"\n{'='*65}")
        print(f"  ACTION LIST — {result.get('name', pin)}")
        print(f"  Status: {result.get('compliance_status', '?')} | Risk: {result.get('risk_score', '?')}/100")
        print(f"{'='*65}")

        if not result["recommendations"]:
            print("\n  All clear — no actions needed right now.\n")
            return

        urgency_icons = {"red": "!!!", "orange": " !!", "yellow": "  !", "green": "   "}

        for rec in result["recommendations"]:
            icon = urgency_icons.get(rec.get("urgency", ""), "   ")
            print(f"\n  {rec['order']}. [{icon}] {rec['title']}")
            print(f"     {rec['detail']}")
            if rec.get("payment_steps"):
                for step in rec["payment_steps"][:5]:
                    print(f"       > {step}")
            if rec.get("shuru_deeplink"):
                print(f"       > WhatsApp: {rec['shuru_deeplink']}")
            if rec.get("shuru_steps"):
                for step in rec["shuru_steps"]:
                    print(f"       > {step}")

        print()
