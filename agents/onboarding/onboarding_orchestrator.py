"""
ONBOARDING ORCHESTRATOR — coordinates profile building, classification, and saves to confirmed/.
"""
from ..base import BaseAgent
from .profile_builder import ProfileBuilder
from .industry_classifier import IndustryClassifier


class OnboardingOrchestrator(BaseAgent):
    name = "onboarding_orchestrator"

    def onboard_interactive(self) -> dict | None:
        """Full interactive onboarding: interview → classify → save."""
        # Step 1: Build profile
        builder = ProfileBuilder()
        profile = builder.build_profile_interactive()
        if not profile:
            return None

        return self._finalize(profile)

    def onboard_from_data(self, data: dict) -> dict | None:
        """Onboard from pre-filled data (batch/API)."""
        builder = ProfileBuilder()
        profile = builder.build_profile_from_data(data)
        return self._finalize(profile)

    def _finalize(self, profile: dict) -> dict:
        """Classify and save the profile."""
        pin = profile["pin"]

        # Step 2: Classify industry + map obligations
        classifier = IndustryClassifier()
        classification = classifier.classify(profile)

        # Attach classification to profile
        profile["classification"] = classification

        # Step 3: Save to confirmed
        self.save_sme(pin, profile)

        # Step 4: Register in SME registry
        self.register_sme(pin, profile["name"])

        self.log(f"Onboarding complete: {profile['name']} (PIN: {pin})")
        self.log(f"  Industry: {classification['industry_label']}")
        self.log(f"  Obligations: {', '.join(classification['obligations'])}")
        self.log(f"  eTIMS required: {classification['etims_required']}")

        self.log_decision(
            f"Onboarded {profile['name']}",
            f"PIN: {pin}, Industry: {classification['industry']}, "
            f"Bracket: {classification['turnover_bracket']}, "
            f"Obligations: {classification['obligations']}"
        )

        return profile
