"""
ORCHESTRATOR — the brain. Reads state, dispatches agents, coordinates the full pipeline.
Does NOT do research, extraction, or alerting itself.
Wraps each pipeline step in error recovery.
"""
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base import BaseAgent, AgentError
from .onboarding import OnboardingOrchestrator
from .intelligence import ObligationMapper, DeadlineCalculator, RiskScorer, ComplianceChecker, PenaltyCalculator
from .validation import ValidationOrchestrator
from .validation.input_validator import InputValidator
from .communication import Explainer, UrgencyFramer, NotificationEngine
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from workflow.audit_trail import AuditTrail


class Orchestrator(BaseAgent):
    name = "orchestrator"

    def __init__(self):
        super().__init__()
        self.audit = AuditTrail()
        self.validator = InputValidator()

    # ── Onboarding ──────────────────────────────────────────────────

    def onboard(self, interactive: bool = True, data: dict | None = None) -> dict | None:
        """Onboard a new SME with input validation."""
        self.log("=== ONBOARD START ===")

        # Validate input (skip for interactive — profile_builder handles it)
        if not interactive and data:
            ok, errors = self.validator.validate_profile(data)
            if not ok:
                self.log(f"Validation failed: {errors}", "ERROR")
                for err in errors:
                    print(f"  Validation error: {err}")
                return None

        try:
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

        except AgentError as e:
            self.log(f"Onboarding failed: {e}", "ERROR")
            return None
        except Exception as e:
            self.log(f"Unexpected error during onboarding: {e}", "ERROR")
            self._log_error(e, "onboarding")
            return None

    # ── Full Compliance Check ────────────────────────────────────────

    def check_sme(self, pin: str) -> dict | None:
        """Run the full intelligence pipeline for a single SME with error recovery."""
        self.log(f"=== CHECK START: {pin} ===")

        # Validate PIN
        ok, msg = self.validator.validate_pin(pin)
        if not ok:
            self.log(f"Invalid PIN: {msg}", "ERROR")
            return None

        # Load profile
        profile = self.load_sme(pin)
        if not profile:
            self.log(f"SME not found: {pin}", "ERROR")
            return None

        # Pipeline steps with error recovery
        try:
            # Step 1: Map obligations
            obligations = self.safe_run(
                lambda: ObligationMapper().map_obligations(profile),
                context="obligation_mapping",
                fallback=None,
            )
            if obligations is None:
                self.log(f"Obligation mapping failed for {pin} — aborting", "ERROR")
                return None

            # Step 2: Calculate deadlines
            obligations = self.safe_run(
                lambda: DeadlineCalculator().calculate_deadlines(obligations),
                context="deadline_calculation",
                fallback=obligations,  # continue with unmapped deadlines
            )

            # Step 3: Score risk
            risk = self.safe_run(
                lambda: RiskScorer().score(profile, obligations),
                context="risk_scoring",
                fallback={"risk_score": 0, "risk_level": "unknown", "factors": [], "audit_probability_pct": 0},
            )

            # Step 4: Check compliance
            compliance = self.safe_run(
                lambda: ComplianceChecker().check(profile, obligations),
                context="compliance_checking",
                fallback={"overall": "unknown", "obligations_met": 0, "obligations_total": len(obligations),
                          "overdue_count": 0, "overdue_list": [], "critical_list": [],
                          "next_action": "Compliance check encountered an error.", "checked_at": datetime.now().isoformat()},
            )

            # Step 5: Calculate penalties
            penalties = self.safe_run(
                lambda: PenaltyCalculator().calculate_penalties(profile, obligations),
                context="penalty_calculation",
                fallback={"total_penalty_exposure_kes": 0, "severity": "unknown", "penalties": []},
            )

            # Step 6: Validate
            validated = self.safe_run(
                lambda: ValidationOrchestrator().validate(profile, obligations, compliance, risk),
                context="validation",
                fallback={"profile": profile, "obligations": obligations, "compliance": compliance, "risk": risk},
            )
            validated["penalties"] = penalties

            # Step 7: Frame urgency
            urgency = self.safe_run(
                lambda: UrgencyFramer().frame(obligations),
                context="urgency_framing",
                fallback={"urgency_level": "unknown", "emoji": "⚪", "prefix": "UNKNOWN",
                          "action": "no_alert", "should_alert": False, "overdue_count": 0,
                          "critical_count": 0, "urgent_count": 0},
            )
            validated["urgency"] = urgency

            # Step 8: Generate explanation
            message = self.safe_run(
                lambda: Explainer().explain(validated),
                context="explanation",
                fallback=f"Compliance check completed for {profile.get('name', pin)}. Some steps encountered errors — review the dashboard for details.",
            )
            validated["message"] = message

            # Step 9: Queue notifications (non-critical — don't fail the pipeline)
            alerts = self.safe_run(
                lambda: NotificationEngine().generate_alerts(profile, obligations, urgency),
                context="notification_queue",
                fallback=[],
            )
            if alerts:
                self.safe_run(
                    lambda: NotificationEngine().save_alert_queue(alerts),
                    context="save_alerts",
                    fallback=None,
                )
                validated["alerts_queued"] = len(alerts)

            # Save full report
            report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
            self.safe_run(
                lambda: self.save_json(report_path, {
                    "pin": pin,
                    "checked_at": datetime.now().isoformat(),
                    "obligations": obligations,
                    "compliance": compliance,
                    "risk": risk,
                    "penalties": penalties,
                    "urgency": urgency,
                }),
                context="save_report",
                fallback=None,
            )

            # Audit
            self.audit.record("COMPLIANCE_CHECK", self.name, {
                "obligations_count": len(obligations),
                "compliance_status": compliance.get("overall", "unknown"),
                "risk_score": risk.get("risk_score", 0),
                "penalty_exposure_kes": penalties.get("total_penalty_exposure_kes", 0),
                "penalty_severity": penalties.get("severity", "none"),
                "urgency": urgency.get("urgency_level", "unknown"),
                "alerts_queued": validated.get("alerts_queued", 0),
            }, sme_pin=pin)

            self.log(f"=== CHECK COMPLETE: {pin} | {compliance.get('overall', 'unknown')} | risk={risk.get('risk_score', '?')} ===")
            return validated

        except Exception as e:
            self.log(f"Pipeline failed for {pin}: {e}", "ERROR")
            self._log_error(e, f"check_sme({pin})")
            self.audit.record("PIPELINE_ERROR", self.name, {
                "error": str(e),
                "error_type": type(e).__name__,
            }, sme_pin=pin)
            return None

    # ── Check All SMEs ──────────────────────────────────────────────

    def check_all(self, max_workers: int = 5) -> list[dict]:
        """Run compliance check for all onboarded SMEs in parallel. Continues on individual failures."""
        smes = self.list_smes()
        active_smes = [s for s in smes if s.get("active", True)]
        results = []

        self.log(f"=== CHECKING ALL ({len(active_smes)} SMEs, {max_workers} workers) ===")

        def check_one(sme):
            try:
                return self.check_sme(sme["pin"])
            except Exception as e:
                self.log(f"Failed to check {sme['pin']}: {e} — continuing", "ERROR")
                self._log_error(e, f"check_all({sme['pin']})")
                return None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(check_one, sme): sme for sme in active_smes}
            for future in as_completed(futures):
                result = future.result()
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
                try:
                    report = self.load_json(report_path)
                    status = report.get("compliance", {}).get("overall", "unknown")
                    risk = report.get("risk", {}).get("risk_score", "?")
                    urgency = report.get("urgency", {}).get("emoji", "")
                    print(f"  {urgency} {sme['name']} ({pin}) — {status} | risk={risk}")
                except Exception:
                    print(f"  ⚠ {sme['name']} ({pin}) — error reading report")
            else:
                print(f"  ⚪ {sme['name']} ({pin}) — not yet checked")

        print()
