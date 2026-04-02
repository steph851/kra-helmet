"""
ETIMS CONNECTOR — eTIMS compliance checking and guidance.
BOUNDARY: Checks eTIMS status and provides guidance. Never submits invoices.
Uses local data to estimate eTIMS compliance and missing invoices.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

EAT = timezone(timedelta(hours=3))


class ETIMSConnector:
    """eTIMS compliance checking and guidance."""

    # Average invoice values by industry (KES)
    AVG_INVOICE_BY_INDUSTRY = {
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

    def __init__(self):
        self._state_path = ROOT / "data" / "monitoring" / "etims_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load eTIMS monitoring state."""
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"smes": {}, "alerts": []}

    def _save_state(self):
        """Save eTIMS monitoring state."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def check_compliance(self, profile: dict) -> dict:
        """Check eTIMS compliance for an SME profile."""
        pin = profile.get("pin", "UNKNOWN")
        has_etims = profile.get("has_etims", False)
        is_vat = profile.get("is_vat_registered", False)
        turnover = profile.get("annual_turnover_kes", 0)
        business_type = profile.get("business_type", "sole_proprietor")

        issues = []
        risk_factors = []

        # Check 1: VAT registered but no eTIMS
        if is_vat and not has_etims:
            issues.append("VAT-registered but no eTIMS — mandatory since Sep 2024")
            risk_factors.append("missing_etims_vat")

        # Check 2: High turnover without eTIMS
        if turnover > 5_000_000 and not has_etims:
            issues.append(f"Annual turnover KES {turnover:,.0f} but no eTIMS — may be required")
            risk_factors.append("high_turnover_no_etims")

        # Check 3: Limited company without eTIMS
        if business_type == "limited_company" and not has_etims:
            issues.append("Limited company without eTIMS — likely required")
            risk_factors.append("company_no_etims")

        # Check 4: Estimate missing invoices
        missing_invoices = self._estimate_missing_invoices(profile)
        penalty_kes = 0
        if missing_invoices > 0:
            penalty_kes = missing_invoices * 50  # KES 50 per missing invoice
            issues.append(
                f"Estimated {missing_invoices} missing eTIMS invoices — "
                f"potential penalty KES {penalty_kes:,.0f}"
            )
            risk_factors.append("missing_invoices")

        # Update state
        if issues:
            self._state["smes"][pin] = {
                "status": "non_compliant",
                "has_etims": has_etims,
                "issue_count": len(issues),
                "last_checked": datetime.now(EAT).isoformat(),
            }
        else:
            self._state["smes"][pin] = {
                "status": "compliant",
                "has_etims": has_etims,
                "last_checked": datetime.now(EAT).isoformat(),
            }
        self._save_state()

        return {
            "pin": pin,
            "status": "non_compliant" if issues else "compliant",
            "has_etims": has_etims,
            "is_vat_registered": is_vat,
            "annual_turnover_kes": turnover,
            "issues": issues,
            "risk_factors": risk_factors,
            "issue_count": len(issues),
            "estimated_missing_invoices": missing_invoices,
            "estimated_penalty_kes": penalty_kes,
            "checked_at": datetime.now(EAT).isoformat(),
        }

    def _estimate_missing_invoices(self, profile: dict) -> int:
        """Estimate missing eTIMS invoices based on turnover and industry."""
        if profile.get("has_etims", False):
            return 0

        turnover = profile.get("annual_turnover_kes", 0)
        if turnover <= 0:
            return 0

        industry = profile.get("industry", "retail_wholesale")
        avg_invoice = self.AVG_INVOICE_BY_INDUSTRY.get(industry, 5000)

        # Estimate monthly invoices
        monthly_turnover = turnover / 12
        estimated_monthly_invoices = max(1, int(monthly_turnover / avg_invoice))

        # Assume 3 months of missing invoices (conservative)
        return estimated_monthly_invoices * 3

    def get_registration_steps(self) -> list[str]:
        """Get steps to register for eTIMS."""
        return [
            "Visit your nearest KRA office with:",
            "  - KRA PIN certificate",
            "  - Business registration certificate",
            "  - ID/Passport",
            "  - Proof of business premises",
            "OR apply online at https://etims.kra.go.ke",
            "KRA will issue an eTIMS device or software license",
            "Install and configure the eTIMS system",
            "Start issuing electronic invoices immediately",
        ]

    def get_compliance_tips(self) -> list[str]:
        """Get eTIMS compliance tips."""
        return [
            "Issue eTIMS invoices for ALL sales — no exceptions",
            "Sync invoices daily to avoid data loss",
            "Keep your eTIMS device/software updated",
            "Reconcile eTIMS invoices with your books monthly",
            "Report any eTIMS issues to KRA immediately",
            "KES 50 penalty per missing invoice — it adds up fast",
        ]

    def get_state(self) -> dict:
        """Get current eTIMS monitoring state."""
        smes = self._state.get("smes", {})
        compliant = sum(1 for s in smes.values() if s.get("status") == "compliant")
        non_compliant = sum(1 for s in smes.values() if s.get("status") == "non_compliant")

        return {
            "smes_tracked": len(smes),
            "compliant": compliant,
            "non_compliant": non_compliant,
            "last_scan": self._state.get("last_scan"),
            "recent_alerts": self._state.get("alerts", [])[-5:],
        }
