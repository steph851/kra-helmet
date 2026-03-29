"""
OBLIGATION MAPPER — maps tax obligations to a specific SME profile.
BOUNDARY: maps obligations only. Never calculates deadlines.
"""
from ..base import BaseAgent


class ObligationMapper(BaseAgent):
    name = "obligation_mapper"
    boundary = "Maps obligations only. Never calculates deadlines or amounts."

    def map_obligations(self, profile: dict) -> list[dict]:
        """Map specific tax obligations for an SME based on their profile + classification."""
        self.log(f"Mapping obligations for {profile['pin']}")

        tax_graph = self.load_intel("tax_knowledge_graph.json")
        taxes = tax_graph.get("taxes", {})

        classification = profile.get("classification", {})
        obligation_keys = classification.get("obligations", [])

        obligations = []
        for key in obligation_keys:
            tax = taxes.get(key)
            if not tax:
                self.log(f"Unknown tax type: {key}", "WARN")
                continue

            ob = {
                "tax_type": key,
                "tax_name": tax["name"],
                "description": tax.get("description", ""),
                "frequency": tax.get("filing_frequency", "unknown"),
                "deadline_day": tax.get("filing_deadline_day"),
                "deadline_date": tax.get("filing_deadline", tax.get("deadline")),
                "rate": self._get_rate(tax, profile),
                "penalty_late_filing": tax.get("penalty_late_filing_kes") or tax.get("penalty_late_filing_pct"),
                "penalty_late_payment_pct": tax.get("penalty_late_payment_pct"),
                "interest_monthly_pct": tax.get("interest_on_late_pct_monthly"),
                "etims_required": tax.get("etims_required", False),
                "itax_code": tax.get("itax_obligation_code"),
                "status": "upcoming",
                "confidence": 0.85,
                "source": self.name,
            }
            obligations.append(ob)

        # Add WHT if triggers exist
        wht_triggers = classification.get("wht_triggers", [])
        if wht_triggers:
            wht = taxes.get("withholding_tax", {})
            rates_detail = wht.get("rates", {})
            for trigger in wht_triggers:
                rate = rates_detail.get(f"{trigger}_pct")
                obligations.append({
                    "tax_type": f"withholding_tax_{trigger}",
                    "tax_name": f"Withholding Tax ({trigger.replace('_', ' ').title()})",
                    "description": f"WHT on {trigger.replace('_', ' ')} payments",
                    "frequency": "monthly",
                    "deadline_day": 20,
                    "deadline_date": None,
                    "rate": f"{rate}%" if rate else "varies",
                    "penalty_late_filing": None,
                    "penalty_late_payment_pct": 5.0,
                    "interest_monthly_pct": 1.0,
                    "etims_required": False,
                    "itax_code": "WHT",
                    "status": "upcoming",
                    "confidence": 0.75,
                    "source": self.name,
                })

        self.log(f"Mapped {len(obligations)} obligations for {profile['pin']}")
        return obligations

    def _get_rate(self, tax: dict, profile: dict) -> str:
        """Extract the applicable rate as a display string."""
        if "rate_pct" in tax:
            return f"{tax['rate_pct']}%"
        if "rate_standard_pct" in tax:
            return f"{tax['rate_standard_pct']}%"
        if "amount_kes_annual" in tax:
            return f"KES {tax['amount_kes_annual']:,}/year"
        if "rate_employee_pct" in tax:
            return f"{tax['rate_employee_pct']}% (employee) + {tax.get('rate_employer_pct', 0)}% (employer)"
        if "brackets_2025" in tax:
            return "progressive (10%-35%)"
        return "varies"
