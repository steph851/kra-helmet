"""
CONFIDENCE ENGINE — assigns confidence score to findings.
Below 0.7 → human_gate. Above 0.7 → proceeds.
"""
from ..base import BaseAgent


class ConfidenceEngine(BaseAgent):
    name = "confidence_engine"

    def score(self, obligations: list[dict], profile: dict) -> list[dict]:
        """Assign confidence scores to each obligation."""
        self.log(f"Scoring confidence for {profile['pin']}")

        thresholds = self.load_config("confidence_thresholds.json")
        auto_proceed = thresholds.get("auto_proceed", 0.7)

        results = []
        low_confidence = []

        for ob in obligations:
            confidence = ob.get("confidence", 0.5)

            # Boost confidence for well-understood obligations
            if ob["tax_type"] in ("turnover_tax", "vat", "paye", "nssf", "shif", "housing_levy"):
                confidence = min(confidence + 0.1, 1.0)

            # Lower confidence for WHT (depends on specific payments)
            if "withholding_tax" in ob["tax_type"]:
                confidence = max(confidence - 0.1, 0.3)

            # Lower if no deadline calculated
            if not ob.get("next_deadline"):
                confidence = max(confidence - 0.2, 0.2)

            ob["confidence"] = round(confidence, 2)
            ob["auto_proceed"] = confidence >= auto_proceed

            if confidence < auto_proceed:
                low_confidence.append(ob["tax_name"])

            results.append(ob)

        if low_confidence:
            self.log(f"Low confidence items ({len(low_confidence)}): {', '.join(low_confidence)}", "WARN")

        return results
