"""
PENALTY CALCULATOR — calculates KRA penalties and interest for late filing/payment.
Based on real Kenya tax law: Tax Procedures Act 2015, Income Tax Act, VAT Act.
BOUNDARY: calculates exposure only. Never recommends actions or scores risk.
"""
import math
from datetime import date, datetime
from ..base import BaseAgent


class PenaltyCalculator(BaseAgent):
    name = "penalty_calculator"
    boundary = "Calculates exposure only. Never recommends actions or scores risk."

    # ── KRA penalty rules (Kenya tax law) ────────────────────────────

    # Income Tax / generic late filing: KES 20,000 or 5% of tax due, whichever is higher
    INCOME_TAX_LATE_FILING_FLAT = 20_000
    INCOME_TAX_LATE_FILING_PCT = 0.05

    # Late payment: 5% one-time penalty + 1% monthly compounding interest
    LATE_PAYMENT_PENALTY_PCT = 0.05
    LATE_PAYMENT_INTEREST_MONTHLY = 0.01

    # VAT late filing: KES 10,000 or 5% of VAT due
    VAT_LATE_FILING_FLAT = 10_000
    VAT_LATE_FILING_PCT = 0.05

    # PAYE late filing: 25% of tax due or KES 10,000
    PAYE_LATE_FILING_PCT = 0.25
    PAYE_LATE_FILING_FLAT = 10_000

    # Turnover Tax late filing: KES 20,000 or 5% of turnover tax due
    TOT_LATE_FILING_FLAT = 20_000
    TOT_LATE_FILING_PCT = 0.05

    # NSSF late penalty: 5% of contribution per month
    NSSF_LATE_MONTHLY_PCT = 0.05

    # SHIF (formerly NHIF) late penalty: 5% per month
    SHIF_LATE_MONTHLY_PCT = 0.05

    # Housing Levy late penalty: 3% of amount due per month
    HOUSING_LEVY_LATE_MONTHLY_PCT = 0.03

    # eTIMS non-compliance: KES 50 per invoice not on eTIMS
    ETIMS_PER_INVOICE = 50

    # Tax types mapped to their penalty rules
    PENALTY_RULES = {
        "income_tax":       "income_tax",
        "vat":              "vat",
        "paye":             "paye",
        "turnover_tax":     "tot",
        "nssf":             "nssf",
        "shif":             "shif",
        "nhif":             "shif",       # legacy name maps to SHIF
        "housing_levy":     "housing_levy",
        "withholding_tax":  "income_tax",
        "installment_tax":  "income_tax",
        "etims":            "etims",
    }

    def calculate_penalties(self, profile: dict, obligations: list[dict]) -> dict:
        """
        Calculate penalty exposure for each overdue obligation.

        Args:
            profile: SME profile dict (must have 'pin', may have estimated amounts).
            obligations: list from DeadlineCalculator with 'status', 'days_until_deadline',
                         'tax_type', and optionally 'estimated_amount_kes'.

        Returns:
            dict with per-obligation breakdown, totals, and severity.
        """
        pin = profile.get("pin", "UNKNOWN")
        self.log(f"Calculating penalties for {pin}")

        overdue = [o for o in obligations if o.get("status") == "overdue"]
        if not overdue:
            self.log(f"No overdue obligations for {pin}")
            return {
                "pin": pin,
                "overdue_count": 0,
                "penalties": [],
                "total_penalty_exposure_kes": 0,
                "severity": "manageable",
                "assessed_at": datetime.now().isoformat(),
                "source": self.name,
            }

        penalties = []
        total_exposure = 0

        for ob in overdue:
            result = self._calculate_single(ob)
            penalties.append(result)
            total_exposure += result["total_exposure_kes"]

        # Severity classification
        if total_exposure > 200_000:
            severity = "critical"
        elif total_exposure > 50_000:
            severity = "serious"
        else:
            severity = "manageable"

        summary = {
            "pin": pin,
            "overdue_count": len(overdue),
            "penalties": penalties,
            "total_penalty_exposure_kes": round(total_exposure, 2),
            "severity": severity,
            "assessed_at": datetime.now().isoformat(),
            "source": self.name,
        }

        self.log(
            f"Penalty exposure for {pin}: KES {total_exposure:,.0f} "
            f"({severity}) across {len(overdue)} obligation(s)"
        )
        return summary

    def _calculate_single(self, obligation: dict) -> dict:
        """Calculate penalty + interest for a single overdue obligation."""
        tax_type = obligation.get("tax_type", "unknown")
        days_overdue = abs(obligation.get("days_until_deadline", 0))
        estimated_amount = obligation.get("estimated_amount_kes", 0)
        rule_key = self.PENALTY_RULES.get(tax_type, "income_tax")

        # Calculate months overdue (partial months count as full)
        months_overdue = math.ceil(days_overdue / 30) if days_overdue > 0 else 0

        # Filing penalty
        filing_penalty = self._filing_penalty(rule_key, estimated_amount)

        # Late payment penalty (one-time 5%) — only if there's a tax amount
        payment_penalty = 0.0
        if estimated_amount > 0 and rule_key not in ("nssf", "shif", "housing_levy", "etims"):
            payment_penalty = estimated_amount * self.LATE_PAYMENT_PENALTY_PCT

        # Interest / monthly penalty
        interest = self._interest(rule_key, estimated_amount, months_overdue)

        total = filing_penalty + payment_penalty + interest

        return {
            "tax_type": tax_type,
            "rule_applied": rule_key,
            "days_overdue": days_overdue,
            "months_overdue": months_overdue,
            "estimated_tax_due_kes": estimated_amount,
            "estimated_penalty_kes": round(filing_penalty + payment_penalty, 2),
            "estimated_interest_kes": round(interest, 2),
            "total_exposure_kes": round(total, 2),
            "breakdown": self._breakdown(rule_key, filing_penalty, payment_penalty, interest),
        }

    def _filing_penalty(self, rule_key: str, amount: float) -> float:
        """Calculate late filing penalty based on tax type."""
        if rule_key == "vat":
            return max(self.VAT_LATE_FILING_FLAT, amount * self.VAT_LATE_FILING_PCT)

        if rule_key == "paye":
            return max(self.PAYE_LATE_FILING_FLAT, amount * self.PAYE_LATE_FILING_PCT)

        if rule_key == "tot":
            return max(self.TOT_LATE_FILING_FLAT, amount * self.TOT_LATE_FILING_PCT)

        if rule_key == "income_tax":
            return max(self.INCOME_TAX_LATE_FILING_FLAT, amount * self.INCOME_TAX_LATE_FILING_PCT)

        # NSSF, SHIF, housing_levy, eTIMS have no flat filing penalty — handled via monthly rate
        return 0.0

    def _interest(self, rule_key: str, amount: float, months: int) -> float:
        """
        Calculate late payment interest or monthly penalty.

        For standard taxes: 1% per month compounding on unpaid tax.
        For NSSF: 5% per month.
        For SHIF: 5% per month.
        For Housing Levy: 3% per month.
        """
        if amount <= 0 or months <= 0:
            return 0.0

        if rule_key == "nssf":
            return amount * self.NSSF_LATE_MONTHLY_PCT * months

        if rule_key == "shif":
            return amount * self.SHIF_LATE_MONTHLY_PCT * months

        if rule_key == "housing_levy":
            return amount * self.HOUSING_LEVY_LATE_MONTHLY_PCT * months

        if rule_key == "etims":
            # eTIMS is per-invoice, not interest-based — no compounding
            return 0.0

        # Standard taxes: 1% per month compounding
        # Compounding formula: P * ((1 + r)^n - 1)
        compounded = amount * ((1 + self.LATE_PAYMENT_INTEREST_MONTHLY) ** months - 1)
        return compounded

    def _breakdown(self, rule_key: str, filing: float, payment: float, interest: float) -> list[str]:
        """Human-readable breakdown of how the penalty was calculated."""
        lines = []

        if filing > 0:
            if rule_key == "paye":
                lines.append(f"Late filing penalty: KES {filing:,.0f} (25% of tax or KES 10,000)")
            elif rule_key == "vat":
                lines.append(f"Late filing penalty: KES {filing:,.0f} (5% of VAT or KES 10,000)")
            elif rule_key == "tot":
                lines.append(f"Late filing penalty: KES {filing:,.0f} (5% of TOT or KES 20,000)")
            else:
                lines.append(f"Late filing penalty: KES {filing:,.0f} (5% of tax or KES 20,000)")

        if payment > 0:
            lines.append(f"Late payment penalty: KES {payment:,.0f} (one-time 5%)")

        if interest > 0:
            if rule_key == "nssf":
                lines.append(f"NSSF late penalty: KES {interest:,.0f} (5%/month)")
            elif rule_key == "shif":
                lines.append(f"SHIF late penalty: KES {interest:,.0f} (5%/month)")
            elif rule_key == "housing_levy":
                lines.append(f"Housing Levy late penalty: KES {interest:,.0f} (3%/month)")
            else:
                lines.append(f"Late payment interest: KES {interest:,.0f} (1%/month compounding)")

        return lines

    def calculate_etims_exposure(self, missing_invoice_count: int) -> dict:
        """
        Separate helper for eTIMS non-compliance exposure.
        KES 50 per invoice not on eTIMS.
        """
        penalty = missing_invoice_count * self.ETIMS_PER_INVOICE
        return {
            "tax_type": "etims",
            "missing_invoices": missing_invoice_count,
            "penalty_per_invoice_kes": self.ETIMS_PER_INVOICE,
            "total_exposure_kes": penalty,
            "note": "KES 50 per invoice not transmitted via eTIMS",
        }
