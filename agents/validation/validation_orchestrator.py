"""
VALIDATION ORCHESTRATOR — coordinates confidence scoring + disclaimer injection.
Routes: PASS → communication / FAIL → human gate.
"""
from ..base import BaseAgent
from .confidence_engine import ConfidenceEngine
from .disclaimer_injector import DisclaimerInjector


class ValidationOrchestrator(BaseAgent):
    name = "validation_orchestrator"

    def validate(self, profile: dict, obligations: list[dict], compliance: dict, risk: dict) -> dict:
        """Run full validation: confidence scoring + disclaimer injection."""
        self.log(f"Validating output for {profile['pin']}")

        # Score confidence on obligations
        engine = ConfidenceEngine()
        scored_obligations = engine.score(obligations, profile)

        # Inject disclaimers
        injector = DisclaimerInjector()
        lang = profile.get("preferred_language", "en")
        compliance = injector.inject(compliance, lang)
        risk = injector.inject(risk, lang)

        # Determine routing
        low_confidence = [o for o in scored_obligations if not o.get("auto_proceed", True)]
        needs_human_review = len(low_confidence) > 0

        result = {
            "profile": profile,
            "obligations": scored_obligations,
            "compliance": compliance,
            "risk": risk,
            "validation": {
                "passed": not needs_human_review,
                "low_confidence_count": len(low_confidence),
                "low_confidence_items": [o["tax_name"] for o in low_confidence],
                "route": "human_gate" if needs_human_review else "communication",
            }
        }

        if needs_human_review:
            self.log(f"ROUTING → human_gate ({len(low_confidence)} items need review)", "WARN")
            # Write to staging for human review
            self.write_staging("review", f"{profile['pin']}_obligations.json", result)
        else:
            self.log("ROUTING → communication (all items passed)")

        return result
