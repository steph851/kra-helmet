"""
ORCHESTRATOR — the brain. Reads state, dispatches agents, coordinates the full pipeline.
Does NOT do research, extraction, or alerting itself.
"""
import json
from datetime import datetime
from .base import BaseAgent
from .onboarding import OnboardingOrchestrator
from .intelligence import ObligationMapper, DeadlineCalculator, RiskScorer, ComplianceChecker
from .validation import ValidationOrchestrator
from .communication import Explainer, UrgencyFramer
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from workflow.audit_trail import AuditTrail


class Orchestrator(BaseAgent):
    name = "orchestrator"

    def __init__(self):
        super().__init__()
        self.audit = AuditTrail()

    # ── Onboarding ──────────────────────────────────────────────────

    def onboard(self, interactive: bool = True, data: dict | None = None) -> dict | None:
        """Onboard a new SME."""
        self.log("=== ONBOARD START ===")
        onboarder = OnboardingOrchestrator()

        if interactive:
            profile = onboarder.onboard_interactive()
        else:
            profile = onboarder.onboard_from_data(data)

        if profile:
            self.audit.record("ONBOARD", self.name, {
                "pin": profile["pin"],
                "industry": profile["industry"],
                "bracket": profile.get("turnover_bracket"),
            }, sme_pin=profile["pin"])

        return profile

    # ── Full Compliance Check ────────────────────────────────────────

    def check_sme(self, pin: str) -> dict | None:
        """Run the full intelligence pipeline for a single SME."""
        self.log(f"=== CHECK START: {pin} ===")

        # Load profile
        profile = self.load_sme(pin)
        if not profile:
            self.log(f"SME not found: {pin}", "ERROR")
            return None

        # Step 1: Map obligations
        mapper = ObligationMapper()
        obligations = mapper.map_obligations(profile)

        # Step 2: Calculate deadlines
        calculator = DeadlineCalculator()
        obligations = calculator.calculate_deadlines(obligations)

        # Step 3: Score risk
        scorer = RiskScorer()
        risk = scorer.score(profile, obligations)

        # Step 4: Check compliance
        checker = ComplianceChecker()
        compliance = checker.check(profile, obligations)

        # Step 5: Validate
        validator = ValidationOrchestrator()
        validated = validator.validate(profile, obligations, compliance, risk)

        # Step 6: Frame urgency
        framer = UrgencyFramer()
        urgency = framer.frame(obligations)
        validated["urgency"] = urgency

        # Step 7: Generate explanation
        explainer = Explainer()
        message = explainer.explain(validated)
        validated["message"] = message

        # Save full report
        report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
        self.save_json(report_path, {
            "pin": pin,
            "checked_at": datetime.now().isoformat(),
            "obligations": obligations,
            "compliance": compliance,
            "risk": risk,
            "urgency": urgency,
        })

        # Audit
        self.audit.record("COMPLIANCE_CHECK", self.name, {
            "obligations_count": len(obligations),
            "compliance_status": compliance["overall"],
            "risk_score": risk["risk_score"],
            "urgency": urgency["urgency_level"],
        }, sme_pin=pin)

        self.log(f"=== CHECK COMPLETE: {pin} | {compliance['overall']} | risk={risk['risk_score']} ===")
        return validated

    # ── Check All SMEs ──────────────────────────────────────────────

    def check_all(self) -> list[dict]:
        """Run compliance check for all onboarded SMEs."""
        smes = self.list_smes()
        results = []

        self.log(f"=== CHECKING ALL ({len(smes)} SMEs) ===")
        for sme in smes:
            if sme.get("active", True):
                result = self.check_sme(sme["pin"])
                if result:
                    results.append(result)

        return results

    # ── Status Dashboard (CLI) ──────────────────────────────────────

    def status(self):
        """Print system status to console."""
        smes = self.list_smes()
        print(f"\n{'='*60}")
        print(f"  KRA HELMET — System Status")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        print(f"  Onboarded SMEs: {len(smes)}")

        for sme in smes:
            pin = sme["pin"]
            report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
            if report_path.exists():
                report = self.load_json(report_path)
                status = report.get("compliance", {}).get("overall", "unknown")
                risk = report.get("risk", {}).get("risk_score", "?")
                urgency = report.get("urgency", {}).get("emoji", "")
                print(f"  {urgency} {sme['name']} ({pin}) — {status} | risk={risk}")
            else:
                print(f"  ⚪ {sme['name']} ({pin}) — not yet checked")

        print()
