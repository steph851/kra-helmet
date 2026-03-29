"""
INDUSTRY CLASSIFIER — classifies business type and determines which taxes apply.
BOUNDARY: classifies only. Never calculates amounts.
"""
from ..base import BaseAgent


class IndustryClassifier(BaseAgent):
    name = "industry_classifier"
    boundary = "Classifies only. Never calculates amounts."

    def classify(self, profile: dict) -> dict:
        """Determine which tax obligations apply based on industry + turnover + employees."""
        self.log(f"Classifying: {profile['business_name']} ({profile['industry']})")

        industry_profiles = self.load_intel("industry_profiles.json")
        industries = industry_profiles.get("industries", {})

        industry_key = profile["industry"]
        industry = industries.get(industry_key)
        if not industry:
            self.log(f"Unknown industry: {industry_key} — defaulting to retail_wholesale", "WARN")
            industry = industries["retail_wholesale"]

        # Determine base obligations from turnover bracket
        bracket = profile.get("turnover_bracket", "below_1m")
        obligations_map = industry.get("obligations", {})

        # Try bracket-specific mapping first
        obligations = obligations_map.get(bracket, [])

        # If using "all" key (e.g. manufacturing)
        if not obligations and "all" in obligations_map:
            obligations = list(obligations_map["all"])

        # Add excise if applicable
        if "if_excisable" in obligations_map:
            # v2: ask if business produces excisable goods
            pass

        # Add employee-related obligations
        if profile.get("has_employees"):
            employee_obligations = industry.get("if_has_employees", [])
            for ob in employee_obligations:
                if ob not in obligations:
                    obligations.append(ob)

        # Add rental income tax if applicable
        rental = profile.get("rental_income_annual_kes") or 0
        if rental > 0:
            if 288000 <= rental <= 15000000:
                if "residential_rental_income" not in obligations:
                    obligations.append("residential_rental_income")
            elif rental > 15000000:
                if "income_tax_resident" not in obligations:
                    obligations.append("income_tax_resident")

        # Add VAT if registered but not already in list
        if profile.get("is_vat_registered") and "vat" not in obligations:
            obligations.append("vat")

        # Add WHT triggers
        wht_triggers = industry.get("common_wht_triggers", [])

        result = {
            "industry": industry_key,
            "industry_label": industry.get("label", industry_key),
            "turnover_bracket": bracket,
            "obligations": obligations,
            "wht_triggers": wht_triggers,
            "etims_required": profile.get("is_vat_registered", False),
            "notes": industry.get("note"),
        }

        self.log(f"Classified: {len(obligations)} obligations for {profile['business_name']}")
        self.log_decision(
            f"Classified {profile['pin']} as {industry_key}/{bracket}",
            f"Obligations: {obligations}"
        )
        return result
