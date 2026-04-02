"""
eTIMS MONITOR — watches eTIMS invoice compliance for onboarded SMEs.
BOUNDARY: Tracks invoice counts and gaps from local data.
Never connects to the actual eTIMS API (v2 feature) — works from filed data.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..base import BaseAgent

EAT = timezone(timedelta(hours=3))


class EtimsMonitor(BaseAgent):
    name = "etims_monitor"
    boundary = "Tracks eTIMS invoice gaps from local data. Never connects to eTIMS API."

    def __init__(self):
        super().__init__()
        self._state_file = self.data_dir / "monitoring" / "etims_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"smes": {}, "alerts": []}

    def _save_state(self):
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self.save_json(self._state_file, self._state)

    def scan(self) -> list[dict]:
        """Scan all onboarded SMEs for eTIMS compliance issues. Returns findings."""
        findings = []
        smes = self.list_smes()

        for sme in smes:
            if not sme.get("active", True):
                continue

            pin = sme["pin"]
            profile = self.load_sme(pin)
            if not profile:
                continue

            result = self._check_sme_etims(pin, profile)
            if result:
                findings.append(result)

        if findings:
            self.log(f"eTIMS issues found for {len(findings)} SME(s)")
            for finding in findings:
                self._route_to_review(finding)

        self._state["last_scan"] = datetime.now(EAT).isoformat()
        self._save_state()
        return findings

    def check_sme(self, pin: str) -> dict:
        """Check eTIMS compliance for a single SME."""
        profile = self.load_sme(pin)
        if not profile:
            return {
                "pin": pin,
                "status": "not_found",
                "checked_at": datetime.now(EAT).isoformat(),
            }
        return self._check_sme_etims(pin, profile) or {
            "pin": pin,
            "status": "compliant",
            "has_etims": profile.get("has_etims", False),
            "checked_at": datetime.now(EAT).isoformat(),
        }

    def _check_sme_etims(self, pin: str, profile: dict) -> dict | None:
        """Analyze eTIMS compliance for one SME. Returns finding dict or None if OK."""
        has_etims = profile.get("has_etims", False)
        turnover = profile.get("annual_turnover_kes", 0)
        is_vat = profile.get("is_vat_registered", False)
        business_type = profile.get("business_type", "sole_proprietor")

        issues = []
        risk_factors = []

        # Check 1: Should have eTIMS but doesn't
        # As of 2024, all VAT-registered taxpayers must use eTIMS
        if is_vat and not has_etims:
            issues.append("VAT-registered but no eTIMS — mandatory since Sep 2024")
            risk_factors.append("missing_etims_vat")

        # Check 2: High turnover without eTIMS (likely needs it)
        if turnover > 5_000_000 and not has_etims:
            issues.append(f"Annual turnover KES {turnover:,.0f} but no eTIMS — may be required")
            risk_factors.append("high_turnover_no_etims")

        # Check 3: Limited company without eTIMS
        if business_type == "limited_company" and not has_etims:
            issues.append("Limited company without eTIMS — likely required")
            risk_factors.append("company_no_etims")

        # Check 4: Filing gaps — look at recent filing data
        filing_gaps = self._check_filing_gaps(pin)
        if filing_gaps:
            issues.extend(filing_gaps["issues"])
            risk_factors.extend(filing_gaps.get("risk_factors", []))

        # Check 5: Invoice count estimation
        invoice_estimate = self._estimate_missing_invoices(profile)
        if invoice_estimate > 0:
            penalty_per_invoice = self._settings.get("penalties", {}).get("etims_missing_invoice_penalty_kes", 50)
            penalty_kes = invoice_estimate * penalty_per_invoice
            issues.append(
                f"Estimated {invoice_estimate} missing eTIMS invoices — "
                f"potential penalty KES {penalty_kes:,.0f}"
            )
            risk_factors.append("missing_invoices")

        if not issues:
            # Update state — SME is compliant
            self._state["smes"][pin] = {
                "status": "compliant",
                "has_etims": has_etims,
                "last_checked": datetime.now(EAT).isoformat(),
            }
            return None

        # Build finding
        finding = {
            "pin": pin,
            "name": profile.get("name", "Unknown"),
            "has_etims": has_etims,
            "is_vat_registered": is_vat,
            "annual_turnover_kes": turnover,
            "issues": issues,
            "risk_factors": risk_factors,
            "issue_count": len(issues),
            "estimated_missing_invoices": invoice_estimate,
            "estimated_penalty_kes": invoice_estimate * 50,
            "detected_at": datetime.now(EAT).isoformat(),
        }

        # Update state
        self._state["smes"][pin] = {
            "status": "non_compliant",
            "has_etims": has_etims,
            "issue_count": len(issues),
            "last_checked": datetime.now(EAT).isoformat(),
        }
        self._state["alerts"].append({
            "pin": pin,
            "issue_count": len(issues),
            "detected_at": finding["detected_at"],
        })
        self._state["alerts"] = self._state["alerts"][-100:]

        return finding

    def _check_filing_gaps(self, pin: str) -> dict | None:
        """Check for months where filings are expected but missing."""
        filings_path = self.data_dir / "filings" / f"{pin}.jsonl"
        if not filings_path.exists():
            return None

        # Read filings
        filings = []
        try:
            with open(filings_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            filings.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            return None

        if not filings:
            return None

        # Find filed periods
        filed_periods = set()
        for filing in filings:
            period = filing.get("period")
            if period:
                filed_periods.add(period)

        # Check for gaps in last 6 months
        now = datetime.now(EAT)
        issues = []
        risk_factors = []

        for months_ago in range(1, 7):
            check_date = now - timedelta(days=30 * months_ago)
            period = check_date.strftime("%Y-%m")

            if period not in filed_periods:
                issues.append(f"No filings found for period {period}")
                risk_factors.append(f"gap_{period}")

        if not issues:
            return None

        return {"issues": issues[:3], "risk_factors": risk_factors[:3]}  # cap at 3

    def _estimate_missing_invoices(self, profile: dict) -> int:
        """Estimate missing eTIMS invoices based on turnover and industry."""
        if profile.get("has_etims", False):
            return 0  # has eTIMS, assume compliant for now

        turnover = profile.get("annual_turnover_kes", 0)
        if turnover <= 0:
            return 0

        # Rough estimate: average invoice value by industry
        avg_invoice_by_industry = {
            "retail_wholesale": 2000,
            "professional_services": 50000,
            "food_hospitality": 1500,
            "transport": 3000,
            "manufacturing": 25000,
            "rental_income": 30000,
            "digital_online": 5000,
            "construction": 100000,
            "agriculture": 15000,
            "salon_beauty": 1000,
            "education": 20000,
            "healthcare": 5000,
        }

        industry = profile.get("industry", "retail_wholesale")
        avg_invoice = avg_invoice_by_industry.get(industry, 5000)

        # Estimate monthly invoices
        monthly_turnover = turnover / 12
        estimated_monthly_invoices = max(1, int(monthly_turnover / avg_invoice))

        # Assume 3 months of missing invoices (conservative)
        return estimated_monthly_invoices * 3

    def _route_to_review(self, finding: dict):
        """Route eTIMS finding to human review."""
        review_item = {
            "type": "etims_compliance_issue",
            "pin": finding["pin"],
            "name": finding["name"],
            "issues": finding["issues"],
            "estimated_penalty_kes": finding["estimated_penalty_kes"],
            "detected_at": finding["detected_at"],
            "status": "pending_review",
            "action_needed": "Review eTIMS compliance and advise SME on registration/device setup",
        }

        ts = datetime.now(EAT).strftime("%Y%m%d_%H%M%S")
        filename = f"etims_{finding['pin']}_{ts}.json"
        self.write_staging("review", filename, review_item)

    def get_state(self) -> dict:
        sme_states = self._state.get("smes", {})
        compliant = sum(1 for s in sme_states.values() if s.get("status") == "compliant")
        non_compliant = sum(1 for s in sme_states.values() if s.get("status") == "non_compliant")

        return {
            "smes_tracked": len(sme_states),
            "compliant": compliant,
            "non_compliant": non_compliant,
            "last_scan": self._state.get("last_scan"),
            "recent_alerts": self._state.get("alerts", [])[-5:],
        }
