"""
WORKFLOW ENGINE — prepares filing packages for SMEs.
BOUNDARY: Assembles documents and instructions. Never files on iTax.
Generates a filing-ready package with:
  - Pre-filled data from profile and obligations
  - Step-by-step iTax instructions from filing guides
  - Required documents checklist
  - M-Pesa payment instructions
  - Deadline countdown
"""
import json
from datetime import datetime, timedelta, timezone

from ..base import BaseAgent

import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.mpesa_caller import MpesaCaller
from workflow.filing_tracker import FilingTracker

EAT = timezone(timedelta(hours=3))


class WorkflowEngine(BaseAgent):
    name = "workflow_engine"
    boundary = "Prepares filing packages. Never files on iTax or submits payments."

    def __init__(self):
        super().__init__()
        self.mpesa = MpesaCaller()
        self.tracker = FilingTracker()

    def prepare_filing(self, pin: str, tax_type: str) -> dict | None:
        """Prepare a complete filing package for a specific tax obligation."""
        profile = self.load_sme(pin)
        if not profile:
            self.log(f"SME not found: {pin}", "ERROR")
            return None

        # Load filing guide
        guide = self._get_guide(tax_type)

        # Load obligation data
        obligation = self._get_obligation(pin, tax_type)

        # Check if already filed for current period
        current_period = datetime.now(EAT).strftime("%Y-%m")
        already_filed = self.tracker.is_filed(pin, tax_type, current_period)

        # Payment instructions
        payment = self.mpesa.generate_payment_instructions(
            tax_type=tax_type,
            amount=0,  # SME fills in actual amount
            pin=pin,
        )

        package = {
            "type": "filing_package",
            "pin": pin,
            "name": profile.get("name", ""),
            "business_name": profile.get("business_name", ""),
            "tax_type": tax_type,
            "period": current_period,
            "already_filed": already_filed,

            # Profile data for pre-filling
            "prefill_data": {
                "kra_pin": pin,
                "taxpayer_name": profile.get("name", ""),
                "business_name": profile.get("business_name", ""),
                "business_type": profile.get("business_type", ""),
                "county": profile.get("county", ""),
                "is_vat_registered": profile.get("is_vat_registered", False),
                "has_etims": profile.get("has_etims", False),
                "employee_count": profile.get("employee_count", 0),
            },

            # Obligation details
            "obligation": obligation,

            # Filing guide
            "guide": guide,

            # Payment
            "payment_instructions": payment,

            # Deadline info
            "deadline": obligation.get("next_deadline") if obligation else None,
            "days_remaining": obligation.get("days_until_deadline") if obligation else None,

            # Checklist
            "checklist": self._build_checklist(tax_type, profile, guide),

            "prepared_at": datetime.now(EAT).isoformat(),
            "prepared_by": self.name,
        }

        # Save the package
        packages_dir = self.data_dir / "filing_packages"
        packages_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(EAT).strftime("%Y%m%d_%H%M%S")
        package_path = packages_dir / f"pkg_{pin}_{tax_type}_{ts}.json"
        self.save_json(package_path, package)

        self.log(f"Filing package prepared: {pin} / {tax_type}")
        return package

    def prepare_all_due(self, pin: str) -> list[dict]:
        """Prepare filing packages for all due/overdue obligations."""
        report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
        if not report_path.exists():
            return []

        report = self.load_json(report_path)
        obligations = report.get("obligations", [])
        packages = []

        for ob in obligations:
            days = ob.get("days_until_deadline")
            if days is not None and days <= 7:  # due within a week or overdue
                tax_key = ob.get("tax_key", "")
                if tax_key:
                    package = self.safe_run(
                        lambda tk=tax_key: self.prepare_filing(pin, tk),
                        context=f"prepare_{tax_key}",
                        fallback=None,
                    )
                    if package:
                        packages.append(package)

        return packages

    def _get_guide(self, tax_type: str) -> dict | None:
        """Load filing guide for a tax type."""
        try:
            guides_path = self.intel_dir / "filing_guides.json"
            data = json.loads(guides_path.read_text(encoding="utf-8"))
            return next(
                (g for g in data["filing_guides"] if g["tax_key"] == tax_type),
                None,
            )
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _get_obligation(self, pin: str, tax_type: str) -> dict | None:
        """Load obligation data for a specific tax type from the latest report."""
        report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
        if not report_path.exists():
            return None

        try:
            report = self.load_json(report_path)
            obligations = report.get("obligations", [])
            return next(
                (o for o in obligations if o.get("tax_key") == tax_type),
                None,
            )
        except Exception:
            return None

    def _build_checklist(self, tax_type: str, profile: dict, guide: dict | None) -> list[dict]:
        """Build a pre-filing checklist."""
        items = [
            {"step": "Log in to iTax", "url": "https://itax.kra.go.ke", "done": False},
        ]

        # Add documents from guide
        if guide:
            for doc in guide.get("documents_needed", []):
                items.append({"step": f"Prepare: {doc}", "done": False})

        # Tax-specific items
        if tax_type in ("paye", "nssf", "shif", "housing_levy"):
            items.append({"step": "Prepare payroll summary for the period", "done": False})
            items.append({"step": f"Verify employee count: {profile.get('employee_count', 0)}", "done": False})

        if tax_type == "vat":
            items.append({"step": "Reconcile sales and purchase invoices", "done": False})
            if profile.get("has_etims"):
                items.append({"step": "Ensure all eTIMS invoices are synced", "done": False})

        if tax_type == "tot":
            items.append({"step": "Calculate 1.5% of gross monthly turnover", "done": False})

        # Common final steps
        items.extend([
            {"step": "File the return on iTax", "done": False},
            {"step": "Pay via M-Pesa (Paybill 572572)", "done": False},
            {"step": "Save acknowledgment receipt", "done": False},
            {"step": "Record filing: python run.py file " + profile.get("pin", "PIN"), "done": False},
        ])

        return items

    def print_package(self, package: dict):
        """Print a filing package to console."""
        print(f"\n{'='*65}")
        print(f"  FILING PACKAGE — {package['name']}")
        print(f"  Tax: {package['tax_type']} | Period: {package['period']}")
        print(f"{'='*65}")

        if package.get("already_filed"):
            print(f"\n  NOTE: Already filed for {package['period']}")

        ob = package.get("obligation")
        if ob:
            days = ob.get("days_until_deadline")
            if days is not None and days < 0:
                print(f"\n  STATUS: OVERDUE by {abs(days)} day(s)")
            elif days is not None and days == 0:
                print(f"\n  STATUS: DUE TODAY")
            elif days is not None:
                print(f"\n  STATUS: {days} day(s) remaining (deadline: {ob.get('next_deadline', '?')})")

        guide = package.get("guide")
        if guide:
            print(f"\n  iTax Path: {guide.get('itax_menu_path', '?')}")
            print(f"  Estimated Time: {guide.get('estimated_time', '?')}")
            print(f"\n  Steps:")
            for i, step in enumerate(guide.get("steps", []), 1):
                print(f"    {i:2d}. {step}")

        print(f"\n  Checklist:")
        for item in package.get("checklist", []):
            print(f"    [ ] {item['step']}")

        pay = package.get("payment_instructions", {})
        if pay:
            print(f"\n  Payment:")
            print(f"    Paybill: {pay.get('paybill', '?')}")
            print(f"    Account: {pay.get('account_number', '?')}")

        print()
