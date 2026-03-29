"""
RISK SCORER — predicts KRA audit probability per SME.
BOUNDARY: scores only. Never recommends actions.
"""
from datetime import datetime
from ..base import BaseAgent


class RiskScorer(BaseAgent):
    name = "risk_scorer"
    boundary = "Scores only. Never recommends actions."

    # Risk factors and their weights (out of 100 total)
    FACTORS = {
        "overdue_filings":      {"weight": 30, "desc": "Has overdue tax filings"},
        "no_etims":             {"weight": 15, "desc": "VAT registered but not using eTIMS"},
        "high_turnover_tot":    {"weight": 10, "desc": "High turnover on simplified tax (potential underreporting)"},
        "missing_employees":    {"weight": 10, "desc": "Has employees but no PAYE/NSSF registered"},
        "inconsistent_income":  {"weight": 10, "desc": "Declared income inconsistent with industry average"},
        "new_business":         {"weight": 5,  "desc": "Business less than 2 years old (higher scrutiny)"},
        "cash_heavy_industry":  {"weight": 10, "desc": "Industry known for cash transactions"},
        "never_filed":          {"weight": 10, "desc": "No filing history found"},
    }

    CASH_HEAVY = {"retail_wholesale", "food_hospitality", "transport", "salon_beauty"}

    def score(self, profile: dict, obligations: list[dict]) -> dict:
        """Calculate risk score for an SME."""
        self.log(f"Scoring risk for {profile['pin']}")

        triggered = []
        total_score = 0

        # Check each risk factor
        overdue = [o for o in obligations if o.get("status") == "overdue"]
        if overdue:
            pts = self.FACTORS["overdue_filings"]["weight"]
            total_score += pts
            triggered.append(f"[+{pts}] {len(overdue)} overdue filing(s)")

        if profile.get("is_vat_registered") and not profile.get("has_etims"):
            pts = self.FACTORS["no_etims"]["weight"]
            total_score += pts
            triggered.append(f"[+{pts}] VAT registered but eTIMS not active")

        bracket = profile.get("turnover_bracket", "below_1m")
        if bracket in ("8m_to_25m", "above_25m"):
            classification = profile.get("classification", {})
            obs = classification.get("obligations", [])
            if "turnover_tax" in obs and "vat" not in obs:
                pts = self.FACTORS["high_turnover_tot"]["weight"]
                total_score += pts
                triggered.append(f"[+{pts}] High turnover but on simplified tax regime")

        if profile.get("has_employees"):
            classification = profile.get("classification", {})
            obs = classification.get("obligations", [])
            if "paye" not in obs:
                pts = self.FACTORS["missing_employees"]["weight"]
                total_score += pts
                triggered.append(f"[+{pts}] Has employees but PAYE not mapped")

        if profile.get("industry") in self.CASH_HEAVY:
            pts = self.FACTORS["cash_heavy_industry"]["weight"]
            total_score += pts
            triggered.append(f"[+{pts}] Cash-heavy industry ({profile['industry']})")

        onboarded = profile.get("onboarded_at", "")
        if onboarded:
            try:
                age_days = (datetime.now() - datetime.fromisoformat(onboarded)).days
                if age_days < 730:
                    pts = self.FACTORS["new_business"]["weight"]
                    total_score += pts
                    triggered.append(f"[+{pts}] Business recently registered")
            except ValueError:
                pass

        # Cap at 100
        total_score = min(total_score, 100)

        # Risk level
        if total_score >= 70:
            level = "critical"
        elif total_score >= 50:
            level = "high"
        elif total_score >= 30:
            level = "medium"
        else:
            level = "low"

        result = {
            "risk_score": total_score,
            "risk_level": level,
            "factors": triggered,
            "audit_probability_pct": round(total_score * 0.6, 1),  # rough proxy
            "last_assessed": datetime.now().isoformat(),
            "source": self.name,
        }

        self.log(f"Risk score for {profile['pin']}: {total_score}/100 ({level})")
        return result
